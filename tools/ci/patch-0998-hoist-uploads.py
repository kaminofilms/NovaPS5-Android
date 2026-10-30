#!/usr/bin/env python3
"""Task 1: record CPU-to-GPU buffer uploads ahead of the current command buffer (no pass break).

Wonder Boy at 720p (0.9.112): ~58 render-pass breaks per frame, ~29 of them from buffer uploads
(bufferCache.cpp SynchronizeBuffer: EndRendering + full-pipeline barrier + copy + barrier). Lowering
the resolution no longer changes GPU time, so these per-upload drains, not pixels, dominate.

An upload is recorded into a "pre" command buffer, submitted in the same vkQueueSubmit just
before the current one, instead of ending the render pass, when:
  * none of the uploaded pages were CPU-written (write fault / invalidation from any thread:
    guest CPU, WRITE_DATA, CPU-side DMA/fill, labels) since the current command buffer began, so
    the bytes were already in guest memory before anything in that command buffer ran and every
    earlier command that reads them sees the same value either way, and
  * the destination buffer has no other write recorded in the current command buffer (buffer
    joins/copies, image-to-buffer syncs, shader writes, label writes), so nothing
    recorded earlier can overwrite the upload or be overwritten out of order.
Otherwise the original in-order path is used. Barriers are unchanged (all prior commands ->
transfer -> all later commands, by queue submission order). NOVA_HOIST_UPLOADS=0 disables.

  NOVA_HOIST_UPLOADS: window_ms=5000 hoisted=140 in_order=12
"""
from pathlib import Path
import sys

r = Path(sys.argv[1]) / 'src/graphics'
files = {
    'h': r / 'host_gpu/renderer/commandScheduler.h',
    'c': r / 'host_gpu/renderer/commandScheduler.cpp',
    'b': r / 'host_gpu/renderer/cache/bufferCache.cpp',
    's': r / 'host_gpu/renderer/cache/streamBuffer.h',
}
text = {k: p.read_text() for k, p in files.items()}

def once(key, old, new):
    if text[key].count(old) != 1:
        raise SystemExit(f'0998: {files[key].name} anchor changed ({text[key].count(old)}): {old[:60]!r}; no source written')
    text[key] = text[key].replace(old, new, 1)

once('h', '\tuint32_t nova_draws_since_submit = 0;\n', '''	uint32_t nova_draws_since_submit = 0;
	// Nova 0998: uploads recorded ahead of the current command buffer.
	vk::CommandBuffer NovaPreCommand();
	// Guest pages CPU-written (write faults/invalidations from any thread) since this command
	// buffer began: an upload of those bytes must stay in recording order.
	void NovaNoteCpuWrite(uint64_t address, uint64_t size) {
		std::lock_guard lock(nova_cpu_mutex);
		if (size == 0) return;
		if (size > (uint64_t {64} << 20) || nova_cpu_pages.size() > 65536) { nova_cpu_overflow = true; return; }
		for (uint64_t page = address >> 12; page <= (address + size - 1) >> 12; ++page) nova_cpu_pages.insert(page);
	}
	[[nodiscard]] bool NovaCpuWritten(uint64_t address, uint64_t size) {
		std::lock_guard lock(nova_cpu_mutex);
		if (nova_cpu_overflow) return true;
		if (nova_cpu_pages.empty() || size == 0) return false;
		const uint64_t first = address >> 12, last = (address + size - 1) >> 12;
		if (last - first + 1 > nova_cpu_pages.size()) {
			for (const auto page: nova_cpu_pages) if (page >= first && page <= last) return true;
			return false;
		}
		for (uint64_t page = first; page <= last; ++page) if (nova_cpu_pages.contains(page)) return true;
		return false;
	}
	void NovaResetCpuWrites() {
		std::lock_guard lock(nova_cpu_mutex);
		nova_cpu_pages.clear();
		nova_cpu_overflow = false;
	}
	vk::CommandBuffer            nova_pre = nullptr;
	std::mutex                   nova_cpu_mutex;
	std::unordered_set<uint64_t> nova_cpu_pages;
	bool                         nova_cpu_overflow = false;
''')
for header in ('#include <mutex>', '#include <unordered_set>'):
    if header not in text['h']:
        first = text['h'].index('#include')
        text['h'] = text['h'][:first] + header + '\n' + text['h'][first:]

once('c', '\t\tsubmit_info.commandBufferCount   = 1;\n\t\tsubmit_info.pCommandBuffers      = &buffer;\n', '''		const std::array<vk::CommandBuffer, 2> nova_buffers {nova_pre, buffer};
		if (nova_pre) {
			EXIT_NOT_IMPLEMENTED(nova_pre.end() != vk::Result::eSuccess);
		}
		submit_info.commandBufferCount   = nova_pre ? 2u : 1u;
		submit_info.pCommandBuffers      = nova_pre ? nova_buffers.data() : &buffer;
''')
once('c', '\tnova_draws_since_submit = 0;\n', '\tnova_draws_since_submit = 0;\n\tnova_pre = nullptr;\n')
once('c', 'void CommandScheduler::NovaMaybeEarlySubmit(bool rendering) {', '''vk::CommandBuffer CommandScheduler::NovaPreCommand() {
	if (nova_pre) return nova_pre;
	if (!Active() || m_command.IsInvalid()) return nullptr;
	auto command = m_command_pool.Commit();
	vk::CommandBufferBeginInfo info {};
	info.flags = vk::CommandBufferUsageFlagBits::eOneTimeSubmit;
	if (command.begin(&info) != vk::Result::eSuccess) return nullptr;
	nova_pre = command;
	return nova_pre;
}

void CommandScheduler::NovaMaybeEarlySubmit(bool rendering) {''')
once('c', '\tm_command.m_buffer = m_command_pool.Commit();\n\tm_command.Begin();\n',
     '\tNovaResetCpuWrites();\n\tm_command.m_buffer = m_command_pool.Commit();\n\tm_command.Begin();\n')
