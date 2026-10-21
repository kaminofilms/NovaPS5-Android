#!/usr/bin/env python3
"""0.9.57: deferred CPU write faults next to GPU-written bytes (Ever Forward).

Owner log (Ever Forward PPSA04703, 0.9.56, Turnip): ~980 CPU write faults per
5 s on 4 KiB pages that also hold GPU-written bytes. Each fault records a
download, waits for the whole GPU timeline (~3 ms) and publishes, costing about
3 of every 5 seconds of the GPU thread. Telemetry: address_disjoint=978/978,
direct_overlap=0: the CPU never writes the GPU's bytes, it only shares the page.

New path (Relaxed readback only, Ever Forward by default; NOVA_DEFERRED_WRITE_FAULTS
=1 enables it for any title, =0 disables it). A write fault qualifies when the
faulting byte is at least 64 bytes away from every GPU-written byte of its page
and no image overlaps the page. Then, on the GPU thread:

  1. The GPU-written byte ranges R of that page stay in the exact dirty-range
     set (still authoritative on the GPU side); a GPU->staging copy of R is
     recorded, and the current guest bytes of R are snapshotted.
  2. The page is released to the CPU immediately (no submit, no wait).
  3. When the copy completes, a priority operation copies the staged bytes into
     the job (it touches no cache state).
  4. Later on the GPU thread, each byte of R whose guest value still equals the
     snapshot receives the GPU value; bytes the CPU changed keep the CPU value
     and the page is marked CPU-modified so the GPU receives them. R then
     leaves the dirty set. If the GPU re-dirtied the page meanwhile, the job is
     dropped and R stays dirty (normal download on the next access).

While R is pending: uploads never copy bytes of the dirty set (the GPU copy is
newer), the stream-buffer shortcut, image sourcing, fills, copies and garbage
collection treat dirty bytes as GPU-owned. In normal operation a CPU-modified
page has no dirty bytes, so these checks change nothing outside this path.
CPU reads of R before step 4 see the previous bytes, which Relaxed readback
already allows (reads are not protected).
"""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0957_DWF: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


sync = src / 'graphics/host_gpu/novaSync.h'
edit(sync, 'inline uint32_t SubmitEveryDraws() {', '''// Nova 0.9.57: deferred CPU write faults next to GPU-written bytes. Default on for
// Ever Forward only; NOVA_DEFERRED_WRITE_FAULTS=1/0 overrides for any title.
inline bool DeferredWriteFaults() {
    static const bool on = [] {
        const char* value = std::getenv("NOVA_DEFERRED_WRITE_FAULTS");
        if (value && value[0] == '0') return false;
        if (value && value[0] == '1') return true;
        const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
        return title && std::string_view(title) == "PPSA04703";
    }();
    return on;
}
inline uint32_t SubmitEveryDraws() {''')

hdr = src / 'graphics/host_gpu/renderer/cache/bufferCache.h'
edit(hdr, '#include <map>\n', '#include <atomic>\n#include <map>\n#include <memory>\n')
edit(hdr, '''	template <bool async>
	[[nodiscard]] bool DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size, ReadbackContext context);
''', '''	template <bool async>
	[[nodiscard]] bool DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size, ReadbackContext context);
	// Nova 0.9.57 deferred write faults (patch-0957-deferred-write-faults.py). GPU thread only.
	struct NovaDwfJob {
		uint64_t                                   page = 0;
		std::vector<std::pair<uint64_t, uint64_t>> ranges; // [begin, end)
		std::vector<uint8_t>                       snapshot;
		std::vector<uint8_t>                       gpu;
		std::atomic<bool>                          ready {false};
	};
	std::vector<std::shared_ptr<NovaDwfJob>> m_nova_dwf;
	uint64_t m_nova_dwf_deferred = 0, m_nova_dwf_merged = 0, m_nova_dwf_conflicts = 0, m_nova_dwf_dropped = 0;
	[[nodiscard]] bool NovaDeferWriteFault(uint64_t fault_vaddr, ReadbackContext context);
	void               NovaPumpDeferredWriteFaults();
''')

cpp = src / 'graphics/host_gpu/renderer/cache/bufferCache.cpp'
s = cpp.read_text()
for inc in ('#include <cstdio>', '#include <chrono>', '#include "graphics/host_gpu/novaSync.h"',
            '#include "graphics/host_gpu/regionDefinitions.h"', '#include "kernel/memory.h"'):
    if inc not in s:
        i = s.index('#include')
        s = s[:i] + inc + '\n' + s[i:]
changes[cpp] = s

