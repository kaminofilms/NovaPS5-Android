# NovaPS5 0.9.36 watchpoint handoff

Continue implementation on `fix/novaps5-0936-luna-watchpoint` in
`kaminofilms/NovaPS5-Android`. Protected 0.9.35 baseline is
`26fae46b7e1b6e81b408b8385006a059bffe9c8e`; do not modify or merge it.
The owner authorized implementation, CI validation and one signed APK once
applicable validation gates pass. Architecture stays native Android ARM64:
Kyty in process, embedded NovaFEX at FEX commit
`14c92681f4d62cf84d901460e0358de09c8847a7`. No alternate backend.

## Actual changes

`tools/ci/patch-0936-fex-watchpoint.py` instruments the real
`Arm64JITCore::DEF_OP(StoreMem)` inside staged FEX `MemoryOps.cpp`.
`tools/ci/build-android-novafex.sh` copies the watchpoint declaration header into
FEXCore includes and runs that source patch after the existing Android patches.
The normal scalar `GenerateMemOperand` and native store cases remain intact;
StoreMemTSO, SIMD and SVE stores are unchanged.

The JIT performs an acquire load of the nonempty-registry flag and branches
around the callback when disabled. Active stores save FPCR/FPSR before FEX
spilling, then use PushDynamicRegs(TMP1), SpillStaticRegs(TMP1), prepare args,
call BeforeStore, FillStaticRegs(), PopDynamicRegs(), restore exact FPCR/FPSR.
The recovered assembly wrapper was deliberately not combined with this strategy:
it saves Q state, not full SVE state, and cannot recover x0/x1 overwritten before
entry. Verify the complete preservation contract using actual generated code.

The source patch's `MaterializeExactStoreAddress` handles no offset, inline
byte offsets, SXTX/UXTW/SXTW and valid scales using reserved temporaries. It
captures source payload directly from GetZeroableReg, including zero, before
assigning call arguments. Guest RIP comes from FEX GuestOpcode metadata via
InsertGuestRIPMove (relocation aware), never host-PC inference.

`native/novafex/watchpoint/` contains an adapted verified-object registry,
1024-slot bounded MPSC capture ring and bridge. Object publication is release /
acquire, slots are immutable, no speculative guest-memory dereference occurs.
The record includes sequence, object, field bitmask, exact source payload,
width, guest RIP, guest address and HOST thread ID. Thread ID is not falsely
labeled a guest scheduler ID. Records are always ATTEMPTED; completion is not
observed, even if the subsequent native store succeeds.

Addresses entering StoreMem may already be translated by NovaAddressTranslation.
The registry retains each verified guest field and its backing host address,
including noncontiguous backing mappings; the callback reconstructs a guest
address only from an overlapping verified field mapping. Never treat StoreMem's
base as unconditionally a guest address.

`NovaFex::RegisterVerifiedCheckpointObject(base)` is an explicit API. Caller must
prove the object identity and pin mappings/lifetime. No production Luna caller
has been established. `ReadWatchpointTrace` provides bounded consumption. ReportGuestFault now drains
at most 1024 records as NOVA_STORE_INTENT lines with completion=unobserved.

## Tests and CI

Host registry/ring tests: tests/test_0936_watchpoint.cpp, compiled with
ASan+UBSan. They cover disabled registry, invalid bases, partial/overlapping
stores, translated and separated field mappings, exact payload/RIP, concurrent
capture, full-ring drops and attempted-only semantics. These passed locally.
Local LeakSanitizer cannot inspect processes under this environment's tracing;
only leak detection was disabled for the local rerun. CI runs the full sanitizer
command without this override.

The dedicated workflow `.github/workflows/novafex-watchpoint.yml` builds actual
Android FEX+bridge+ARM64 assembly and then executes the static bionic binary on
ubuntu-24.04-arm. Original regression configuration runs first. A separate
FEX_TSOENABLED=0 process specifically exercises scalar StoreMem with new guest
machine-code tests in test/watchpoint.inc. This test-only override does not
change production TSO defaults or StoreMemTSO. Do not conflate an ARM Linux CI
runner with the owner's Snapdragon/Android device.

First validation run:
https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38834453560

Do not assume this run passed: inspect final jobs and logs. Repair actual
compilation/test errors. Compilation succeeded after adding the architectural FPSR encoding missing from
the pinned emitter enum. Run 38834871850 built Android FEX and the bridge at
29153a024437634bb416b1394186f0f1c2fee3cb. Its runtime result must still be checked.
The initial source commit is
`ecf66954892eabe63c80b24cd6d0b765d5e2fb2f`.

## Blocking gaps before a useful device APK

1. Identify a trustworthy, early Luna CheckpointName object lifecycle point.
   Neither the baseline source nor recovered artifacts establish it. The safe
   registry is intentionally empty until explicitly registered. Do not guess
   from float 100.0, scan arbitrary memory, or arm after corruption and claim the
   first writer was caught. Bind registration and any mapping lifetime policy to
   verified object identity. Immutable slots must not outlive/reclassify reused
   allocations without a proven lifetime policy.