if '#include <array>' not in text['c']:
    text['c'] = text['c'].replace('#include <algorithm>\n', '#include <algorithm>\n#include <array>\n', 1)

once('s', '\tsize_t lru_id       = 0;\n', '\tsize_t lru_id       = 0;\n\t// Nova 0998: tick of the last write recorded in the main command stream (not an upload).\n\tuint64_t nova_main_write_tick = UINT64_MAX;\n')

once('b', '''	if (source) {
		auto& command = m_scheduler.Current();
		command.EndRendering();
		const auto native = command.Handle();
''', '''	if (source) {
		// Nova 0998: record the upload ahead of the current command buffer when that cannot
		// reorder it against other writes (see tools/ci/patch-0998-hoist-uploads.py).
		static const bool nova_hoist = [] {
			const char* value = std::getenv("NOVA_HOIST_UPLOADS");
			return !(value && value[0] == '0');
		}();
		vk::CommandBuffer native = nullptr;
		const auto nova_span = NovaRender::UploadDestinationRange(copies, buffer.Size());
		// Why an upload stays in order (reported so the next step targets the real cause).
		const bool nova_written = buffer.nova_main_write_tick == m_scheduler.CurrentTick();
		const bool nova_cpu = !nova_written &&
		    m_scheduler.NovaCpuWritten(buffer.CpuAddress() + nova_span.offset, nova_span.size);
		if (nova_hoist && !nova_written && !nova_cpu) {
			native = m_scheduler.NovaPreCommand();
		}
		struct HoistStats {
			uint64_t hoisted = 0, in_order = 0, buffer_written = 0, cpu_written = 0, bytes_in_order = 0;
			std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
		};
		static HoistStats hoist_stats;
		if (native) {
			hoist_stats.hoisted++;
		} else {
			hoist_stats.in_order++;
			hoist_stats.buffer_written += nova_written;
			hoist_stats.cpu_written += nova_cpu;
			hoist_stats.bytes_in_order += total_size;
		}
		if (const auto now = std::chrono::steady_clock::now(); now - hoist_stats.start >= std::chrono::seconds(5)) {
			std::fprintf(stderr, "NOVA_HOIST_UPLOADS: window_ms=%.0f hoisted=%llu in_order=%llu (buffer_written_this_cb=%llu cpu_written_this_cb=%llu in_order_kib=%llu)\\n",
			             std::chrono::duration<double, std::milli>(now - hoist_stats.start).count(),
			             (unsigned long long)hoist_stats.hoisted, (unsigned long long)hoist_stats.in_order,
			             (unsigned long long)hoist_stats.buffer_written, (unsigned long long)hoist_stats.cpu_written,
			             (unsigned long long)(hoist_stats.bytes_in_order / 1024));
			hoist_stats = {};
			hoist_stats.start = now;
		}
		if (!native) {
			auto& command = m_scheduler.Current();
			command.EndRendering();
			native = command.Handle();
		}
''')
once('b', '\t\treturn SynchronizeBufferFromImage(buffer, vaddr, size);',
     '\t\tbuffer.nova_main_write_tick = m_scheduler.CurrentTick();\n\t\treturn SynchronizeBufferFromImage(buffer, vaddr, size);')
once('b', '\tnew_buffer.CopyFrom(m_scheduler.Current(), overlap, 0,',
     '\tnew_buffer.nova_main_write_tick = m_scheduler.CurrentTick();\n\tnew_buffer.CopyFrom(m_scheduler.Current(), overlap, 0,')
once('b', '\tdst->CopyFrom(command, *src, src_offset, dst_offset, size);',
     '\tdst->nova_main_write_tick = m_scheduler.CurrentTick();\n\tdst->CopyFrom(command, *src, src_offset, dst_offset, size);')
once('b', '''void BufferCache::InvalidateMemory(uint64_t vaddr, uint64_t size, ReadbackContext context) {
	if (!GuestRange {vaddr, size}.Valid()) {
		EXIT("BufferCache: invalid memory-invalidation range\\n");
	}
''', '''void BufferCache::InvalidateMemory(uint64_t vaddr, uint64_t size, ReadbackContext context) {
	if (!GuestRange {vaddr, size}.Valid()) {
		EXIT("BufferCache: invalid memory-invalidation range\\n");
	}
	m_scheduler.NovaNoteCpuWrite(vaddr, size);
''')
once('b', '\t\tm_scheduler.EndRendering();\n\t\tconst auto command = m_scheduler.Current().Handle();\n',
     '\t\tbuffer.nova_main_write_tick = m_scheduler.CurrentTick();\n\t\tm_scheduler.EndRendering();\n\t\tconst auto command = m_scheduler.Current().Handle();\n')
once('b', '\tif (is_written) {\n', '\tif (is_written) {\n\t\tbuffer.nova_main_write_tick = m_scheduler.CurrentTick();\n')
for header in ('#include <chrono>', '#include <cstdio>', '#include <cstdlib>'):
    if header not in text['b']:
        first = text['b'].index('#include')
        text['b'] = text['b'][:first] + header + '\n' + text['b'][first:]

for k, p in files.items():
    p.write_text(text[k])
print('0998: buffer uploads recorded ahead of the current command buffer when order-safe (NOVA_HOIST_UPLOADS)')