# --- the deferral itself, tried before the synchronous download ---
edit(cpp, '''		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];

		if (DownloadBufferMemory<false>(buffer, vaddr, size, context)) {''', '''		if (is_write && NovaDeferWriteFault(vaddr, context)) {
			return;
		}
		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];

		if (DownloadBufferMemory<false>(buffer, vaddr, size, context)) {''')

edit(cpp, '''BufferId BufferCache::FindBuffer(uint64_t vaddr, uint64_t size) {''', '''bool BufferCache::NovaDeferWriteFault(uint64_t fault_vaddr, ReadbackContext context) {
	if (!NovaSync::DeferredWriteFaults() || !context.is_fault_origin || NovaSync::PreciseReadbacks() ||
	    NovaSync::ReadbackOff()) {
		return false;
	}
	NovaPumpDeferredWriteFaults();
	if (m_nova_dwf.size() >= 256) return false;
	const uint64_t page = fault_vaddr & ~(TRACKER_PAGE_SIZE - 1);
	if (page + TRACKER_PAGE_SIZE < page) return false;
	// The host reports the first faulting byte only; keep a 64-byte guard band
	// (the widest x86 store) between it and every GPU-written byte.
	const uint64_t guard_begin = std::max(page, fault_vaddr >= 64 ? fault_vaddr - 64 : 0);
	const uint64_t guard_end   = std::min(page + TRACKER_PAGE_SIZE, fault_vaddr + 64);
	if (m_gpu_modified_ranges.Intersects(guard_begin, guard_end - guard_begin)) return false;
	if (m_texture_cache.FindImageFromRange(page, TRACKER_PAGE_SIZE)) return false;
	auto job = std::make_shared<NovaDwfJob>();
	job->page = page;
	m_gpu_modified_ranges.ForEachInRange(page, TRACKER_PAGE_SIZE, [&](uint64_t begin, uint64_t end) {
		job->ranges.emplace_back(begin, end);
	});
	if (job->ranges.empty()) return false; // nothing to download: the normal path is already cheap
	const uint64_t span_begin = job->ranges.front().first;
	const uint64_t span_end   = job->ranges.back().second;
	const auto*    owner      = m_page_table.Find(span_begin >> PageTable::kPageBits);
	if (owner == nullptr || !*owner) return false;
	auto& buffer = m_slot_buffers[*owner];
	if (!buffer.IsInBounds(span_begin, span_end - span_begin)) return false;

	std::vector<vk::BufferCopy> copies;
	uint64_t                    total = 0;
	for (const auto& [begin, end]: job->ranges) {
		copies.emplace_back(begin - buffer.CpuAddress(), total, end - begin);
		total += end - begin;
	}
	job->snapshot.resize(total);
	uint64_t at = 0;
	for (const auto& [begin, end]: job->ranges) {
		if (!Libs::LibKernel::Memory::TryReadBacking(begin, job->snapshot.data() + at, end - begin)) return false;
		at += end - begin;
	}
	auto [mapped, offset] = m_download_buffer.Map(total, 64);
	if (mapped == nullptr) return false;
	m_download_buffer.Commit();
	for (auto& copy: copies) copy.dstOffset += offset;

	auto& command = m_scheduler.Current();
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
	                       nullptr, 1, &after, 0, nullptr);
	m_scheduler.DeferPriorityOperation([this, job, mapped, offset, total] {
		m_download_buffer.Invalidate(offset, total);
		job->gpu.assign(mapped, mapped + total);
		job->ready.store(true, std::memory_order_release);
	});
	// Release the page to the CPU now; the exact dirty ranges keep GPU ownership of R.
	m_memory_tracker.UnmarkRegionAsGpuModified(fault_vaddr, 1);
	m_memory_tracker.MarkRegionAsCpuModified(fault_vaddr, 1);
	m_nova_dwf.push_back(std::move(job));
	++m_nova_dwf_deferred;
	return true;
}

void BufferCache::NovaPumpDeferredWriteFaults() {
	if (m_nova_dwf.empty()) return;
	size_t keep = 0;
	for (size_t i = 0; i < m_nova_dwf.size(); i++) {
		auto job = m_nova_dwf[i];
		if (!job->ready.load(std::memory_order_acquire)) {
			m_nova_dwf[keep++] = std::move(job);
			continue;
		}
		if (m_memory_tracker.IsRegionGpuModified(job->page, TRACKER_PAGE_SIZE)) {
			++m_nova_dwf_dropped; // the GPU wrote the page again: R stays dirty
			continue;
		}
		bool     conflict = false;
		uint64_t at       = 0;
		for (const auto& [begin, end]: job->ranges) {
			const auto bytes = end - begin;
			if (m_gpu_modified_ranges.Intersects(begin, bytes)) {
				std::vector<uint8_t> current(bytes);
				if (Libs::LibKernel::Memory::TryReadBacking(begin, current.data(), bytes)) {
					for (uint64_t k = 0; k < bytes; k++) {
						if (current[k] == job->snapshot[at + k]) {
							current[k] = job->gpu[at + k];
						} else {
							conflict = true; // the CPU wrote this byte after the fault: keep it
						}
					}
					(void)Libs::LibKernel::Memory::TryWriteBacking(begin, current.data(), bytes);
				}
				m_eop_labels.Invalidate(begin, bytes);
				m_gpu_modified_ranges.Subtract(begin, bytes);
			}
			at += bytes;
		}
		if (conflict) {
			m_memory_tracker.MarkRegionAsCpuModified(job->page, TRACKER_PAGE_SIZE);
			++m_nova_dwf_conflicts;
		}
		++m_nova_dwf_merged;
	}
	m_nova_dwf.resize(keep);
	static auto last = std::chrono::steady_clock::now();
	const auto  now  = std::chrono::steady_clock::now();
	if (now - last >= std::chrono::seconds(5)) {
		last = now;
		std::fprintf(stderr, "NOVA_DEFERRED_WRITE_FAULTS: deferred=%llu merged=%llu cpu_kept=%llu dropped=%llu pending=%zu\\n",
		             (unsigned long long)m_nova_dwf_deferred, (unsigned long long)m_nova_dwf_merged,
		             (unsigned long long)m_nova_dwf_conflicts, (unsigned long long)m_nova_dwf_dropped, m_nova_dwf.size());
		m_nova_dwf_deferred = m_nova_dwf_merged = m_nova_dwf_conflicts = m_nova_dwf_dropped = 0;
	}
}

BufferId BufferCache::FindBuffer(uint64_t vaddr, uint64_t size) {''')

