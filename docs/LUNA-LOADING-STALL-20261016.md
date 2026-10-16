# October 16 Luna loading stall and controller output

Device report: versionName 0.9.36-android, NX809J/SM8850/Android 16, PPSA36257.
The owner reports no crash, remaining on the loading screen at approximately
1 FPS. The supplied later heartbeats report 3.5 and 5.1 game FPS and increasing
game frames (1896 to 1973). These counters do not prove loading completes or
identify the visible scene.

The no-window message precedes a period of frozen presentation. That background
pause cannot by itself explain the earlier foreground loading-screen behavior.
Later frames progress again. The pasted stack tail begins after the main and
GPU-worker stacks, so it cannot locate their foreground bottleneck.

Thread 13616 is in KernelBatchMap2 -> RenderContext::UnmapMemory ->
GuestGpu::SendCommandSync. The real source removes a command from m_commands
before executing it and releasing the caller's semaphore. Therefore zero
commands pending does not prove that command has completed. UnmapMemory can
wait in CommandScheduler::Finish, WaitPriorityOperations, and cache invalidation.
Neither that stack nor a sleeping SuspendPoint caller establishes a deadlock.
No GPU wait/completion behavior is changed on this evidence.

The existing controller implementation fills the guest PadData pointer directly.
Repeated native field stores fault when this pointer requires guest translation.
The latest hostemu counts rise by roughly 1238 across 77 game frames (about 16
emulated accesses/frame), with PadReadState fields prominent. Counts alone are
not elapsed-time measurements and do not prove this is the 1 FPS bottleneck.

The controller patch builds the exact same zero-initialized 120-byte packet in
host-local storage, then publishes it through the existing GuestMemory::Copy.
This preserves buttons, axes, touch, sensors, connection state, timestamp,
reserved bytes and padding. Both PadReadState and each PadRead packet share
this initializer. The copy handles noncontiguous guest slots and still faults
on an inaccessible destination. Return values, handles, sampling and input
semantics are unchanged. This controller patch changes no renderer, JIT, guest layout or wait path.

Host tests compile the actual patched initializer, the original initializer for
differential comparison, the real PadData/ControllerState declarations, and
the production NovaGuest/GuestMemory copying helpers. They check 726 packet
comparisons across six input/connection variants and all 119 crossing alignments,
guard bytes, and bounded guest-destination translations. The normal negative
tests require SIGSEGV for protected and unmapped backing. ASan catches an
unmapped synthetic guest address in its shadow gap before the CPU store;
the sanitizer test requires that exact WRITE-107/address report rather than
accepting an arbitrary sanitizer failure. Both normal and ASan/UBSan runs pass.
Local LeakSanitizer is unsupported under tracing; only the local run sets
detect_leaks=0. CI keeps its normal sanitizer configuration.

Source-only CI runs the existing Android compilation and ARM64 regression jobs,
plus controller tests before Kyty compilation. A commit tagged [source-only]
deliberately skips APK packaging; it is not a released or device-tested fix.
At the start of this investigation the published APK was versionCode 85, source 56282b0.

Review of that release's boundary-load emitter also found avoidable JIT code
growth: sixteen translation sequences were emitted at each 128-bit load site,
including sites that only take the normal fast path. The source update emits
one byte-read loop using reserved TMP4 as the current guest address and EXT to
append each byte to the temporary vector. A non-flag-setting subtraction and
TBZ end the loop after sixteen reads. The allocated destination is still
committed only after success; per-byte translation, TSO barriers and fault RIP
semantics are retained. This reduces the number of emitted translation copies,
not the number of byte reads for an actual crossing. No device FPS improvement
is established by source-code size alone. Existing ARM64 differential and fault
tests gate this change along with the controller patch.

Initial evidence request (fulfilled below): export the complete boot-log text file, including the
entire latest foreground freeze report, beginning with MainThread and the GPU
worker stacks, its preceding heartbeats, shader/pipeline timing and guest thread
table. The pasted tail starts at tid 13580 and omits the relevant earlier
threads. Capture while the game window remains visible; preserve existing caches
and app data. Inspect the actual GPU-worker frame before changing synchronization
or calling the loading stall fixed. The CheckpointName writer is still unproven.

## Export received during this investigation

The owner supplied lunalog.txt (430839 bytes). Its startup records confirm the
profile armed at base 0x900000000 and registered SaveGameInstanceData object
0x81c0f019e0 with vtable 0x906f114f0. No NOVA_STORE_INTENT records appear. The
production TSO/SIMD exclusions still apply; absence of scalar records does not
establish that all writes were correct.

Heartbeats show sustained roughly 5.0–5.6 game FPS for several minutes before
the no-window pause, with guest frames increasing to 1799. The detailed native
stack dump is at the later 20-second background pause. Guest main thread 13534
is in pthread_cond_timedwait; RenderThread 13616 waits for synchronous unmap;
priority callback workers 13524/13529 are asleep awaiting operations. The GPU
worker's native trace (tid 13531) stops at the signal trampoline. There is no
foreground native-PC sample or timing breakdown establishing the loading-screen
bottleneck. The later heartbeat resumes frame progress to 1973.

