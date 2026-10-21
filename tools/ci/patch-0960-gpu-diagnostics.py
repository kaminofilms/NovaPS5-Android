#!/usr/bin/env python3
"""0.9.60: GPU diagnostics for frame-rate work (log only; no rendering change).

  * NOVA_GPU_TIME: real GPU execution time per 5 s, from Vulkan timestamps written at the
    start and end of every command buffer (union of intervals, so overlap is not counted
    twice). Shows whether the phone GPU is saturated.
  * NOVA_PASS_BREAK: where rendering passes are ended (file:line of the EndRendering call),
    counted only when a pass was actually open. Shows what splits the game's passes.

Timestamps use the raw command buffer handle, so they do not mark a command buffer as
having work (empty-flush skipping is unchanged). Any Vulkan failure disables the timer.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]); r = root / 'src/graphics/host_gpu/renderer'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0960_GPU_DIAG: anchor changed {path.name}: {old[:80]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


# ---- pass-break reasons ----
rh = r / 'render.h'
edit(rh, '#include <array>\n', '#include <array>\n#include <source_location>\n')
edit(rh, '''	void BeginRendering(const RenderState& state) const;
	void EndRendering() const;
 bool RasterScaleNeedsFlush''', '''	void BeginRendering(const RenderState& state) const;
	void EndRendering(std::source_location where = std::source_location::current()) const;
 bool RasterScaleNeedsFlush''')
cx = r / 'context.cpp'
edit(cx, '''void CommandBuffer::EndRendering() const {
	if (!m_rendering) {
		return;
	}
''', '''namespace {
// Nova 0.9.60: count where open passes are ended; report the top call sites every 5 s.
void NovaCountPassBreak(const std::source_location& where) {
	struct Site { const char* file; uint32_t line; uint64_t count; };
	static std::mutex              mutex;
	static std::array<Site, 64>    sites {};
	static uint64_t                other = 0, total = 0;
	static auto                    start = std::chrono::steady_clock::now();
	std::lock_guard lock(mutex);
	total++;
	bool found = false;
	for (auto& s: sites) {
		if (s.count == 0 || (s.line == where.line() && std::strcmp(s.file, where.file_name()) == 0)) {
			if (s.count == 0) { s.file = where.file_name(); s.line = where.line(); }
			s.count++;
			found = true;
			break;
		}
	}
	if (!found) other++;
	const auto now = std::chrono::steady_clock::now();
	if (now - start < std::chrono::seconds(5)) return;
	std::array<Site, 64> sorted = sites;
	std::sort(sorted.begin(), sorted.end(), [](const Site& a, const Site& b) { return a.count > b.count; });
	char line[1200];
	int  at = std::snprintf(line, sizeof(line), "NOVA_PASS_BREAK: window_ms=%.0f passes_ended=%llu",
	                        std::chrono::duration<double, std::milli>(now - start).count(),
	                        static_cast<unsigned long long>(total));
	for (size_t i = 0; i < 10 && sorted[i].count != 0 && at < static_cast<int>(sizeof(line)) - 80; i++) {
		const char* base = std::strrchr(sorted[i].file, '/');
		at += std::snprintf(line + at, sizeof(line) - at, " %s:%u=%llu", base ? base + 1 : sorted[i].file,
		                    sorted[i].line, static_cast<unsigned long long>(sorted[i].count));
	}
	if (other) std::snprintf(line + at, sizeof(line) - at, " other=%llu", static_cast<unsigned long long>(other));
	std::fprintf(stderr, "%s\\n", line);
	sites = {};
	other = total = 0;
	start = now;
}
} // namespace

void CommandBuffer::EndRendering(std::source_location where) const {
	if (!m_rendering) {
		return;
	}
	NovaCountPassBreak(where);
''')
edit(cx, '#include <algorithm>\n', '#include <algorithm>\n#include <array>\n#include <mutex>\n#include <source_location>\n')

sh = r / 'commandScheduler.h'
edit(sh, '#include <condition_variable>\n', '#include <condition_variable>\n#include <source_location>\n')
edit(sh, '	void           EndRendering();\n',
     '	void           EndRendering(std::source_location where = std::source_location::current());\n')
sc = r / 'commandScheduler.cpp'
edit(sc, '''void CommandScheduler::EndRendering() {
	if (Active() && !m_command.IsInvalid()) {
		Current().EndRendering();
	}
}''', '''void CommandScheduler::EndRendering(std::source_location where) {
	if (Active() && !m_command.IsInvalid()) {
		Current().EndRendering(where);
	}
}''')

# ---- GPU time ----
edit(sh, '''	MasterSemaphore              m_master;
	RenderContext&               m_context;''', '''	// Nova 0.9.60: GPU execution time from command-buffer timestamps (NOVA_GPU_TIME).
	void NovaGpuTimeBegin();
	void NovaGpuTimeEnd();
	VkQueryPool m_nova_qp         = VK_NULL_HANDLE;
	bool        m_nova_qp_failed  = false;
	uint32_t    m_nova_qp_next    = 0;
	int64_t     m_nova_qp_slot    = -1;
	std::vector<uint8_t> m_nova_qp_written;
	double      m_nova_ns_per_tick = 1.0;
	uint64_t    m_nova_last_end    = 0;
	uint64_t    m_nova_busy_ticks  = 0;
	uint64_t    m_nova_measured    = 0;
	uint64_t    m_nova_unready     = 0;
	uint64_t    m_nova_window_start_ns = 0;

	MasterSemaphore              m_master;
	RenderContext&               m_context;''')
edit(sc, '''CommandBuffer& CommandScheduler::BeginCommand() {
	EXIT_IF(!m_command.IsInvalid());
	m_command.m_buffer = m_command_pool.Commit();
	m_command.Begin();
	m_dynamic_state.Invalidate();
	return m_command;
}''', '''CommandBuffer& CommandScheduler::BeginCommand() {
	EXIT_IF(!m_command.IsInvalid());
	m_command.m_buffer = m_command_pool.Commit();
	m_command.Begin();
	NovaGpuTimeBegin();
	m_dynamic_state.Invalidate();
	return m_command;
}

namespace {
constexpr uint32_t kNovaGpuTimeSlots = 256; // pairs of timestamps
uint64_t NovaSteadyNs() {
	return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
	                                 std::chrono::steady_clock::now().time_since_epoch())
	                                 .count());
}
} // namespace

void CommandScheduler::NovaGpuTimeBegin() {
	m_nova_qp_slot = -1;
	if (m_nova_qp_failed) return;
	const auto& d      = VULKAN_HPP_DEFAULT_DISPATCHER;
	const auto  device = static_cast<VkDevice>(m_graphics.device);
	if (m_nova_qp == VK_NULL_HANDLE) {
		const auto& limits = m_graphics.physical_device_properties.limits;
		if (!limits.timestampComputeAndGraphics || limits.timestampPeriod <= 0.0f || d.vkCreateQueryPool == nullptr) {
			m_nova_qp_failed = true;
			std::fprintf(stderr, "NOVA_GPU_TIME: unavailable (no graphics timestamps)\\n");
			return;
		}
		VkQueryPoolCreateInfo info {};
		info.sType      = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO;
		info.queryType  = VK_QUERY_TYPE_TIMESTAMP;
		info.queryCount = kNovaGpuTimeSlots * 2;
		if (d.vkCreateQueryPool(device, &info, nullptr, &m_nova_qp) != VK_SUCCESS) {
			m_nova_qp        = VK_NULL_HANDLE;
			m_nova_qp_failed = true;
			std::fprintf(stderr, "NOVA_GPU_TIME: unavailable (query pool)\\n");
			return;
		}
		m_nova_ns_per_tick     = static_cast<double>(limits.timestampPeriod);
		m_nova_qp_written.assign(kNovaGpuTimeSlots, 0);
		m_nova_window_start_ns = NovaSteadyNs();
	}
	const uint32_t slot = m_nova_qp_next++ % kNovaGpuTimeSlots;
	// Collect the result this slot held from kNovaGpuTimeSlots submits ago (in submission order).
	if (m_nova_qp_written[slot]) {
		// With availability: {begin, avail, end, avail}.
		uint64_t   both[4] {};
		const auto r2 = d.vkGetQueryPoolResults(device, m_nova_qp, slot * 2, 2, sizeof(both), both, 2 * sizeof(uint64_t),
		                                        VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WITH_AVAILABILITY_BIT);
		if (r2 == VK_SUCCESS && both[1] != 0 && both[3] != 0 && both[2] >= both[0]) {
			const uint64_t begin = std::max(both[0], m_nova_last_end);
			if (both[2] > begin) m_nova_busy_ticks += both[2] - begin;
			m_nova_last_end = std::max(m_nova_last_end, both[2]);
			m_nova_measured++;
		} else {
			m_nova_unready++;
		}
		m_nova_qp_written[slot] = 0;
	}
	const auto command = static_cast<VkCommandBuffer>(m_command.m_buffer);
	d.vkCmdResetQueryPool(command, m_nova_qp, slot * 2, 2);
	d.vkCmdWriteTimestamp(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, m_nova_qp, slot * 2);
	m_nova_qp_slot = slot;

	const uint64_t now = NovaSteadyNs();
	if (now - m_nova_window_start_ns >= 5000000000ull) {
		const double window_ms = static_cast<double>(now - m_nova_window_start_ns) / 1e6;
		const double busy_ms   = static_cast<double>(m_nova_busy_ticks) * m_nova_ns_per_tick / 1e6;
		std::fprintf(stderr,
		             "NOVA_GPU_TIME: scheduler=%p window_ms=%.0f gpu_busy_ms=%.1f gpu_busy_pct=%.0f command_buffers=%llu unready=%llu\\n",
		             static_cast<void*>(this), window_ms, busy_ms, 100.0 * busy_ms / window_ms,
		             static_cast<unsigned long long>(m_nova_measured), static_cast<unsigned long long>(m_nova_unready));
		m_nova_busy_ticks = m_nova_measured = m_nova_unready = 0;
		m_nova_window_start_ns = now;
	}
}

void CommandScheduler::NovaGpuTimeEnd() {
	if (m_nova_qp_slot < 0 || m_nova_qp == VK_NULL_HANDLE) return;
	m_command.EndRendering();
	VULKAN_HPP_DEFAULT_DISPATCHER.vkCmdWriteTimestamp(static_cast<VkCommandBuffer>(m_command.m_buffer),
	                                                  VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, m_nova_qp,
	                                                  static_cast<uint32_t>(m_nova_qp_slot) * 2 + 1);
	m_nova_qp_written[static_cast<size_t>(m_nova_qp_slot)] = 1;
	m_nova_qp_slot = -1;
}''')
edit(sc, '''	m_command.End();
	const auto buffer   = m_command.m_buffer;''', '''	NovaGpuTimeEnd();
	m_command.End();
	const auto buffer   = m_command.m_buffer;''')
s = changes[sc]
if '#include <chrono>' not in s:
    s = s.replace('#include <algorithm>\n', '#include <algorithm>\n#include <chrono>\n', 1)
changes[sc] = s

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0960_GPU_DIAG: NOVA_GPU_TIME (command-buffer timestamps) and NOVA_PASS_BREAK (pass end sites)')