# --- uploads never overwrite GPU-owned dirty bytes ---
edit(cpp, '''	    [&](uint64_t address, uint64_t bytes) noexcept {
		    copies.emplace_back(total_size, buffer.Offset(address), bytes);
		    total_size += bytes;
	    },''', '''	    [&](uint64_t address, uint64_t bytes) noexcept {
		    // Nova 0.9.57: bytes still in the exact GPU dirty set are newer on the GPU
		    // (only possible after a deferred write fault); upload the rest.
		    uint64_t cursor = address;
		    const uint64_t end = address + bytes;
		    m_gpu_modified_ranges.ForEachInRange(address, bytes, [&](uint64_t dirty_begin, uint64_t dirty_end) {
			    if (dirty_begin > cursor) {
				    copies.emplace_back(total_size, buffer.Offset(cursor), dirty_begin - cursor);
				    total_size += dirty_begin - cursor;
			    }
			    cursor = std::max(cursor, dirty_end);
		    });
		    if (end > cursor) {
			    copies.emplace_back(total_size, buffer.Offset(cursor), end - cursor);
			    total_size += end - cursor;
		    }
	    },''')

# --- GPU-owned dirty bytes are GPU-modified for every shortcut ---
edit(cpp, '''	if (!is_written && size <= CACHING_PAGESIZE &&
	    !m_memory_tracker.IsRegionGpuModified(vaddr, size) &&''', '''	NovaPumpDeferredWriteFaults();
	if (!is_written && size <= CACHING_PAGESIZE &&
	    !m_memory_tracker.IsRegionGpuModified(vaddr, size) && !m_gpu_modified_ranges.Intersects(vaddr, size) &&''')
edit(cpp, '''bool BufferCache::IsRegionGpuModified(uint64_t vaddr, uint64_t size) {
	return m_memory_tracker.IsRegionGpuModified(vaddr, size);
}''', '''bool BufferCache::IsRegionGpuModified(uint64_t vaddr, uint64_t size) {
	// Nova 0.9.57: exact dirty bytes count too (deferred write faults).
	return m_memory_tracker.IsRegionGpuModified(vaddr, size) || m_gpu_modified_ranges.Intersects(vaddr, size);
}''')
edit(cpp, '''		const bool dirty = m_memory_tracker.IsRegionGpuModified(buffer.CpuAddress(), buffer.Size());''',
     '''		const bool dirty = m_memory_tracker.IsRegionGpuModified(buffer.CpuAddress(), buffer.Size()) ||
		                   m_gpu_modified_ranges.Intersects(buffer.CpuAddress(), buffer.Size());''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0957_DWF: deferred CPU write faults next to GPU-written bytes (Ever Forward default)')
