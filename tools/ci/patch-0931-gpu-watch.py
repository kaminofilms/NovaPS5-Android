#!/usr/bin/env python3
"""0.9.31: make the GPU wait diagnostics truthful in release builds (no behaviour change).

Replaces the first 0.9.31 draft of this script. That draft wrapped the NOVA_GPU_WATCH print
in a second rate limiter, but the print is already inside `if (n.fetch_add(1) < 32)`, so it
could never emit more than 32 lines and the draft removed no measurable overhead.

What is actually wrong: release builds remove the GPU write ring (NOVA_PERF, see
build-android-kyty.sh), so `g_nova_write_pos` stays 0 and every NOVA_GPU_WAIT report printed
"no GPU write near it in the last 0 writes". Device logs read that as proof that no GPU write
happened, while NOVA_GPU_WATCH later showed the producer's write (Luna: event 0 E-write = 0x1
to the label queue 32 waits on with func=3, i.e. `(value & mask) == ref`). This patch:
  * says plainly when the write ring is disabled, instead of claiming there were no writes;
  * prints the label width (32/64-bit) next to the compare, so `value` can be read correctly;
  * tags each later write to the watched label with whether it now satisfies the reported
    wait (`satisfies=1/0`), so a log shows directly whether the producer wrote the value the
    consumer compares against.
Guest memory, packet processing, wait results and ordering are unchanged.
"""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / "src/graphics/guest_gpu/graphicsRun.cpp"
s = path.read_text()
if "NOVA_0931_WAIT_DIAG" in s:
    raise SystemExit("NOVA_0931: GPU wait diagnostics already applied")


def replace_once(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit(f"NOVA_0931: anchor not unique/absent: {old[:70]!r}")
    s = s.replace(old, new, 1)


# 1) Remember the reported compare so later watched writes can be judged against it.
replace_once(
    "std::atomic<uint64_t> g_nova_watch_addr {0};\n",
    "std::atomic<uint64_t> g_nova_watch_addr {0};\n"
    "/* NOVA_0931_WAIT_DIAG */\n"
    "std::atomic<uint64_t> g_nova_watch_ref {0};\n"
    "std::atomic<uint64_t> g_nova_watch_mask {0};\n"
    "std::atomic<uint32_t> g_nova_watch_func {0};\n"
    "std::atomic<uint32_t> g_nova_watch_bytes {0};\n",
)
replace_once(
    'std::fprintf(stderr, "NOVA_GPU_WATCH: queue(event %u) %c-write 0x%016llx = 0x%llx\\n", queue, kind,\n'
    "\t\t\t             static_cast<unsigned long long>(a), static_cast<unsigned long long>(value));",
    "const auto nova_bytes = g_nova_watch_bytes.load(std::memory_order_relaxed);\n"
    "\t\t\tconst auto nova_label = nova_bytes == 4 ? (value & 0xffffffffull) : value;\n"
    "\t\t\tconst bool nova_exact = a == watch;\n"
    "\t\t\tstd::fprintf(stderr, \"NOVA_GPU_WATCH: queue(event %u) %c-write 0x%016llx = 0x%llx satisfies=%d\\n\", queue, kind,\n"
    "\t\t\t             static_cast<unsigned long long>(a), static_cast<unsigned long long>(value),\n"
    "\t\t\t             nova_exact ? (Libs::Graphics::TestWaitRegMemValue(nova_label, g_nova_watch_ref.load(std::memory_order_relaxed),\n"
    "\t\t\t                                               g_nova_watch_mask.load(std::memory_order_relaxed),\n"
    "\t\t\t                                               g_nova_watch_func.load(std::memory_order_relaxed)) ? 1 : 0)\n"
    "\t\t\t                        : -1);",
)
# TestWaitRegMemValue is defined later in the file; declare it before NovaNoteGpuWrite.
replace_once(
    "#if defined(KYTY_NOVA_FEX)\nnamespace {\nstd::atomic<uint64_t> g_nova_gpu_stall_since_ms {0};",
    "#if defined(KYTY_NOVA_FEX)\nnamespace Libs::Graphics {\nbool TestWaitRegMemValue(uint64_t value, uint64_t ref, uint64_t mask, uint32_t func);\n} // namespace Libs::Graphics\n"
    "namespace {\nstd::atomic<uint64_t> g_nova_gpu_stall_since_ms {0};",
)
# 2) Report width with the compare.
replace_once(
    '"NOVA_GPU_WAIT: queue(event %u) waits on 0x%016llx func=%u ref=0x%llx mask=0x%llx value=0x%llx for %llu ms\\n",\n'
    "\t\t\t             static_cast<unsigned>(m_interrupt_event_id), a64, func,",
    '"NOVA_GPU_WAIT: queue(event %u) waits on 0x%016llx bits=%u func=%u ref=0x%llx mask=0x%llx value=0x%llx for %llu ms\\n",\n'
    "\t\t\t             static_cast<unsigned>(m_interrupt_event_id), a64, static_cast<unsigned>(sizeof(T) * 8u), func,",
)
# 3) Truthful message when the write ring is compiled out.
replace_once(
    "\t\t\tif (shown == 0) {\n"
    '\t\t\t\tstd::fprintf(stderr, "NOVA_GPU_WAIT:   no GPU write near it in the last %u writes\\n",\n'
    "\t\t\t\t             std::min<uint32_t>(g_nova_write_pos, NOVA_WRITES));\n"
    "\t\t\t}",
    "\t\t\tif (shown == 0 && g_nova_write_pos == 0) {\n"
    '\t\t\t\tstd::fprintf(stderr, "NOVA_GPU_WAIT:   GPU write history is disabled in this build (NOVA_GPU_TRACE_WRITES=1 '
    'enables it); later writes to this label are reported as NOVA_GPU_WATCH\\n");\n'
    "\t\t\t} else if (shown == 0) {\n"
    '\t\t\t\tstd::fprintf(stderr, "NOVA_GPU_WAIT:   no GPU write near it in the last %u writes\\n",\n'
    "\t\t\t\t             std::min<uint32_t>(g_nova_write_pos, NOVA_WRITES));\n"
    "\t\t\t}",
)
replace_once(
    "\t\t\tg_nova_watch_addr.store(a64, std::memory_order_relaxed);",
    "\t\t\tg_nova_watch_ref.store(static_cast<uint64_t>(ref), std::memory_order_relaxed);\n"
    "\t\t\tg_nova_watch_mask.store(static_cast<uint64_t>(mask), std::memory_order_relaxed);\n"
    "\t\t\tg_nova_watch_func.store(func, std::memory_order_relaxed);\n"
    "\t\t\tg_nova_watch_bytes.store(static_cast<uint32_t>(sizeof(T)), std::memory_order_relaxed);\n"
    "\t\t\tg_nova_watch_addr.store(a64, std::memory_order_relaxed);",
)
path.write_text(s)
print("NOVA_0931: truthful GPU wait diagnostics (write-ring state, label width, watched write satisfies wait)")
