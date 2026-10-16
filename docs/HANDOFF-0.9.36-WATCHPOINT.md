# NovaPS5 0.9.36 — constructor watchpoint handoff

Continue on `fix/novaps5-0936-luna-watchpoint` in kaminofilms/NovaPS5-Android.
Protected 0.9.35 baseline: 26fae46b7e1b6e81b408b8385006a059bffe9c8e.
Owner authorized source edits, pushes, CI and a signed 0.9.36 APK after gates pass.
Native Android ARM64 Kyty + pinned FEXCore 14c92681f4d62cf84d901460e0358de09c8847a7
must remain. Do not change renderer compatibility, TSO, app ID, signing identity,
saves, shader caches or imported drivers. Do not claim a game boot/FPS without
owner-device evidence.

## Current implementation

The scalar StoreMem hook materializes exact native store addresses and captures
source-register payload plus FEX GuestOpcode RIP. PushDynamicRegs/SpillStaticRegs
precede argument assignment; FillStaticRegs/PopDynamicRegs restore state. Exact
FPCR/FPSR are saved before FEX spills and restored after fills. The pinned emitter
lacks an FPSR enumerator; the source patch uses architectural S3_3_C4_C4_1.
The recovered Q-only assembly wrapper is not combined with FEX preservation.

Scalar GenerateMemOperand and original native store instructions are retained.
StoreMemTSO, SIMD and SVE store implementations remain unchanged. Records are
ATTEMPTED with completion unobserved, including after successful native stores.
The verified guest/host field correspondence prevents labeling translated host
addresses as guest addresses. No speculative guest memory is read for payloads.

The owner then supplied eboot.bin. Its readable SELF payload and reflected class
metadata establish SaveGameInstanceData's CheckpointName at +0x38, with the next
member at +0x48. See LUNA-0936-BINARY-EVIDENCE.md for the exact SHA256, metadata
chain, disassembly findings and RVAs. This supersedes the earlier missing-site
blocker; it does not establish a live object or the corrupting writer.

The loader configures the profile after main-module loading and symbol parsing,
before guest initialization, only for PPSA36257. Six code/name/layout spans must
match. Safe kernel copies read only bounded mapped-module spans. Unknown versions
reject without arming. The full input hash is documented, not recomputed at runtime.

FEX GuestOpcode instrumentation at base+0xf2fca3 reads spilled guest RBX (object)
and RAX (expected class vtable base+0x6f114f0), and registers the verified object
before the first derived vtable store and original SIMD field initialization.
The callback does not dereference FObjectInitializer or the object. At
base+0xf3b5c4, destructor RDI and RAX identify and retire the object before the
original destructor store. Retired slot data stays immutable and is never
reclaimed; a reused allocation requires a new verified constructor event and slot.
There are 16 slots; exhaustion is logged. No reset/zeroing of guest data is added.

The 1024-slot ring is allocation-free, bounded MPSC with explicit full/contended
drops. ReportGuestFault and typed retirement dump NOVA_STORE_INTENT records.
Logging includes sequence, matched object/fields, guest RIP/address, width,
payload and HOST thread ID. Never call that a guest scheduler ID. Records may
need ordering by sequence. A full ring drops later records until consumed.

## CI and packaging

Existing .github/workflows/android-native.yml now carries all gates in one run,
with Kyty build waiting for novafex-test. The older dedicated watchpoint workflow
is manual-only to avoid duplicate FEX builds. Tests include full host ASan/UBSan,
original ARM64 bridge regressions, scalar widths/zero/address/RIP/payload/flags,
live SIMD, indexed/negative/signed/unsigned address differential checks, original
successful and SIGSEGV stores, plus signature rejection and automatic typed
constructor registration/retirement with TSO enabled and in scalar-test mode.
The constructor fixture is sparse synthetic memory with selected verified spans,
a base-constructor stub and a shortened destructor tail. It is not execution of
the complete game and must never be described as a Luna boot.

Prior scalar-only validation passed at run 38835231143 / source commit
1251c9e80c615196ef507c8f71bd39abfaa6066a. That predates automatic constructor hooks.
Check the new full Android run for the constructor-enabled implementation; do not
assume it passed. Repair actual failures without removing tests or faking results.
Local host sanitizer tests passed again after profile/lifetime changes. Local
LeakSanitizer is unsupported under process tracing; only the local rerun disables
leak detection. CI uses full ASan/UBSan without that override.