2. Confirm ReportGuestFault is reached on the actual Luna failure. It now emits
   bounded NOVA_STORE_INTENT records. A full ring drops later records until drained;
   select an earlier safe drain point if real traces demonstrate this is needed.
3. Add actual AArch64 differential coverage for every effective-address mode,
   SIMD/FPCR/FPSR preservation and synchronous fault versus successful stores.
   The added scalar tests cover widths, zero source, RIP/payload/address, flags,
   a live XMM value, indexed/extended addresses and successful/faulting stores;
   do not claim the full requested validation matrix is complete.
4. Establish whether the offending writer is StoreMem. Production enables TSO;
   StoreMemTSO is intentionally outside this task. Do not silently disable TSO
   in the emulator or broaden instrumentation to forbidden paths.
5. Inspect NovaAddressTranslationPass::EffectiveAddress from
   patches/fex-android/0002-nova-guest-va.patch: it scales constant offsets, whereas
   GenerateMemOperand uses inline constants as byte offsets. This is an observed
   source discrepancy, not a proven Luna root cause. Reproduce with actual IR
   before changing unrelated translation semantics.

## Next device log investigation

Require a verified registration record and an attempted-store record that
overlaps +0x38 (pointer) or +0x40 (length). Locate guest module and offset from
captured RIP; inspect guest instruction bytes/disassembly and compare source
register value, access width and effective address with emitted AArch64. An
attempt record alone proves neither write completion nor corruption origin.
Correlate synchronous faults and prior/next records. Determine whether the
0x42c80000 payload is a legitimate float copied into an incorrect field, bad
guest structure metadata/layout, loader initialization or translation error.
No zeroing, fault suppression, fake save initialization or boot-success claims.

After gates pass, adapt existing `.github/workflows/android-native.yml` on this
isolated branch for versionName 0.9.36-android and a versionCode greater than 83.
Sign with tools/ci/novaps5-ci-test.keystore, alias novaps5dev, password android;
keep application ID and all user data. Verify signatures/certificate continuity,
ARM64 libraries, version, packaging and published artifact. Do not substitute
0.9.35 or a source archive for the requested APK. No 0.9.36 APK has been produced
by the initial integration commit.

Prior-context check: the earlier review explicitly left runtime object identity,
object address, constructor/property-population location and writer RIP unresolved.
The reported memcpy RIP 0x910003fc6 is a crash site, not a proven corrupting writer.
Do not arm a guessed object based on that RIP or on 0x42c80000.

## Final verified results from this turn

Tested source commit: `1251c9e80c615196ef507c8f71bd39abfaa6066a`.
Final successful validation run:
https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38835231143

Both jobs succeeded. CI passed full host ASan/UBSan tests, Android ARM64 FEX and
bridge compilation/linkage, the original FEX runtime regression configuration,
scalar widths/RIP/address/payload/zero/flags tests, live XMM preservation,
32 iterations of indexed/negative/signed/unsigned address differential tests,
and fresh-process successful store and original synchronous SIGSEGV tests.
The fault test confirmed one attempted record and no reported completion.

Runner features reported SVE256=0 and AFP=0. Do not claim target-device,
SVE256, AFP-specific or exhaustive machine-state validation. End-to-end guest
address tests are not direct coverage proof of every helper switch branch:
NovaAddressTranslation can materialize the EA before StoreMem. A dedicated
raw-IR/emitter differential matrix remains useful before broader deployment.
No target-device game execution, captured Luna corrupting writer or root-cause
fix was established. No Kyty/APK packaging/signing/update-install verification
was performed, because actual Luna early registration is still unimplemented.
No 0.9.36 APK/release exists from this work.

## Exact repository files changed

- .github/workflows/novafex-watchpoint.yml
- tools/ci/build-android-novafex.sh
- tools/ci/patch-0936-fex-watchpoint.py
- native/novafex/CMakeLists.txt
- native/novafex/novafex.h
- native/novafex/novafex.cpp
- native/novafex/watchpoint/NovaFexWatchpoint.safe.hpp
- native/novafex/watchpoint/NovaFexTraceRing.hpp
- native/novafex/watchpoint/NovaFexWatchpointBridge.cpp
- native/novafex/test/novafex_test.cpp
- native/novafex/test/watchpoint.inc
- tests/test_0936_watchpoint.cpp
- docs/HANDOFF-0.9.36-WATCHPOINT.md

The staged upstream file changed by the build patch is
FEXCore/Source/Interface/Core/JIT/MemoryOps.cpp. A source comparison verified
that removing the injected scalar hook/includes restores the upstream file
exactly. No StoreMemTSO, SIMD or SVE store implementation was changed.
