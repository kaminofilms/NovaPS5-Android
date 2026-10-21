#!/usr/bin/env python3
"""0.9.61: keep GPU render passes open across redundant barriers and deferred downloads.

0.9.60 NOVA_PASS_BREAK (Ever Forward, 5 s): ~11,000 render passes ended, of which ~3,600 by
EmitGlobalBarrier (PM4 PS/CS partial flushes, CB/DB writebacks, RELEASE_MEM cache actions) and
~1,600 by the 0.9.57 deferred-write-fault download. On a tiled GPU every pass end stores and
reloads the attachments; the GPU was 65-71 % busy at ~10 FPS.

  1. Global barrier elision. Inside one Vulkan render pass, draws that only write their colour /
     depth attachments are already ordered (rasterization order), and reading an attachment as a
     texture changes its layout, which ends the pass through Image::Transit. A PM4 flush/barrier
     therefore only needs a Vulkan barrier when, since the last emitted barrier, a draw wrote
     through a storage buffer/image, used raw memory access (uses_dma / BDA), or a compute
     dispatch was recorded. If a pass is open and none of these happened, the pass stays open and
     the barrier is skipped. Every other case is unchanged (end pass + full barrier).
     Copies recorded by the buffer/texture caches carry their own barriers.
  2. Deferred-write-fault downloads (bufferCache NovaDeferWriteFault) are recorded when the open
     pass ends instead of ending it. Their completion callback already runs only after the whole
     command buffer, every non-draw operation still ends the pass first (so order against other
     copies is kept), and any draw that writes memory while a download is pending ends the pass
     first (ObtainBuffer is_written / storage image), exactly as before.

NOVA_PASS_MERGE reports elided / emitted barriers (with the reason) and deferred downloads every 5 s.
NOVA_PASS_MERGE=0 restores 0.9.60 behaviour.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]); g = root / 'src/graphics'; r = g / 'host_gpu/renderer'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0961_PASS_MERGE: anchor changed {path.name}: {old[:80]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


# ---- shared state (render.h) ----
rh = r / 'render.h'
edit(rh, '#include <array>\n', '#include <array>\n#include <atomic>\n#include <cstdlib>\n#include <functional>\n')
edit(rh, 'namespace Libs::Graphics {\n', '''namespace Libs::Graphics {

// Nova 0.9.61: render-pass merging (patch-0961-pass-merge.py).
namespace NovaPassMerge {
inline bool Enabled() {
	static const bool enabled = [] {
		const char* v = std::getenv("NOVA_PASS_MERGE");
		return v == nullptr || v[0] != '0';
	}();
	return enabled;
}
// Bits: work since the last emitted global barrier that a later barrier must order.
enum : uint32_t { kStorage = 1u, kDma = 2u, kDispatch = 4u };
inline std::atomic<uint32_t>& Unsynced() {
	static std::atomic<uint32_t> bits {kDispatch}; // unknown at start: emit the first barrier
	return bits;
}
struct Counters {
	std::atomic<uint64_t> elided {0}, emitted_closed {0}, emitted_storage {0}, emitted_dma {0},
	    emitted_dispatch {0}, deferred_downloads {0}, flushed_for_write {0};
};
inline Counters& Count() {
	static Counters c;
	return c;
}
} // namespace NovaPassMerge
''', 1)
edit(rh, ''' bool RasterScaleNeedsFlush(const Image* image,vk::ImageLayout layout,vk::AccessFlags2 access)const {''', '''	// Nova 0.9.61: true while a render pass is open.
	[[nodiscard]] bool NovaRendering() const noexcept { return m_rendering; }
	// Nova 0.9.61: record `work` (non-draw commands) when the open pass ends; at once if none is open.
	void NovaAfterPass(std::function<void(vk::CommandBuffer)> work) const {
		if (m_rendering) {
			m_nova_after_pass.push_back(std::move(work));
		} else {
			work(Handle());
		}
	}
	// Nova 0.9.61: a draw is about to write memory; record deferred work first.
	void NovaFlushAfterPass() const {
		if (!m_nova_after_pass.empty()) {
			NovaPassMerge::Count().flushed_for_write.fetch_add(1, std::memory_order_relaxed);
			EndRendering();
		}
	}
 bool RasterScaleNeedsFlush(const Image* image,vk::ImageLayout layout,vk::AccessFlags2 access)const {''')
edit(rh, '	mutable bool        m_rendering   = false;\n',
     '	mutable bool        m_rendering   = false;\n	mutable std::vector<std::function<void(vk::CommandBuffer)>> m_nova_after_pass;\n')

cx = r / 'context.cpp'
edit(cx, '''      if(a.raster_owner && a.image_view)a.raster_owner->EndRasterScale(a.image_view,a.image_layout,Handle());
    }
	m_render_state = {};
}''', '''      if(a.raster_owner && a.image_view)a.raster_owner->EndRasterScale(a.image_view,a.image_layout,Handle());
    }
	m_render_state = {};
	// Nova 0.9.61: non-draw work deferred while this pass was open, in recording order.
	if (!m_nova_after_pass.empty()) {
		auto work = std::move(m_nova_after_pass);
		m_nova_after_pass.clear();
		for (auto& w: work) w(Handle());
	}
}''')

# ---- 1. global barrier elision ----
gr = g / 'guest_gpu/graphicsRun.cpp'
edit(gr, '''void CommandProcessor::EmitGlobalBarrier() {
	Common::LockGuard lock(m_renderer.GetMutex());
''', '''void CommandProcessor::EmitGlobalBarrier() {
	Common::LockGuard lock(m_renderer.GetMutex());
	if (NovaPassMerge::Enabled()) {
		auto&          count = NovaPassMerge::Count();
		const uint32_t bits  = NovaPassMerge::Unsynced().load(std::memory_order_relaxed);
		if (bits == 0 && GetScheduler().Active() && CurrentBuffer().NovaRendering()) {
			// Only attachment writes since the last barrier: already ordered inside the pass.
			count.elided.fetch_add(1, std::memory_order_relaxed);
			NovaReportPassMerge();
			return;
		}
		if (bits & NovaPassMerge::kDispatch) count.emitted_dispatch.fetch_add(1, std::memory_order_relaxed);
		else if (bits & NovaPassMerge::kDma) count.emitted_dma.fetch_add(1, std::memory_order_relaxed);
		else if (bits & NovaPassMerge::kStorage) count.emitted_storage.fetch_add(1, std::memory_order_relaxed);
		else count.emitted_closed.fetch_add(1, std::memory_order_relaxed);
		NovaPassMerge::Unsynced().store(0, std::memory_order_relaxed);
		NovaReportPassMerge();
	}
''')
edit(gr, 'void CommandProcessor::EmitGlobalBarrier() {', '''// Nova 0.9.61: NOVA_PASS_MERGE report, every 5 s.
static void NovaReportPassMerge() {
	static auto start = std::chrono::steady_clock::now();
	const auto  now   = std::chrono::steady_clock::now();
	if (now - start < std::chrono::seconds(5)) return;
	start       = now;
	auto& c     = NovaPassMerge::Count();
	std::fprintf(stderr,
	             "NOVA_PASS_MERGE: barriers_elided=%llu emitted(no_pass=%llu storage=%llu dma=%llu dispatch=%llu) "
	             "downloads_deferred=%llu flushed_for_write=%llu\\n",
	             (unsigned long long)c.elided.exchange(0), (unsigned long long)c.emitted_closed.exchange(0),
	             (unsigned long long)c.emitted_storage.exchange(0), (unsigned long long)c.emitted_dma.exchange(0),
	             (unsigned long long)c.emitted_dispatch.exchange(0), (unsigned long long)c.deferred_downloads.exchange(0),
	             (unsigned long long)c.flushed_for_write.exchange(0));
}

void CommandProcessor::EmitGlobalBarrier() {''')
s = changes[gr]
if '#include <chrono>' not in s:
    s = s.replace('#include', '#include <chrono>\n#include', 1)
changes[gr] = s

# Work that a later barrier must order.
rc = r / 'renderCompute.cpp'
edit(rc, '''	buffer.EndRendering();
	auto& pipeline =
	    m_context.GetPipelineCache().GetComputePipeline(input_info, compute_program);''', '''	buffer.EndRendering();
	NovaPassMerge::Unsynced().fetch_or(NovaPassMerge::kDispatch, std::memory_order_relaxed);
	auto& pipeline =
	    m_context.GetPipelineCache().GetComputePipeline(input_info, compute_program);''')
edit(rc, '''	buffer.EndRendering();
	auto& pipeline = m_context.GetPipelineCache().GetComputePipeline(input_info, compute_program);''', '''	buffer.EndRendering();
	NovaPassMerge::Unsynced().fetch_or(NovaPassMerge::kDispatch, std::memory_order_relaxed);
	auto& pipeline = m_context.GetPipelineCache().GetComputePipeline(input_info, compute_program);''')
ds = r / 'pipeline/descriptors.cpp'
edit(ds, '''	if (uses_dma) {
		m_context.PrepareBda();
	}
	for (auto* stage: stages) {
		RebindImages(*stage);
	}''', '''	if (uses_dma) {
		m_context.PrepareBda();
		// Raw memory access may write anything: a later barrier must not be skipped.
		NovaPassMerge::Unsynced().fetch_or(NovaPassMerge::kDma, std::memory_order_relaxed);
	}
	for (auto* stage: stages) {
		RebindImages(*stage);
	}''')
edit(ds, '''	auto [buffer, offset] = context.GetBufferCache().ObtainBuffer(
	    address, size, resource.written,''', '''	if (resource.written) {
		NovaPassMerge::Unsynced().fetch_or(NovaPassMerge::kStorage, std::memory_order_relaxed);
	}
	auto [buffer, offset] = context.GetBufferCache().ObtainBuffer(
	    address, size, resource.written,''')
edit(ds, '''	const bool storage = resource.written;
	if (storage) {
		ValidateStorageImageResource(resource);
	}''', '''	const bool storage = resource.written;
	if (storage) {
		ValidateStorageImageResource(resource);
		NovaPassMerge::Unsynced().fetch_or(NovaPassMerge::kStorage, std::memory_order_relaxed);
		if (m_context.GetCommandScheduler().Active()) m_context.GetCommandScheduler().Current().NovaFlushAfterPass();
	}''')

# ---- 2. deferred-write-fault download at pass end ----
bc = r / 'cache/bufferCache.cpp'
edit(bc, '''	auto& command = m_scheduler.Current();
	command.EndRendering();
	const auto              native = command.Handle();
	vk::BufferMemoryBarrier before {};
	before.srcAccessMask       = vk::AccessFlagBits::eMemoryRead | vk::AccessFlagBits::eMemoryWrite;
	before.dstAccessMask       = vk::AccessFlagBits::eTransferRead;
	before.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
	before.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
	before.buffer              = buffer.Handle();
	before.offset              = 0;
	before.size                = buffer.Size();
	native.pipelineBarrier(vk::PipelineStageFlagBits::eAllCommands, vk::PipelineStageFlagBits::eTransfer, {}, 0,
	                       nullptr, 1, &before, 0, nullptr);
	native.copyBuffer(buffer.Handle(), m_download_buffer.Handle(), static_cast<uint32_t>(copies.size()),
	                  copies.data());
	auto after          = before;
	after.srcAccessMask = vk::AccessFlagBits::eTransferWrite;
	after.dstAccessMask = vk::AccessFlagBits::eHostRead;
	after.buffer        = m_download_buffer.Handle();
	after.offset        = offset;
	after.size          = total;
	native.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,
	                       vk::PipelineStageFlagBits::eAllCommands | vk::PipelineStageFlagBits::eHost, {}, 0,
	                       nullptr, 1, &after, 0, nullptr);''', '''	auto& command = m_scheduler.Current();
	const auto record = [source = buffer.Handle(), source_size = buffer.Size(), download = m_download_buffer.Handle(),
	                     copies, offset, total](vk::CommandBuffer native) {
		vk::BufferMemoryBarrier before {};
		before.srcAccessMask       = vk::AccessFlagBits::eMemoryRead | vk::AccessFlagBits::eMemoryWrite;
		before.dstAccessMask       = vk::AccessFlagBits::eTransferRead;
		before.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
		before.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
		before.buffer              = source;
		before.offset              = 0;
		before.size                = source_size;
		native.pipelineBarrier(vk::PipelineStageFlagBits::eAllCommands, vk::PipelineStageFlagBits::eTransfer, {}, 0,
		                       nullptr, 1, &before, 0, nullptr);
		native.copyBuffer(source, download, static_cast<uint32_t>(copies.size()), copies.data());
		auto after          = before;
		after.srcAccessMask = vk::AccessFlagBits::eTransferWrite;
		after.dstAccessMask = vk::AccessFlagBits::eHostRead;
		after.buffer        = download;
		after.offset        = offset;
		after.size          = total;
		native.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,
		                       vk::PipelineStageFlagBits::eAllCommands | vk::PipelineStageFlagBits::eHost, {}, 0,
		                       nullptr, 1, &after, 0, nullptr);
	};
	if (NovaPassMerge::Enabled() && command.NovaRendering()) {
		// 0.9.61: record when the open pass ends (same command buffer, before any other copy).
		NovaPassMerge::Count().deferred_downloads.fetch_add(1, std::memory_order_relaxed);
		command.NovaAfterPass(record);
	} else {
		command.EndRendering();
		record(command.Handle());
	}''')
# A draw/dispatch that writes memory records pending deferred work first.
edit(bc, '''	NovaPumpDeferredWriteFaults();
	if (!is_written && size <= CACHING_PAGESIZE &&''', '''	NovaPumpDeferredWriteFaults();
	if (is_written) command.NovaFlushAfterPass();
	if (!is_written && size <= CACHING_PAGESIZE &&''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0961_PASS_MERGE: redundant global barriers kept inside the pass; write-fault downloads at pass end (NOVA_PASS_MERGE=0 restores)')
