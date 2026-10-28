#!/usr/bin/env python3
"""Task 1: coalesce CPU-write-fault readbacks of GPU-written buffer memory.

Luna (PPSA36257, Kyty, 0.9.106) spends 2.0-3.0 s of every 5 s on its render thread waiting for
GPU readbacks caused by guest CPU writes to GPU-written pages: 1,000-1,700 HandleFaultWrite
readbacks per 5 s, ~4 KiB each, nearly all direct_overlap (NOVA_RENDER_COST readback_caller,
NOVA_CPU_WAIT bufferCache.cpp:373). Each fault submits the command buffer and waits for the GPU,
for one 4 KiB page; the next page of the same GPU-written run faults again.

When a write fault hits a GPU-written range, download every GPU-written byte of the same buffer
inside an aligned window around the fault (NOVA_FAULT_COALESCE_KB, default 256; 0 = off) in
that same single wait, then hand the whole span to the CPU exactly as the faulting page is
(GPU-modified cleared, CPU-modified set: re-uploaded before the GPU uses it again). Nothing is
discarded or skipped: the extra bytes are real GPU data read back early, and later GPU writes
re-mark their ranges as before. Ranges backing images are excluded (page path unchanged).

  NOVA_FAULT_COALESCE: window_kb=256 faults=1600 coalesced=40 extra_pages=900 extra_kib=3600
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer/cache/bufferCache.cpp'
s = p.read_text()
old = '''		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];

		if (DownloadBufferMemory<false>(buffer, vaddr, size, context)) {
			m_memory_tracker.UnmarkRegionAsGpuModified(vaddr, size);
		}
		if (is_write) {
			m_memory_tracker.MarkRegionAsCpuModified(vaddr, size);
		}
	});
}
'''
if s.count(old) != 1:
    raise SystemExit(f'0993: ReadMemory download anchor changed ({s.count(old)}); no source written')
new = '''		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];

		// Nova 0993: a write fault into a GPU-written run reads back the run's neighbourhood
		// in the same wait (see tools/ci/patch-0993-fault-coalesce.py).
		uint64_t span_begin = vaddr, span_size = size;
		if (is_write && context.is_fault_origin) {
			static const uint64_t window = [] {
				const char* value = std::getenv("NOVA_FAULT_COALESCE_KB");
				const long  kb    = value ? std::strtol(value, nullptr, 10) : 256;
				return (kb <= 0 || kb > 4096 || (kb & (kb - 1)) != 0) ? uint64_t {0} : uint64_t(kb) * 1024u;
			}();
			const uint64_t page = vaddr & ~(TRACKER_PAGE_SIZE - 1);
			if (window > TRACKER_PAGE_SIZE && page + TRACKER_PAGE_SIZE > page &&
			    m_gpu_modified_ranges.Intersects(page, TRACKER_PAGE_SIZE)) {
				const uint64_t buffer_begin = buffer.CpuAddress(), buffer_end = buffer_begin + buffer.Size();
				const uint64_t window_begin = std::max(vaddr & ~(window - 1), buffer_begin);
				const uint64_t window_end   = std::min((vaddr & ~(window - 1)) + window, buffer_end);
				uint64_t       first = UINT64_MAX, last = 0;
				if (window_end > window_begin) {
					m_gpu_modified_ranges.ForEachInRange(window_begin, window_end - window_begin, [&](uint64_t begin, uint64_t end) {
						first = std::min(first, std::max(begin, window_begin));
						last  = std::max(last, std::min(end, window_end));
					});
				}
				if (first < last) {
					const uint64_t begin = std::min(first & ~(TRACKER_PAGE_SIZE - 1), page);
					const uint64_t end   = std::max(Common::AlignUp(last, TRACKER_PAGE_SIZE), page + TRACKER_PAGE_SIZE);
					const uint64_t clamped_begin = std::max(begin, buffer_begin), clamped_end = std::min(end, buffer_end);
					if (clamped_end > clamped_begin && clamped_end - clamped_begin > TRACKER_PAGE_SIZE &&
					    IsRegionRegistered(clamped_begin, clamped_end - clamped_begin) &&
					    !m_texture_cache.FindImageFromRange(clamped_begin, clamped_end - clamped_begin)) {
						span_begin = clamped_begin;
						span_size  = clamped_end - clamped_begin;
					}
				}
			}
			struct Stats {
				uint64_t faults = 0, coalesced = 0, extra_pages = 0;
				std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
			};
			static Stats stats;
			++stats.faults;
			if (span_size > size) {
				++stats.coalesced;
				stats.extra_pages += span_size / TRACKER_PAGE_SIZE - 1;
			}
			if (const auto now = std::chrono::steady_clock::now(); now - stats.start >= std::chrono::seconds(5)) {
				std::fprintf(stderr, "NOVA_FAULT_COALESCE: window_kb=%llu faults=%llu coalesced=%llu extra_pages=%llu extra_kib=%llu\\n",
				             static_cast<unsigned long long>(window / 1024), static_cast<unsigned long long>(stats.faults),
				             static_cast<unsigned long long>(stats.coalesced), static_cast<unsigned long long>(stats.extra_pages),
				             static_cast<unsigned long long>(stats.extra_pages * TRACKER_PAGE_SIZE / 1024));
				stats = {};
				stats.start = now;
			}
		}

		if (DownloadBufferMemory<false>(buffer, span_begin, span_size, context)) {
			m_memory_tracker.UnmarkRegionAsGpuModified(span_begin, span_size);
		}
		if (is_write) {
			m_memory_tracker.MarkRegionAsCpuModified(span_begin, span_size);
		}
	});
}
'''
s = s.replace(old, new, 1)
for header in ('#include <chrono>', '#include <cstdio>', '#include <cstdlib>'):
    if header not in s:
        first = s.index('#include')
        s = s[:first] + header + '\n' + s[first:]
p.write_text(s)
print('0993: write-fault readbacks download the GPU-written neighbourhood in one wait (NOVA_FAULT_COALESCE)')
