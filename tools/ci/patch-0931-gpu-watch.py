#!/usr/bin/env python3
"""0.9.31: Rate-limit repeated GPU watchpoint output without changing guest writes."""
from pathlib import Path
import re
import sys

path = Path(sys.argv[1]) / "src/graphics/guest_gpu/graphicsRun.cpp"
source = path.read_text()
# Watchpoint printing can produce thousands of synchronous Android stderr writes
# for one unfulfilled GPU event. Preserve the first 16 observations and periodic
# samples; do not modify the guest memory, event ordering, or wait result.
pattern = r'(\s*)std::fprintf\(stderr,\s*"NOVA_GPU_WATCH:[\s\S]*?\);'
matches = list(re.finditer(pattern, source))
if len(matches) != 1:
    raise SystemExit(f"NOVA_0931: expected one GPU watch print, found {len(matches)}")
m = matches[0]
replacement = (
    m.group(1) + "static std::atomic<uint64_t> nova_watch_print_count {0};\n"
    + m.group(1) + "const auto nova_watch_n = nova_watch_print_count.fetch_add(1, std::memory_order_relaxed);\n"
    + m.group(1) + "if (nova_watch_n < 16 || (nova_watch_n & 4095u) == 0u) {\n"
    + m.group(0).lstrip() + "\n" + m.group(1) + "}"
)
source = source[:m.start()] + replacement + source[m.end():]
path.write_text(source)
print("NOVA_0931: GPU watch logging bounded; GPU writes and waits unchanged")
