#!/usr/bin/env python3
"""0.9.31 regression test: WAIT_REG_MEM compare semantics and truthful wait diagnostics.

* Compiles the production TestWaitRegMemValue from the patched graphicsRun.cpp and checks
  every compare function (0..6) against a reference, for 32- and 64-bit labels, including
  the Luna case from the 0.9.30 log: func=3 (equal), ref=0x1, mask=0xffffffff. The stale
  value 0xe7010002 must not satisfy it; the producer's later E-write of 0x1 must.
* Checks that the release build no longer claims "no GPU write ... in the last 0 writes"
  without saying the write history is disabled, that waits report the label width, and that
  watched writes report whether they satisfy the pending wait.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

src = (Path(sys.argv[1]) / "src/graphics/guest_gpu/graphicsRun.cpp").read_text()
fail = []
for marker in ("NOVA_0931_WAIT_DIAG", "GPU write history is disabled in this build", "bits=%u func=%u", "satisfies=%d"):
    if marker not in src:
        fail.append(f"missing {marker!r}")
if src.count("void CommandProcessor::WaitRegMem(") != 1 or "SuspendPm4();\n\t}\n}" not in src:
    fail.append("WaitRegMem no longer suspends unsatisfied waits")

m = re.search(r"bool TestWaitRegMemValue\(uint64_t value, uint64_t ref, uint64_t mask, uint32_t func\) \{[\s\S]*?\n\}\n", src)
if m is None:
    fail.append("TestWaitRegMemValue not found")
else:
    body = m.group(0).replace('EXIT("unknown wait compare function: %" PRIu32 "\\n", func);', "std::abort();")
    harness = "#include <cstdint>\n#include <cstdio>\n#include <cstdlib>\n" + body + r"""
static bool Ref(uint64_t v, uint64_t r, uint64_t m, uint32_t f) {
    const uint64_t x = v & m;
    switch (f) { case 0: return true; case 1: return x < r; case 2: return x <= r; case 3: return x == r;
                 case 4: return x != r; case 5: return x >= r; default: return x > r; }
}
int main() {
    int bad = 0;
    const uint64_t vals[] = {0, 1, 2, 0xe7010002ull, 0xffffffffull, 0x100000001ull, ~0ull, 0x8000000000000000ull};
    const uint64_t masks[] = {0xffffffffull, ~0ull, 0xffull, 0};
    for (uint32_t f = 0; f <= 6; f++) for (uint64_t v : vals) for (uint64_t r : vals) for (uint64_t mk : masks)
        if (TestWaitRegMemValue(v, r, mk, f) != Ref(v, r, mk, f)) { bad++; }
    // Luna PPSA36257, 0.9.30: queue(event 32) func=3 ref=0x1 mask=0xffffffff
    if (TestWaitRegMemValue(0xe7010002ull, 1, 0xffffffffull, 3)) bad++;
    if (!TestWaitRegMemValue(1, 1, 0xffffffffull, 3)) bad++;
    std::printf(bad ? "COMPARE FAIL %d\n" : "COMPARE PASS\n", bad);
    return bad != 0;
}
"""
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / "t.cpp"
        c.write_text(harness)
        exe = Path(tmp) / "t"
        subprocess.run(["c++", "-std=c++20", "-O1", "-Wall", "-Werror", str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            fail.append("compare semantics")
if fail:
    for f in fail:
        print("GPU_WAIT_DIAG_TEST: FAIL", f)
    sys.exit(1)
print("GPU_WAIT_DIAG_TEST: PASS (7 compare functions x 32/64-bit values; Luna func=3 case; truthful release diagnostics)")
