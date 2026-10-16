#!/usr/bin/env python3
"""Ever Forward: record constant EOP labels through the coherent GPU buffer cache."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
changes = {}
def edit(path, old, new):
    text = changes.get(path, (root / path).read_text())
    if text.count(old) != 1:
        raise SystemExit(f'NOVA_GPU_LABEL: anchor changed: {path}: {old[:80]!r}')
    changes[path] = text.replace(old, new, 1)

base = 'src/graphics/host_gpu/renderer/cache/'
edit(base+'bufferCache.h', '\tvoid FillBuffer(uint64_t vaddr, uint64_t size, uint32_t value, bool is_gds);',
     '\t// GPU-thread only. False leaves the original drained CPU fallback available.\n'
     '\tbool WriteEopLabel(uint64_t vaddr, const void* data, uint64_t size);\n'
     '\tvoid FillBuffer(uint64_t vaddr, uint64_t size, uint32_t value, bool is_gds);')
edit(base+'bufferCache.cpp', 'void BufferCache::Register(BufferId id) {', '''bool BufferCache::WriteEopLabel(uint64_t vaddr, const void* data, uint64_t size) {
	// Do not reinterpret texture-backed or unaligned labels as ordinary buffers.
	if (vaddr == 0 || (vaddr & 3u) != 0 || (size != 4 && size != 8) ||
	    !GuestRange {vaddr, size}.Valid() || m_texture_cache.FindImageFromRange(vaddr, size)) {
		return false;
	}
	// ObtainBuffer marks the exact dirty bytes and protects CPU access before any
	// recording. CPU faults and explicit PM4 reads download from the real GPU tick.
	NovaRender::Scope nova_gpu_label_cost(NovaRender::Cost::EopGpu);
	auto [buffer, offset] = ObtainBuffer(vaddr, size, true);
	(void)offset;
	m_scheduler.EndRendering();
	vk::MemoryBarrier2 release {};
	release.srcStageMask = vk::PipelineStageFlagBits2::eAllCommands;
	release.srcAccessMask = vk::AccessFlagBits2::eMemoryWrite;
	release.dstStageMask = vk::PipelineStageFlagBits2::eTransfer;
	release.dstAccessMask = vk::AccessFlagBits2::eTransferWrite;
	vk::DependencyInfo dependency {};
	dependency.memoryBarrierCount = 1;
	dependency.pMemoryBarriers = &release;
	m_scheduler.Current().Handle().pipelineBarrier2(dependency);
	// Copies immutable bytes into the existing flushed staging ring. Its buffer
	// barriers preserve later GPU reads; there is no CPU store or invented signal.
	WriteDataBuffer(*buffer, vaddr, data, size);
	return true;
}

void BufferCache::Register(BufferId id) {''')
gr = 'src/graphics/guest_gpu/graphicsRun.cpp'
edit(gr, '\tauto complete_write = [&](auto data, bool timestamp) {\n\t\tNovaRender::Scope nova_eop_cost(NovaRender::Cost::EopDrain);', '''	auto complete_write = [&](auto data, bool timestamp) {
		if (NovaRender::EverProfile() && !timestamp &&
		    m_renderer.GetBufferCache().WriteEopLabel(
		        reinterpret_cast<uint64_t>(dst_gpu_addr), &data, sizeof(data))) {
			// IRQ callbacks are attached to the actual GPU timeline, after the copy.
			// CPU label readers use buffer-cache readback, including before this IRQ.
			if (with_interrupt) {
				GetScheduler().DeferPriorityOperation(
				    [&renderer = m_renderer, event_id = m_interrupt_event_id, interrupt_context_id] {
					    renderer.TriggerInterrupt(event_id, interrupt_context_id);
				    });
			}
			return;
		}
		NovaRender::Scope nova_eop_cost(NovaRender::Cost::EopDrain);''')
edit(gr, '\t// The label is guest memory: read it through its host address (addr stays the identity).\n\tconst T* value = GuestMemory::Ptr(addr, sizeof(T));', '''	// A queued GPU label may not yet be in CPU backing. Resolve only actual dirty
	// bytes through the cache before evaluating the original wait predicate.
	T nova_label_value {};
	const T* value = nullptr;
	if (NovaRender::EverProfile()) {
		EXIT_IF(!LibKernel::Memory::TryReadBufferBacking(
		    reinterpret_cast<uint64_t>(addr), &nova_label_value, sizeof(T)));
		value = &nova_label_value;
	} else {
		value = GuestMemory::Ptr(addr, sizeof(T));
	}''')

for path, text in changes.items():
    (root / path).write_text(text)
print('NOVA_GPU_LABEL: Ever-only GPU-ordered constant labels; coherent reads and timeline IRQs')
