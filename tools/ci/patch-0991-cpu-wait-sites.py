#!/usr/bin/env python3
"""Tasks 1-4 measurement: where does the CPU wait for the GPU?

Wonder Boy (Kyty, 0.9.105) runs ~15 FPS with the GPU busy only ~63% (NOVA_GPU_TIME): the CPU and
GPU take turns. Every host wait for GPU completion goes through CommandScheduler::Wait / Finish /
FlushAndWait (buffer readbacks, fault reconciliation, stream-buffer reuse, swapchain slots, EOP
drains). This records the caller of each wait that actually blocks (tick not yet complete) and
reports, every 5 s, blocked time per call site:

  NOVA_CPU_WAIT: window_ms=5000 site=bufferCache.cpp:177 calls=120 blocked_ms=840.2 max_ms=31.0

Measurement only: the waits themselves are unchanged (same tick, same order, same callbacks).
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer'
h = root / 'commandScheduler.h'
c = root / 'commandScheduler.cpp'
hs, cs = h.read_text(), c.read_text()

def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f'0991: {what} anchor changed ({text.count(old)}); no source written')
    return text.replace(old, new, 1)

hs = once(hs, '\tvoid           FlushAndWait();\n', '\tvoid           FlushAndWait(std::source_location where = std::source_location::current());\n', 'FlushAndWait decl')
hs = once(hs, '\tvoid           Finish();\n', '\tvoid           Finish(std::source_location where = std::source_location::current());\n', 'Finish decl')
hs = once(hs, '\tvoid                      Wait(uint64_t tick);\n',
          '\tvoid                      Wait(uint64_t tick, std::source_location where = std::source_location::current());\n'
          '\t// Nova 0991: m_master.Wait(tick) with blocked-time attribution to the caller.\n'
          '\tvoid                      NovaTimedWait(uint64_t tick, const std::source_location& where);\n', 'Wait decl')

cs = once(cs, 'void CommandScheduler::FlushAndWait() {\n\tconst auto tick = Submit();\n\tm_master.Wait(tick);\n',
          'void CommandScheduler::FlushAndWait(std::source_location where) {\n\tconst auto tick = Submit();\n\tNovaTimedWait(tick, where);\n', 'FlushAndWait body')
cs = once(cs, 'void CommandScheduler::Finish() {\n', 'void CommandScheduler::Finish(std::source_location where) {\n', 'Finish def')
a = cs.index('void CommandScheduler::Finish(std::source_location where) {\n')
b = cs.index('void CommandScheduler::Wait(uint64_t tick) {', a)
finish = cs[a:b]
finish = once(finish, '\tm_master.Wait(CurrentTick() - 1);\n\tBeginNext();\n\tPopPendingOperations();\n',
              '\tNovaTimedWait(CurrentTick() - 1, where);\n\tBeginNext();\n\tPopPendingOperations();\n', 'Finish wait')
cs = cs[:a] + finish + cs[b:]
a = cs.index('void CommandScheduler::Wait(uint64_t tick) {')
b = cs.index('bool CommandScheduler::PollCompletion(uint64_t tick) {', a)
wait = cs[a:b]
expected = '''void CommandScheduler::Wait(uint64_t tick) {
	EXIT_IF(tick > CurrentTick());
	if (tick == CurrentTick()) {
		CheckActive();
		// A stream-buffer wrap can wait while a draw is being prepared through a reference to
		// Current(). The wrapper stays stable while its pooled Vulkan buffer is retired. Deferred
		// resources are released only at the next GPU operation boundary.
		const auto submitted_tick = Submit();
		EXIT_IF(submitted_tick != tick);
		m_master.Wait(tick);
		BeginNext();
	} else {
		m_master.Wait(tick);
	}
}
'''
if wait.strip() != expected.strip():
    raise SystemExit('0991: CommandScheduler::Wait body changed; no source written')
new_wait = '''namespace {
struct NovaWaitSite {
	const char* file = nullptr;
	uint32_t    line = 0;
	uint64_t    calls = 0, ns = 0, max_ns = 0;
};
struct NovaWaitSites {
	std::mutex                              mutex;
	std::array<NovaWaitSite, 48>            sites {};
	uint64_t                                overflow = 0;
	std::chrono::steady_clock::time_point   start = std::chrono::steady_clock::now();
};
NovaWaitSites& NovaWaits() {
	static NovaWaitSites waits;
	return waits;
}
const char* NovaBaseName(const char* path) {
	const char* base = path;
	for (const char* p = path; p && *p; ++p) if (*p == '/' || *p == '\\\\') base = p + 1;
	return base;
}
void NovaRecordWait(const std::source_location& where, uint64_t ns) {
	auto& waits = NovaWaits();
	std::lock_guard lock(waits.mutex);
	bool found = false;
	for (auto& site: waits.sites) {
		if (site.file == nullptr || (site.file == where.file_name() && site.line == where.line())) {
			site.file = where.file_name();
			site.line = where.line();
			++site.calls;
			site.ns += ns;
			site.max_ns = std::max(site.max_ns, ns);
			found = true;
			break;
		}
	}
	if (!found) ++waits.overflow;
	const auto now = std::chrono::steady_clock::now();
	if (now - waits.start < std::chrono::seconds(5)) return;
	const auto window = std::chrono::duration<double, std::milli>(now - waits.start).count();
	for (auto& site: waits.sites) {
		if (site.calls == 0) continue;
		std::fprintf(stderr, "NOVA_CPU_WAIT: window_ms=%.0f site=%s:%u calls=%llu blocked_ms=%.1f max_ms=%.1f\\n", window,
		             NovaBaseName(site.file), site.line, static_cast<unsigned long long>(site.calls), double(site.ns) / 1e6,
		             double(site.max_ns) / 1e6);
		site.calls = site.ns = site.max_ns = 0;
	}
	if (waits.overflow) std::fprintf(stderr, "NOVA_CPU_WAIT: overflow=%llu\\n", static_cast<unsigned long long>(waits.overflow));
	waits.overflow = 0;
	waits.start = now;
}
} // namespace

void CommandScheduler::NovaTimedWait(uint64_t tick, const std::source_location& where) {
	if (m_master.IsFree(tick)) {
		m_master.Wait(tick);
		return;
	}
	const auto start = std::chrono::steady_clock::now();
	m_master.Wait(tick);
	NovaRecordWait(where, static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count()));
}

void CommandScheduler::Wait(uint64_t tick, std::source_location where) {
	EXIT_IF(tick > CurrentTick());
	if (tick == CurrentTick()) {
		CheckActive();
		// A stream-buffer wrap can wait while a draw is being prepared through a reference to
		// Current(). The wrapper stays stable while its pooled Vulkan buffer is retired. Deferred
		// resources are released only at the next GPU operation boundary.
		const auto submitted_tick = Submit();
		EXIT_IF(submitted_tick != tick);
		NovaTimedWait(tick, where);
		BeginNext();
	} else {
		NovaTimedWait(tick, where);
	}
}

'''
cs = cs[:a] + new_wait + cs[b:]
for header in ('#include <array>', '#include <mutex>', '#include <source_location>'):
    if header not in cs:
        cs = cs.replace('#include <algorithm>\n', '#include <algorithm>\n' + header + '\n', 1)
h.write_text(hs)
c.write_text(cs)
print('0991: blocking CommandScheduler waits are attributed to their call sites (NOVA_CPU_WAIT)')
