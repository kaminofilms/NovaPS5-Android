# Nova PS5 0.8.5 startup candidates

Base: `android-native`, native Android 0.8.4. Device traces: NX809J / SM8850 / Android 16, Luna Abyss PPSA36257 and ccleste PPSA59322.

## Implemented

- Route application-heap malloc/posix_memalign guest callbacks through FEX on ARM64, and return a FEX gate for the `scriptingGetMem` dlsym fallback.
- Prepare the HLE heap after libc module initialization and before executable entry, rather than rewriting allocators in the first malloc. Redirect recognized writable libc dispatch slots as well as exports. Preserve original targets in relocated trampolines so foreign-pointer frees cannot loop through the newly redirected slot.
- Cover libc exports for aligned/nothrow new and all delete forms already registered by NovaHeap.
- Select a page-alignment workaround solely from metadata title ID PPSA59322. Fixed mappings still require a non-null 16 KiB-aligned, non-wrapping range, valid physical backing and guest ownership; other titles retain the existing placement-alignment check.
- Include alignment/physical offset/protection in failed-map reports and sample semaphore names, timeout arguments and return codes to investigate EverForward's preload stall.

## Validation and limits

`python3 tests/test_native_startup.py <patched-kyty>` passes on Linux x86_64. It executes the actual relocated wrapper before/after slot redirection, verifies its original trampoline still targets the original allocator, rejects writes to read-only/unaligned slots, checks the ccleste placement predicate and checks FEX callback dispatch with a mock bridge. The regenerated patch applies to the workflow's exact upstream commit plus the preceding five patches; changed sources match after application. Existing APK/signature/FEX checks are retained.

These are source candidates, not confirmed title-boot fixes. No APK build or device test has been run. Full Android compile/link and real FEX callback integration still require CI and device validation. EverForward's remaining loading dependency is not identified from the supplied export; sampled diagnostics are intended to expose it, not manufacture completion. No AAA compatibility claim is made.

The oversized-reservation workaround still exists. This batch does not create a separate translated guest address space. A remaining direct map above the host ceiling needs further work rather than a false successful map.

Dead Cells' launcher profile is unchanged; regression risk from the shared callback corrections must still be checked on-device.

## Next device evidence

After an authorized 0.8.5 build, test Dead Cells first, then ccleste, Luna and EverForward. Export the in-app session log for each failure. Check the ccleste profile line, libc allocator/dispatch counts, failed mapping arguments and sampled semaphore results. Do not equate heartbeat FPS or "Game started" with a rendered menu.

## Sources inspected

- https://github.com/boykopovar/AnyPS5/tree/main/core/libs/prx/libkernel/DirectMemory
- https://github.com/boykopovar/AnyPS5/blob/main/core/libs/prx/libc/src/GuestHeap.cpp
- https://github.com/boykopovar/AnyPS5/blob/main/docs/dev/debt/libkernel.md
- https://github.com/sharpemu/sharpemu/blob/main/src/SharpEmu.Libs/Kernel/KernelMemoryCompatExports.cs
- https://github.com/Coder787-source/KytyPlus
- https://github.com/mattias800/prosper/tree/main/prosper/src/hle/libc
- https://github.com/KytyPS5/KytyPS5
- https://github.com/PS5Dev/PS5SDK
- https://github.com/john-tornblom/ps5-payload-sdk

Public Unity/Unreal forum and Reddit searches supplied leads but no exact verified remedy for these Android traces. The user-provided logs and inspected source, rather than forum compatibility claims, drive this patch.
