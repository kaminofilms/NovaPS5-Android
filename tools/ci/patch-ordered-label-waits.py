#!/usr/bin/env python3
"""0.9.52: satisfy PM4 WAIT_REG_MEM on a known, queued constant label through
GPU submission order instead of suspending the queue for a CPU round trip.

Device evidence (Ever Forward PPSA04703, 0.9.51): the GPU thread spends
2.1-2.3 s of every 5 s in `queue_poll_wait` (12.5-13.8k calls) because every
PM4 queue is suspended on a pending GPU label, and each suspension also forces
a tiny submit (`PollCompletion` -> `Flush`).

All PM4 queues are recorded by one GPU thread into one CommandScheduler stream
on one Vulkan queue. The label's transfer copy (BufferCache::WriteEopLabel) is
followed by an all-commands memory barrier, so any GPU command recorded after
this WAIT_REG_MEM executes after the label is in memory. If the recorded value
already satisfies the original predicate, the waiting queue may continue
recording immediately. shadPS4 relies on the same single-queue ordering (its
ReleaseMem/EventWriteEop write labels at command-processing time).

Unchanged: guest CPU readers still use real completion / readback; IRQs stay on
the real timeline; a value that does not satisfy the predicate, unknown data,
texture-backed or invalidated labels keep the existing cooperative suspend.
NOVA_GPU_ORDERED_WAITS=0 disables only this shortcut.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])
renderer = root / 'src/graphics/host_gpu/renderer'
changes = {}


def edit(path, old, new):
    s = changes.get(path, path.read_text())
    if s.count(old) != 1:
        raise SystemExit(f'NOVA_ORDERED_WAIT: anchor changed {path}: {old[:90]!r}')
    changes[path] = s.replace(old, new, 1)


cost = renderer / 'novaRenderCosts.h'
edit(cost, 'inline bool DeadCellsProfile() {', '''inline bool OrderedLabelWaits() {
    static const bool enabled = [] {
        const char* value = std::getenv("NOVA_GPU_ORDERED_WAITS");
        return !(value && std::string_view(value) == "0");
    }();
    return enabled;
}
inline bool DeadCellsProfile() {''')
edit(cost, 'QueuePollWait, Count };', 'QueuePollWait, EopLabelOrdered, Count };')
edit(cost, '"queue_poll_wait"', '"queue_poll_wait", "eop_label_ordered"')

h = renderer / 'cache/bufferCache.h'
edit(h, '\tbool IsEopLabelPending(uint64_t vaddr, uint64_t size);',
     '\tbool IsEopLabelPending(uint64_t vaddr, uint64_t size);\n'
     '\t// GPU-thread only. Known recorded bytes of a still-tracked label; no completion claim.\n'
     '\tbool TryPeekEopLabel(uint64_t vaddr, void* data, uint64_t size);')

c = renderer / 'cache/bufferCache.cpp'
edit(c, 'bool BufferCache::IsEopLabelPending(uint64_t vaddr, uint64_t size) {',
     '''bool BufferCache::TryPeekEopLabel(uint64_t vaddr, void* data, uint64_t size) {
    if (!NovaRender::LabelReadbackProfile() || data == nullptr || (size != 4 && size != 8) ||
        !GuestRange {vaddr, size}.Valid() || !m_gpu_modified_ranges.Contains(vaddr, size)) return false;
    const auto known = m_eop_labels.Find(vaddr, size);
    if (!known || m_texture_cache.FindImageFromRange(vaddr, size)) return false;
    std::memcpy(data, known->bytes.data() + (vaddr - known->address), size);
    return true;
}

bool BufferCache::IsEopLabelPending(uint64_t vaddr, uint64_t size) {''')

gr = root / 'src/graphics/guest_gpu/graphicsRun.cpp'
edit(gr, '''	if (NovaRender::LabelReadbackProfile() && m_renderer.GetBufferCache().IsEopLabelPending(
	        reinterpret_cast<uint64_t>(addr), sizeof(T))) {''',
     '''	// Single-queue GPU order already places later recorded work after the label
	// copy and its barrier; continue recording when the queued value satisfies
	// the original predicate. Guest CPU readers still wait for real completion.
	if (NovaRender::LabelReadbackProfile() && NovaRender::OrderedLabelWaits()) {
		T nova_known {};
		if (m_renderer.GetBufferCache().TryPeekEopLabel(reinterpret_cast<uint64_t>(addr), &nova_known, sizeof(T)) &&
		    TestWaitRegMemValue(nova_known, ref, mask, func)) {
			NovaRender::Scope cost(NovaRender::Cost::EopLabelOrdered);
#if defined(KYTY_NOVA_FEX)
			if (m_nova_wait_addr != nullptr) {
				m_nova_wait_addr = nullptr;
				g_nova_gpu_stall_since_ms.store(0, std::memory_order_relaxed);
			}
#endif
			return;
		}
	}
	if (NovaRender::LabelReadbackProfile() && m_renderer.GetBufferCache().IsEopLabelPending(
	        reinterpret_cast<uint64_t>(addr), sizeof(T))) {''')

for path, s in changes.items():
    path.write_text(s)
print('NOVA_ORDERED_WAIT: known queued labels satisfy PM4 waits through GPU order; CPU readers/IRQs unchanged; opt-out NOVA_GPU_ORDERED_WAITS=0')
