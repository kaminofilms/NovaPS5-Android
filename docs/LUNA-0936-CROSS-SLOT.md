# Luna libc cross-slot load: device evidence and regression

The 2026-10-16 NX809J log reaches 959 game frames, with sampled game FPS
roughly 3–5.5, then faults at libc.prx+0x3fe8. This establishes rendered game
frames, not which scene was visible or that startup is fully fixed.

The exact guest bytes `c5 fa 6f 7e 70` decode as
`vmovdqu xmm7,[rsi+0x70]`. RSI is `0x903fffff83`, so the 16-byte read starts
at `0x903ffffff3`: 13 bytes before the guest slot boundary `0x9040000000`.
The preceding native instructions translate that start address with delta
`0xffffff8044000000`, giving host address `0x1083fffff3`. The native
`ldr q23,[x20]` therefore crosses into `0x1084000000`, the reported fault
address. Translation of only the first byte cannot represent this read when
adjacent guest slots have separate host backing windows.

The downstream FEX patch retains the complete guest address for 128-bit FPR
LoadMem and LoadMemTSO through a NovaLoad128 operation. Loads contained in one
slot retain a native vector load. Boundary loads translate each of 16 byte
addresses with acquire table reads, accumulate into reserved temporary vectors,
then commit the allocated vector. No native condition flags, allocated source
registers, guest pointers or stack state are changed. TSO vector-load barriers
are preserved. Missing/protected backing memory still faults at a byte read
mapped to the original guest RIP; no exception handler advances the PC.

This correction covers those 128-bit load operations. It does not claim to
solve cross-slot stores, 256-bit loads, paired/masked memory operations, or REP
bulk operations. SIMD/SVE/TSO store encodings and scalar watchpoints are untouched.

ARM64 tests use the exact Luna instruction and all 15 crossing alignments,
with a readable poisoned host neighbor that would silently return wrong data
under first-byte-only translation. They check output and ZF, plus separate
unmapped/protected next-slot runs checking a real SIGSEGV, unchanged output,
and the exact guest RIP. Both TSO configurations run in CI.

The pasted device log contains no constructor registration or store-intent
records. It does not identify a CheckpointName writer or establish the earlier
float-100 corruption's cause. The next device run must still provide startup
NOVA_LUNA_PROFILE/NOVA_LUNA_OBJECT messages, any NOVA_STORE_INTENT records,
and the complete next fault or successful scene progression.

Meat Boy reaches gameplay according to the device report, then logs 1.0–1.1
game FPS. The earlier 37.3 sample is not steady-state performance. Shader counts
continue rising and available memory falls to 772 MB. Repeated host-emulated
AgcCreatePrimState accesses are visible, but these counts are not timing data;
none alone establishes the bottleneck. No renderer optimization or FPS fix is
claimed by this memory-correctness patch. Preserve caches for a repeat capture.

Performance source identification (same released libmain.so): offset 0x823a54
decodes as `strb w12,[x0],#1` in the RandomGetRandomNumber loop in
kyty/src/libs/libNet.cpp (LCG constants 1664525 and 1013904223). Its count stays
at 4864 in the later samples, so the cumulative top count does not establish a
continuing hotspot. AgcCreatePrimState in kyty/src/libs/agc.cpp directly follows
gs/hs specials pointers and writes cx/uc register outputs; those sites continue
faulting. Measure elapsed time and per-interval deltas before selecting a
performance change. Do not bypass GPU waits or clear shader caches.

Validation source commit: 56282b0a1751f72667c48ff953b85faa25698185.
CI run: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38896361820

FEX compilation/linkage, host ASan/UBSan and native static-bionic ARM64
regressions passed. Both full native runs report ALL PASS, including the
poison-neighbor byte comparisons and ZF. All four combinations of TSO on/off
and next-slot unmapped/protected report an original SIGSEGV, unchanged output
and exact RIP equal to the emitted VMOVDQU fixture. This is ARM64 execution on
a Linux runner, not the NX809J's Android signal/mapping environment.
The first CI attempt (c872f96, run 38895628872) rejected an unsized emitter GPR
move; commit 56282b0 supplies the required i64Bit width. No test was disabled.

Counter interpretation: videoOut.cpp calls NoteGameFrame after Presenter::Present.
The increasing game_frames counter therefore records presentation progress; it
does not identify the visible scene. The freeze-report GPU write-history counter
is diagnostic history, not a draw/presentation count. Its zero value must not be
used to conclude that these games performed no rendering.

## Published update

All jobs in run 38896361820 completed successfully. APK source commit:
`56282b0a1751f72667c48ff953b85faa25698185`.

Direct APK (20,609,644 bytes):
https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-56282b0/NovaPS5-0.9.36-android-arm64.apk

APK SHA256: `e9e6be563b3961b4823c850048eda7dcdbc31a32810ba2cebf35f9051a0cba3d`.
Signing certificate SHA256:
`21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0`,
matching the previous release. VersionName 0.9.36-android, versionCode 85,
package com.kaminofilms.novaps5. APK validation confirms signature, version,
ARM64-only native libraries, Android dependencies and 16 KB alignment. Mesh
driver verification also passed. Actions artifact android-apk: 12044570819.
Install compatibility is supported by the unchanged package/certificate and
higher versionCode; actual update installation remains a phone test.

The protected 0.9.35 release and the preceding 0.9.36 APK remain unchanged.
There is no target-device result for this update yet.
