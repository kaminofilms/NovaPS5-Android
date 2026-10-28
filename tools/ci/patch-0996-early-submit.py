#!/usr/bin/env python3
"""Keep the GPU busy while the CPU is still recording a frame (early submission).

Wonder Boy gameplay (0.9.106-0.9.110): ~39-43 ms of GPU work and ~25 ms of Kyty draw recording per
frame, yet frames take ~64-70 ms and the GPU is only ~57-65% busy. Kyty submits only ~4 times per
frame (at guest submit/flip boundaries), so the GPU waits for most of a frame's recording before it
starts: the two halves run one after the other instead of overlapping.

At the start of a draw, outside any render pass, if at least NOVA_EARLY_SUBMIT_DRAWS draws
(default 64; 0 = off) were recorded since the last submission and at least 1 ms has passed, the
recorded work is submitted (CommandScheduler::Flush) and recording continues in a new command
buffer. Same queue, same order, same synchronisation: Kyty already submits at arbitrary points
(stream-buffer wraps, readbacks) with the CommandBuffer wrapper staying valid. No render pass is
split (only when the previous pass already ended).

  NOVA_EARLY_SUBMIT: window_ms=5000 early_submits=310 draws=1600 threshold=64
"""
from pathlib import Path
import sys

r = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer'
h, c, d = r / 'commandScheduler.h', r / 'commandScheduler.cpp', r / 'renderDraw.cpp'
hs, cs, ds = h.read_text(), c.read_text(), d.read_text()

def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f'0996: {what} anchor changed ({text.count(old)}); no source written')
    return text.replace(old, new, 1)

hs = once(hs, '\t[[nodiscard]] bool             IsFree(uint64_t tick);\n',
          '\t[[nodiscard]] bool             IsFree(uint64_t tick);\n'
          '\t// Nova 0996: draws recorded since the last submission, and when that submission happened.\n'
          '\tuint32_t nova_draws_since_submit = 0;\n'
          '\tstd::chrono::steady_clock::time_point nova_last_submit = std::chrono::steady_clock::now();\n'
          '\tvoid NovaMaybeEarlySubmit(bool rendering);\n', 'scheduler header')
if '#include <chrono>' not in hs:
    hs = hs.replace('#include <condition_variable>\n', '#include <chrono>\n#include <condition_variable>\n', 1)

cs = once(cs, '\tm_command.m_buffer = nullptr;\n\treturn tick;\n}\n',
          '\tm_command.m_buffer = nullptr;\n\tnova_draws_since_submit = 0;\n\tnova_last_submit = std::chrono::steady_clock::now();\n\treturn tick;\n}\n', 'Submit tail')
cs = cs.rstrip()
if not cs.endswith('} // namespace Libs::Graphics'):
    raise SystemExit('0996: commandScheduler.cpp tail changed; no source written')
cs = cs[: -len('} // namespace Libs::Graphics')] + r'''void CommandScheduler::NovaMaybeEarlySubmit(bool rendering) {
	static const uint32_t threshold = [] {
		const char* value = std::getenv("NOVA_EARLY_SUBMIT_DRAWS");
		const long  draws = value ? std::strtol(value, nullptr, 10) : 64;
		return draws <= 0 ? 0u : uint32_t(std::min<long>(draws, 100000));
	}();
	struct Stats {
		uint64_t early = 0, draws = 0;
		std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
	};
	static thread_local Stats stats;
	++nova_draws_since_submit;
	++stats.draws;
	const auto now = std::chrono::steady_clock::now();
	if (now - stats.start >= std::chrono::seconds(5)) {
		std::fprintf(stderr, "NOVA_EARLY_SUBMIT: window_ms=%.0f early_submits=%llu draws=%llu threshold=%u\n",
		             std::chrono::duration<double, std::milli>(now - stats.start).count(), (unsigned long long)stats.early,
		             (unsigned long long)stats.draws, threshold);
		stats = {};
		stats.start = now;
	}
	if (threshold == 0 || rendering || nova_draws_since_submit < threshold || !Active() || m_command.IsInvalid() ||
	    now - nova_last_submit < std::chrono::milliseconds(1)) {
		return;
	}
	++stats.early;
	Flush();
}

} // namespace Libs::Graphics
'''
for header in ('#include <cstdlib>', '#include <algorithm>', '#include <cstdio>'):
    if header not in cs:
        cs = cs.replace('#include <chrono>\n', '#include <chrono>\n' + header + '\n', 1)

ds = once(ds, '''	                                     bool primitive_restart_enable) {
	auto& ucfg = buffer.GetUserConfig();
''', '''	                                     bool primitive_restart_enable) {
	// Nova 0996: submit already-recorded work between passes so the GPU starts while we record.
	m_context.GetCommandScheduler().NovaMaybeEarlySubmit(buffer.NovaRendering());
	auto& ucfg = buffer.GetUserConfig();
''', 'ExecutePreparedDraw head')
h.write_text(hs)
c.write_text(cs)
d.write_text(ds)
print('0996: early submission between passes after NOVA_EARLY_SUBMIT_DRAWS draws (NOVA_EARLY_SUBMIT)')