DumpSelf now writes the interrupted native PC/LR/SP/FP directly from the kernel
ucontext before printing its ordinary backtrace, so signal-unwinder failure
cannot discard those addresses. They are explicitly native PCs and must not
be presented as guest RIPs. The handler does not modify registers, advance PC,
change waits or fabricate completion. This is bundled with the real controller
and JIT code-size changes, not claimed as a loading fix on its own.

Shader counts settle at VS45/PS86/CS59 for most of the steady 5-FPS interval
(CS60 appears later). Ongoing shader compilation alone therefore does not
explain that entire interval. After background/resume, RSS falls substantially
while sampled FPS remains around 5, so memory pressure alone is also unproven.
The known controller/JIT costs are corrected, but the dominant foreground
CPU/GPU wait or loading condition remains to be measured on the updated APK.

The source-only run 38899502199 at commit 21d9e1f6f3646599de055123a15b7c0711bc594b
passed all compilation/tests, with APK packaging intentionally skipped. It
confirmed compact-loop ARM64 behavior, exact RIP under all four negative cases,
and normal plus ASan/UBSan controller comparisons during Kyty compilation.
The subsequent full release candidate bundles these changes with native PC/LR
capture, uses versionCode 86, and runs all release gates again before packaging.

## Published batched update

Tested source: `52d1eac5b0c0360d1b96d48a795d84dae6c1b68d` on
`fix/novaps5-0936-luna-watchpoint`.
All jobs passed: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38900422917

APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-52d1eac/NovaPS5-0.9.36-android-arm64.apk

VersionName 0.9.36-android, versionCode 86, size 20,609,644 bytes.
APK SHA256: `8aa72c79e5822eec0d910bdf58cd70ab45c2a664f7c12219a19fa314a021c74d`.
Signing certificate SHA256:
`21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0`.
Application ID remains com.kaminofilms.novaps5. This certificate matches the
previous releases. Android packaging/ARM64/native library/16 KB alignment
verification and bundled driver checks all passed. Actual installation and
performance on NX809J remain device checks.

Full release CI reconfirmed both 726-case controller runs, including ASan/UBSan,
FEX compilation and ARM64 linkage, full native regressions in both TSO modes,
all 15 JIT crossing alignments/ZF/poison-neighbor comparisons, genuine fault
behavior with precise RIP under all four TSO/protection combinations, and
existing watchpoint/constructor coverage. No failing test was disabled.
The ARM runner has SVE256=0/AFP=0; it is not the target Android phone.

Changed paths since the preceding 0.9.36 handoff:
- tools/ci/patch-controller-output.py
- tests/test_controller_output.py
- tools/ci/build-android-kyty.sh
- tools/ci/patch-0936-cross-slot-load.py
- native/novafex/novafex.cpp
- .github/workflows/android-native.yml
- docs/LUNA-LOADING-STALL-20261016.md
- docs/HANDOFF-0.9.36-WATCHPOINT.md

## Prompt for the next device log

Continue NovaPS5 native Android on fix/novaps5-0936-luna-watchpoint. Read this
document and HANDOFF-0.9.36-WATCHPOINT.md before editing. The latest tested APK
is source 52d1eac5b0c0360d1b96d48a795d84dae6c1b68d, versionCode 86, CI run
38900422917. Preserve the protected 0.9.35 baseline, signing identity, application
ID, native Kyty/FEX backend, game saves, shader caches and imported drivers.

The last owner run no longer crashed but remained on the loading screen; its
export confirms a live constructor-registered object and sustained roughly 5.3
game FPS. A background pause later resumes. It does not prove loading completed
or identify a corrupting CheckpointName writer. Do not reinterpret absence of
scalar intents as absence of writes: TSO/SIMD/native stores remain excluded.

The new APK compacts boundary-load code and removes per-field controller guest
faults. Compare the same screen with existing caches intact. Verify the installed
update, inspect game-frame progress and per-interval PadReadState hostemu deltas,
and check whether loading actually advances. Resolve interrupted native PC/LR
against this build's matching native libraries when unwinding stops; these
addresses are not guest RIPs. Distinguish foreground samples from the no-window
background pause. Do not declare a GPU deadlock from a sleeping caller or an
empty command queue; the old source dequeues commands before completion.

If performance/loading still stalls, identify the actual native GPU-worker/main
PC, guest wait return/caller where available, and timing before changing runtime
or synchronization. Shader counts had largely stopped rising during the old
steady 5-FPS interval, so ongoing compilation alone is insufficient. No forced
wait completion, hardcoded guest initialization, invalid-memory zero filling,
TSO disabling, backend replacement or cache wipe is allowed. Execute real tests
and report unavailable device coverage. Treat the new APK's FPS/loading outcome
as unverified until the owner supplies the next log/screen result.
