# Nova PS5 0.9.20: native guest-memory fast paths and DC ZVA

The 0.9.19 device test displayed the startup logo and recorded 545 game frames.
It later stopped at NOVA_FAULT_LOOP with instruction d50b7428, DC ZVA x8, on
guest address 0x8d00171000. The same run recorded over 22 million signal-emulated
host memory accesses. Hot sites included bionic libc and AgcCbReleaseMem.

The bridge now handles DC ZVA on translated guest memory: read the actual
DCZID_EL0 block size, align the original guest operand to that block, zero its
translated backing, preserve registers, then advance PC. It does not silently
skip the write, change memory protections, or suppress unrelated faults.

The Android Kyty target wraps memset/memcpy/memmove/memcmp at link time. Each
wrapper translates guest addresses once per slot-sized piece, then calls the
real libc primitive. Low host addresses keep the direct path; untranslated
addresses retain ordinary fault behavior. Move direction preserves overlapping
guest ranges, including crossings into separately backed 1 GiB slots. Original
guest return pointers and comparison ordering are preserved. The wrappers are
also linked into the ARM64 bridge test binary. They do not replace the system
libc or change shared libraries outside this target.

AgcCbReleaseMem constructs the identical eight-dword packet on the host stack,
then uses the existing slot-aware NovaGuest::Copy helper to write it to guest
command memory. Guest label addresses, return pointers, packet fields, GPU
submission order, barriers and interrupts are unchanged.

Host tests exercise the actual wrappers with noncontiguous backing, slot
crossings, both overlap directions, comparison ordering and return values.
ARM64 tests check bulk operations cause no host fault signals, and exercise
DC ZVA on a high guest address with adjacent sentinel blocks when permitted.
Existing mesh and compute regressions remain in the build.

These changes target observed CPU/signal overhead and the reported fault. They
do not establish a device FPS gain, sustained gameplay, or absence of another
fault. The compute-based mesh driver and shader compilation still have costs.
The driver and mesh-packing fixes from 0.9.19 remain in place.