Target APK is NovaPS5-0.9.36-android-arm64.apk, versionName 0.9.36-android,
versionCode 84 (>0.9.35's 83). Keep com.kaminofilms.novaps5 and
 tools/ci/novaps5-ci-test.keystore / alias novaps5dev / password android.
The existing APK verifier compares its signing certificate to that keystore,
checks the package/version/ARM64 and native libraries. Actual update installation
still needs the owner's phone. No data cleanup is authorized or required.

## Next owner-device log

Install the new APK as an update and launch PPSA36257 to the same crash. Preserve
full logs, especially:

1. NOVA_LUNA_PROFILE armed/rejected, module base and constructor/destructor RIPs.
2. NOVA_LUNA_OBJECT registered/retired, object address and expected vtable.
3. NOVA_STORE_INTENT records and existing NOVA_FAULT guest/module/register output.

A rejected profile must be investigated against that device's exact executable;
never force known RVAs onto another build. An armed profile without a registration
record means the proved constructor boundary was not reached or its register
checks failed; no live object should be guessed. Registration without a relevant
scalar writer record does not rule out corruption: production TSO stores, SIMD
stores and native memcpy/HLE writes are outside scalar StoreMem coverage. The
original constructor itself clears the field through SIMD, deliberately unchanged.
Do not disable TSO or broaden forbidden paths without explicit owner direction.

If a relevant record appears, map guest RIP to module-relative instruction bytes,
check width/source/EA against disassembly and emitted AArch64, and correlate any
fault. A pre-store record does not prove completion. Do not assume the historical
memcpy crash RIP 0x910003fc6 is the writer, or assume every 0x42c80000 value is
illegitimate. Establish translation/layout/loader root cause before changing game
state. No hardcoded zero fields, suppressed faults or fake initialization.

SVE256/AFP-specific and target Snapdragon/Android behavior remain device checks;
the previous ARM runner reported SVE256=0 and AFP=0. End-to-end address tests do
not directly prove every raw-IR helper branch, since NovaAddressTranslation may
materialize offsets first. The existing constant-scaling discrepancy in that
pass is a separate unproven concern, not an established Luna cause.

## Completed release and verification

Source / tested APK commit: `55ad2a60abbedfa3f2df3002d5530908ca234a57`.
Successful full run:
https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38890414120
Release:
https://github.com/kaminofilms/NovaPS5-Android/releases/tag/v0.9.36-android-55ad2a6
Direct APK:
https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-55ad2a6/NovaPS5-0.9.36-android-arm64.apk

APK size: 20601452 bytes.
APK SHA256: b71246e76e535494bb8fdb2826a673dc7a3cd44242ba1719a62d275cedea93c1
Signing certificate SHA256:
21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0

All workflow jobs succeeded: novafex, novafex-test, ffmpeg, kyty, apk and logs.
Full host ASan/UBSan and ELF/SELF fixture tests passed. Actual ARM64 bionic
execution passed the original regressions, scalar RIP/address/payload/width/zero,
flags/SIMD and addressing checks, genuine successful/SIGSEGV store tests, and
signature rejection plus automatic constructor registration and retirement in
both production-TSO and scalar-test modes. Expected registration and retirement
records appeared in the ARM64 fixture logs; they are not owner-device records.

Kyty compilation/linkage and all existing compatibility/renderer checks passed.
Packaging verifier reported NOVA_NATIVE_APK: ALL PASS, including the original
certificate, application ID, version, AArch64 libraries, Android dependencies,
16 KB page alignment and expected JNI/API exports. Bundled Turnip verification
passed. GitHub release API confirms the APK asset is uploaded and its SHA256
matches the digest above. No manual test gate was removed or bypassed.

The version/signing/package requirements for updating 0.9.35 are verified;
installation on the owner's Red Magic 11 Pro is still unperformed. Preserve all
app data and install as an update. Reproduce the same Luna failure and export
FULL boot logs, since the Key lines summary may omit the new trace records.
The writer/root cause and successful Luna boot remain unverified.

## Exact changed repository paths against the protected baseline

- .github/workflows/android-native.yml
- .github/workflows/novafex-watchpoint.yml
- tools/ci/build-android-novafex.sh
- tools/ci/build-android-kyty.sh
- tools/ci/patch-0936-fex-watchpoint.py
- tools/ci/patch-0936-luna-constructor.py
- tools/analysis/inspect_luna_elf.py
- native/novafex/CMakeLists.txt
- native/novafex/novafex.h
- native/novafex/novafex.cpp
- native/novafex/watchpoint/NovaFexWatchpoint.safe.hpp
- native/novafex/watchpoint/NovaFexTraceRing.hpp
- native/novafex/watchpoint/NovaFexWatchpointBridge.cpp
- native/novafex/watchpoint/NovaFexLunaProfile.hpp
- native/novafex/test/novafex_test.cpp
- native/novafex/test/watchpoint.inc
- native/novafex/test/luna_constructor.inc
- tests/test_0936_watchpoint.cpp
- tests/test_luna_elf_inspect.py
- docs/LUNA-0936-BINARY-EVIDENCE.md
- docs/HANDOFF-0.9.36-WATCHPOINT.md

The staged FEX source patch changes MemoryOps.cpp (scalar StoreMem only) and
MiscOps.cpp (typed constructor/destructor GuestOpcode boundaries). The staged
Kyty source patch changes loader/runtimeLinker.cpp. No renderer source or
StoreMemTSO/SIMD/SVE store implementation was changed.
