#!/usr/bin/env python3
"""0.9.31: translate guest pthread objects and timespecs in the timed sync entry points.

Luna (PPSA36257, Unreal) spends most of its CPU time in PthreadCondTimedwaitAbs and
PthreadStaticObjects::CreateObject. Unreal allocates its FEvent/FCriticalSection objects in
arenas above 2^39 (translated guest VA). The untimed entry points (Lock/Unlock/Wait/Signal...)
already translate their object pointer with NOVA_XLAT_PTR, but the timed ones did not:

  PthreadCondTimedwaitAbs (POSIX pthread_cond_timedwait)  cond, mutex, abstime
  PthreadMutexTimedlock                                    mutex
  PthreadRwlockTimedrdlock / PthreadRwlockTimedwrlock      rwlock
  pthread_mutex_timedlock                                  abstime
  KernelNanosleep                                          rqtp, rmtp
  KernelClockGettime / KernelClockGetres                   tp (Unreal's FPlatformTime)
  sem_timedwait / sem_getvalue (semaphore.cpp)             abstime, value

Every access to such an object from native code was a SIGSEGV emulated one instruction at a
time by NovaFEX (counted as `hostemu`), several per call, on the hottest synchronization path
of the game. The object storage, its contents and the guest ABI are unchanged: the guest still
owns the same memory; only the host now reads and writes it through its translated view.
Low (< 2^39) and null pointers are left untouched by NOVA_XLAT_PTR, so titles without guest VA
translation (Dead Cells) run the identical code path as before.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])
pthread = root / "src/kernel/pthread.cpp"
sema = root / "src/kernel/semaphore.cpp"
s = pthread.read_text()

if "NOVA_0931_PTHREAD_XLAT" in s:
    raise SystemExit("NOVA_0931_PTHREAD: already applied")
if s.count("#define NOVA_XLAT_PTR(p)") != 2:
    raise SystemExit("NOVA_0931_PTHREAD: NOVA_XLAT_PTR definition changed; refusing edit")


def insert_after_signature(src, signature, lines):
    if src.count(signature) != 1:
        raise SystemExit(f"NOVA_0931_PTHREAD: expected one '{signature[:70]}'")
    at = src.index(signature)
    brace = src.index("{", at + len(signature) - 1)
    body = "".join(f"\n\t{line}" for line in lines)
    return src[: brace + 1] + body + src[brace + 1 :]


tag = "/* NOVA_0931_PTHREAD_XLAT: translated guest VA view */"
s = insert_after_signature(
    s,
    "int KYTY_SYSV_ABI PthreadCondTimedwaitAbs(PthreadCond* cond, PthreadMutex* mutex,\n"
    "                                          const KernelTimespec* abstime) {",
    [tag, "NOVA_XLAT_PTR(cond);", "NOVA_XLAT_PTR(mutex);", "NOVA_XLAT_PTR(abstime);"],
)
s = insert_after_signature(
    s, "int KYTY_SYSV_ABI PthreadMutexTimedlock(PthreadMutex* mutex, KernelUseconds usec) {", [tag, "NOVA_XLAT_PTR(mutex);"]
)
s = insert_after_signature(
    s, "int KYTY_SYSV_ABI PthreadRwlockTimedrdlock(PthreadRwlock* rwlock, KernelUseconds usec) {", [tag, "NOVA_XLAT_PTR(rwlock);"]
)
s = insert_after_signature(
    s, "int KYTY_SYSV_ABI PthreadRwlockTimedwrlock(PthreadRwlock* rwlock, KernelUseconds usec) {", [tag, "NOVA_XLAT_PTR(rwlock);"]
)
s = insert_after_signature(
    s,
    "int KYTY_SYSV_ABI pthread_mutex_timedlock(LibKernel::PthreadMutex*         mutex,\n"
    "                                          const LibKernel::KernelTimespec* abstime) {",
    [tag, "NOVA_XLAT_PTR(abstime);"],
)
s = insert_after_signature(
    s,
    "int KYTY_SYSV_ABI KernelNanosleep(const KernelTimespec* rqtp, KernelTimespec* rmtp) {",
    [tag, "NOVA_XLAT_PTR(rqtp);", "NOVA_XLAT_PTR(rmtp);"],
)
s = insert_after_signature(
    s, "int KYTY_SYSV_ABI KernelClockGetres(KernelClockid clock_id, KernelTimespec* tp) {", [tag, "NOVA_XLAT_PTR(tp);"]
)
s = insert_after_signature(
    s, "int KYTY_SYSV_ABI KernelClockGettime(KernelClockid clock_id, KernelTimespec* tp) {", [tag, "NOVA_XLAT_PTR(tp);"]
)
pthread.write_text(s)

t = sema.read_text()
if "NOVA_0931_PTHREAD_XLAT" in t:
    raise SystemExit("NOVA_0931_PTHREAD: semaphore already applied")
# The 16-byte timespec and the int are naturally aligned, so they never straddle a 1 GiB slot.
helper = (
    "\n#if defined(KYTY_NOVA_FEX)\n"
    "/* NOVA_0931_PTHREAD_XLAT: translated guest VA view */\n"
    "template <typename T>\n"
    "static T* NovaSemXlat(T* p) {\n"
    "\treturn (p != nullptr && reinterpret_cast<uint64_t>(p) >= NovaGuest::kLow)\n"
    "\t           ? static_cast<T*>(NovaGuest::Host(reinterpret_cast<uint64_t>(p)))\n"
    "\t           : p;\n"
    "}\n"
    "#else\n"
    "template <typename T>\n"
    "static T* NovaSemXlat(T* p) {\n"
    "\treturn p;\n"
    "}\n"
    "#endif\n"
)
anchor = "static bool AbsTimespecToMicros(const LibKernel::KernelTimespec* abstime, uint32_t* micros) {"
if t.count(anchor) != 1:
    raise SystemExit("NOVA_0931_PTHREAD: AbsTimespecToMicros anchor changed")
t = t.replace(anchor, helper + anchor + "\n\tabstime = NovaSemXlat(abstime);", 1)
getvalue = "int KYTY_SYSV_ABI sem_getvalue(void* sem, int* value) {"
if t.count(getvalue) != 1:
    raise SystemExit("NOVA_0931_PTHREAD: sem_getvalue anchor changed")
t = t.replace(getvalue, getvalue + "\n\tvalue = NovaSemXlat(value);", 1)
if "#include \"common/novaFex.h\"" not in t:
    first = t.index("#include")
    t = t[:first] + "#include \"common/novaFex.h\"\n" + t[first:]
sema.write_text(t)
print("NOVA_0931_PTHREAD: timed cond/mutex/rwlock, nanosleep and semaphore guest pointers translated")
