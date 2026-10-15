#!/usr/bin/env python3
"""0.9.31 regression test: timed pthread/semaphore entry points use translated guest views.

1. Source invariant over the compiled Kyty source: every exported pthread entry point that
   receives a guest mutex/cond/rwlock pointer and dereferences it (directly or through
   PthreadStaticObjects::CreateObject), or reads a guest timespec, translates that pointer
   with NOVA_XLAT_PTR before its first use. This fails for the 0.9.30 source, where
   PthreadCondTimedwaitAbs, PthreadMutexTimedlock and the timed rwlock locks did not.
2. Behaviour: the production NOVA_XLAT_PTR macro and the semaphore helper, extracted from the
   patched source, are compiled against a guest window above 2^39 that is PROT_NONE (any
   untranslated access faults and fails the test) and backed by separate native memory.
   Pointer slots of every sync type and timespecs (const and non-const) must resolve to the
   backing memory; null and low (< 2^39) pointers must be returned unchanged; translating a
   translated pointer again must be the identity (host views are below 2^39).
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
pthread = (root / "src/kernel/pthread.cpp").read_text()
sema = (root / "src/kernel/semaphore.cpp").read_text()
failures = []

sig = re.compile(r"\n(?:int|void\*|void|\w+) KYTY_SYSV_ABI (\w+)\(([^)]*)\)\s*\{")
checked = 0
for m in sig.finditer(pthread):
    name, args = m.group(1), m.group(2)
    body = pthread[m.end():].split("\n}\n")[0]
    params = re.findall(r"(?:Pthread(?:Mutex|Cond|Rwlock)|KernelTimespec)\*\s*(\w+)", args)
    for p in params:
        uses = [u for u in (
            body.find(f"CreateObject({p},"),
            body.find(f"*{p}"),
            body.find(f"{p}->"),
            body.find(f"NativeCondDeadlineFromAbs(cond_value->clock_id, {p}"),
        ) if u >= 0]
        if not uses:
            continue  # forwarding wrapper: the callee translates
        checked += 1
        x = body.find(f"NOVA_XLAT_PTR({p})")
        if x < 0 or x > min(uses):
            failures.append(f"{name}: '{p}' used before NOVA_XLAT_PTR")
for required in ("PthreadCondTimedwaitAbs", "PthreadMutexTimedlock", "PthreadRwlockTimedrdlock", "PthreadRwlockTimedwrlock"):
    if f"KYTY_SYSV_ABI {required}(" not in pthread:
        failures.append(f"{required} missing")
if checked < 20:
    failures.append(f"only {checked} guest object uses found; the audit no longer matches the source")
if "abstime = NovaSemXlat(abstime);" not in sema or "value = NovaSemXlat(value);" not in sema:
    failures.append("semaphore timespec/value translation missing")

# Extract the production macro (KYTY_NOVA_FEX branch) and the semaphore helper.
mm = re.search(r"#if defined\(KYTY_NOVA_FEX\)\n(?://[^\n]*\n)*(#define NOVA_XLAT_PTR\(p\)(?:[^\n]*\\\n)+[^\n]*\n)", pthread)
hm = re.search(r"#if defined\(KYTY_NOVA_FEX\)\n/\* NOVA_0931_PTHREAD_XLAT[^\n]*\n(template <typename T>\nstatic T\* NovaSemXlat[\s\S]*?\n})\n#else", sema)
if mm is None or hm is None:
    failures.append("could not extract NOVA_XLAT_PTR / NovaSemXlat from the patched source")
else:
    harness = r"""
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <sys/mman.h>
namespace NovaFex {
static uint64_t g_guest = 0, g_host = 0;
uint64_t TranslateGuestVA(uint64_t a) {
    const uint64_t slot = a & ~((uint64_t{1} << 30) - 1);
    return slot == g_guest ? g_host + (a - g_guest) : a;
}
}
namespace NovaGuest {
constexpr uint64_t kLow = uint64_t{1} << 39;
inline void* Host(uint64_t a) { return reinterpret_cast<void*>(static_cast<uintptr_t>(NovaFex::TranslateGuestVA(a))); }
}
struct KernelTimespec { int64_t tv_sec; int64_t tv_nsec; };
struct PthreadMutexPrivate; struct PthreadCondPrivate; struct PthreadRwlockPrivate;
using PthreadMutex = PthreadMutexPrivate*; using PthreadCond = PthreadCondPrivate*; using PthreadRwlock = PthreadRwlockPrivate*;
@MACRO@
@HELPER@
int main() {
    const uint64_t guest = 0x9040000000ull; // Luna's arena slot, above 2^39
    void* g = mmap(reinterpret_cast<void*>(guest), uint64_t{1} << 30, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
    void* h = mmap(nullptr, 1 << 20, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (g != reinterpret_cast<void*>(guest) || h == MAP_FAILED) { std::puts("SKIP-MAP"); return 3; }
    NovaFex::g_guest = guest; NovaFex::g_host = reinterpret_cast<uint64_t>(h);
    auto* host = static_cast<uint8_t*>(h);
    int fails = 0;
    auto expect = [&](bool ok, const char* what) { if (!ok) { std::printf("FAIL %s\n", what); fails++; } };
    // Guest object slots (8-byte pointers to the host objects) at Unreal-like offsets.
    const uint64_t off[3] = {0x40, 0x1000, 0xFFFF8};
    for (uint64_t o : off) {
        std::memcpy(host + o, &o, sizeof(o));
        PthreadMutex* m = reinterpret_cast<PthreadMutex*>(guest + o);
        PthreadCond* c = reinterpret_cast<PthreadCond*>(guest + o);
        PthreadRwlock* r = reinterpret_cast<PthreadRwlock*>(guest + o);
        NOVA_XLAT_PTR(m); NOVA_XLAT_PTR(c); NOVA_XLAT_PTR(r);
        expect(reinterpret_cast<uint8_t*>(m) == host + o && reinterpret_cast<uint64_t>(*m) == o, "mutex slot");
        expect(reinterpret_cast<uint8_t*>(c) == host + o && reinterpret_cast<uint64_t>(*c) == o, "cond slot");
        expect(reinterpret_cast<uint8_t*>(r) == host + o && reinterpret_cast<uint64_t>(*r) == o, "rwlock slot");
        PthreadMutex* again = m; NOVA_XLAT_PTR(again);
        expect(again == m, "idempotent");
    }
    KernelTimespec ts {1234, 567};
    std::memcpy(host + 0x2000, &ts, sizeof(ts));
    const KernelTimespec* abstime = reinterpret_cast<const KernelTimespec*>(guest + 0x2000);
    NOVA_XLAT_PTR(abstime);
    expect(abstime->tv_sec == 1234 && abstime->tv_nsec == 567, "const timespec");
    KernelTimespec* rmtp = reinterpret_cast<KernelTimespec*>(guest + 0x2000);
    NOVA_XLAT_PTR(rmtp);
    rmtp->tv_sec = 0; rmtp->tv_nsec = 0;
    expect(reinterpret_cast<KernelTimespec*>(host + 0x2000)->tv_sec == 0, "timespec write");
    const KernelTimespec* st = NovaSemXlat(reinterpret_cast<const KernelTimespec*>(guest + 0x2000));
    expect(st == reinterpret_cast<const KernelTimespec*>(host + 0x2000), "semaphore timespec");
    int* v = NovaSemXlat(reinterpret_cast<int*>(guest + 0x3000)); *v = 7;
    expect(*reinterpret_cast<int*>(host + 0x3000) == 7, "semaphore value");
    static PthreadMutex low_slot = nullptr;
    PthreadMutex* low = &low_slot; NOVA_XLAT_PTR(low);
    expect(low == &low_slot, "low unchanged");
    PthreadCond* null_cond = nullptr; NOVA_XLAT_PTR(null_cond);
    expect(null_cond == nullptr, "null unchanged");
    expect(NovaSemXlat(static_cast<int*>(nullptr)) == nullptr, "semaphore null");
    std::printf("%s\n", fails ? "XLAT FAIL" : "XLAT PASS");
    return fails ? 1 : 0;
}
""".replace("@MACRO@", mm.group(1)).replace("@HELPER@", hm.group(1))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "x.cpp"
        exe = Path(tmp) / "x"
        src.write_text(harness)
        cxx = "clang++" if subprocess.run(["which", "clang++"], capture_output=True).returncode == 0 else "g++"
        base = [cxx, "-std=c++20", "-O1", "-Wall", "-Werror", "-Wno-unused-function", str(src), "-o", str(exe)]
        # UBSan when the toolchain ships its runtime (CI does); plain build otherwise.
        if subprocess.run(base + ["-fsanitize=undefined", "-fno-sanitize-recover=all"], capture_output=True).returncode != 0:
            subprocess.run(base, check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode == 3:
            print("NOTE: host could not reserve a guest window above 2^39; behavioural part skipped")
        elif r.returncode != 0 or "XLAT PASS" not in r.stdout:
            failures.append(f"behaviour harness failed (exit {r.returncode}) {r.stderr[-400:]}")

if failures:
    for f in failures:
        print("PTHREAD_XLAT_TEST: FAIL", f)
    sys.exit(1)
print(f"PTHREAD_XLAT_TEST: PASS ({checked} guest sync/timespec uses translated before first access; PROT_NONE guest window)")
