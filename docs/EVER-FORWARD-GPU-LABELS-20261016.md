# Ever Forward GPU completion labels — 16 October 2026

Target: PPSA04703, native Android ARM64, Kyty + embedded NovaFEX. Branch: `fix/novaps5-0936-luna-watchpoint`. Protected development baseline is unchanged.

## Device evidence motivating the change

The owner's versionCode 88 log reports later heartbeat intervals of 3.9, 4.7 and 4.3 FPS. The user occasionally sees 6 FPS, but sustained 6 FPS is not established. The GPU worker spends roughly 3.4–4.1 seconds per five-second window inside `eop_drain`, with approximately 3,800–4,900 calls. Readback accounts for roughly 0.2–0.5 seconds; stream-ring reuse is only 5–11 milliseconds. Presentation and warmed pipeline lookup are small. Inclusive timings overlap; do not sum them or interpret CPU wait duration as GPU execution time.

The owner reports Dead Cells seems good again and explicitly prioritizes Ever Forward. Leave Luna investigation paused and retain the other titles' versionCode 88 renderer behavior.

## Implementation

`tools/ci/patch-ever-gpu-labels.py` applies after the existing renderer overlay, with exact anchors and no partial writes on an anchor failure.

For Ever Forward only, validated constant 32/64-bit EOP stores call `BufferCache::WriteEopLabel`. It rejects null, unaligned, invalid guest ranges and texture-backed destinations. Accepted destinations go through the existing `ObtainBuffer(..., true)` mechanism, which marks exact dirty bytes and protects CPU accesses. A global all-command memory-write to transfer-write dependency precedes the existing `WriteDataBuffer` flushed staging copy; its buffer barriers order subsequent GPU reads. There is no immediate CPU store, per-label `Finish`, synthetic label, or fabricated completion signal.

Interrupt delivery is deferred to the scheduler's actual GPU timeline after the copy. CPU accesses retain the existing protected-page fault/readback mechanism. Ever Forward's PM4 WAIT_REG_MEM explicitly calls `TryReadBufferBacking`, which downloads actual GPU-dirty data before testing the original predicate. Unsatisfied waits still suspend. Timestamp and special GDS events, unsupported fast-path destinations, and every other title retain the drained fallback. No general backend or shader semantic changes are introduced.

`scope=eop_gpu` counts accepted GPU-label records and their host recording cost; `scope=eop_drain` remains the fallback cost. Compare these with `readback`, `submit`, `wait`, heartbeat game FPS and visual correctness in the next export.

## Verification

- Production EOP body regression: GPU-label recording leaves the CPU label unchanged, queue submission alone does not publish it, actual completion applies the staged value, and interrupts follow it. Covers 32/64-bit labels, IRQ/no IRQ, fallback, timestamps, unsupported event rejection and all title profiles.
- Production WAIT_REG_MEM body regression: both widths, seven compare predicates, coherent GPU-label reads, failed read rejection and unsatisfied suspension. Other titles retain direct translated guest reads.
- Vulkan regression: executes the actual `WriteDataBuffer` and `WriteEopLabel` bodies, with allocation/tracker fixtures, 512 staged 32/64-bit writes, repeated overwrites and GPU readback. Requires synchronization validation with zero errors in CI. This tests command recording and GPU ordering, not the entire production page-fault/mapping system or a game boot.
- Existing MRU, bounded writer, completed-empty Finish, ring concurrency, sanitizer, native FEX, shader fence and APK verification gates remain enabled.
- Local host regressions pass; Vulkan test compiles locally, but local ICD/layers are absent. Actual Vulkan execution and Android compilation are required CI gates.

## Device validation

Install the new APK as an update; preserve game data, imported Turnip and caches. Test the same Ever Forward gameplay area for 60–90 seconds, then repeat with warm caches. Export the full log, including source build identity, heartbeat lines and all render-cost scopes. Check image correctness, audio, input, scene transitions, save/load and return from background. A shader-warmup-only speedup is not proof of steady gameplay gains. Keep the known-good APK for comparison.

30–60 FPS is a target, not a measured result. If GPU labels merely move the same cost into readback, investigate who reads each label and the exact protected-page ownership/readback granularity. Do not bypass real waits, force label values, remove interrupts or globally disable coherency. If readbacks and EOP drains shrink but FPS remains low, profile the new dominant path before making further changes.

## Continuation prompt

> Continue NovaPS5 native Android performance work on branch `fix/novaps5-0936-luna-watchpoint`, starting from the versionCode 89 source and successful release run recorded below. Read this handoff and `docs/EVER-DEAD-CELLS-SYNC-20261016.md`, inspect the next full phone export and confirm its build identity. Prioritize Ever Forward PPSA04703 on NX809J/SM8850/Android16/Turnip A8xx. Compare the same gameplay scene against versionCode 88: heartbeat game FPS, `eop_gpu`, `eop_drain`, `readback`, submit/wait counts, shader warmup, memory and image correctness. Accepted constant labels now use tracked GPU buffer copies and timeline IRQs; PM4 reads resolve actual dirty data. Preserve real completion, protected-page ownership, readback and interrupt order. If performance regresses, diagnose or narrowly disable only the Ever GPU-label path. Dead Cells is owner-reported good again; do not change its path without evidence. Luna remains spinning at loading and is deferred. Implement evidence-based fixes, execute production-body/Vulkan synchronization/native ARM64/APK gates, build a signed update and return the actual new APK/run/source links. Do not promise 30–60 FPS without new phone measurements.

## Build record

Source: `1b334a297bf96e6670b55bb04eab27900fcdcdac`.
CI: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38912842288

All six CI jobs passed: NovaFEX, native ARM64 tests, FFmpeg, Kyty, APK and logs. The actual CI log confirms the 512-write Vulkan test passed with zero synchronization-validation errors. Normal and ASAN/UBSAN profile/Finish/ring tests, EOP ordering and native ARM64 cross-slot faults passed. APK verification passed signature, package/version, AArch64 dependency/export checks, 16 KiB alignment and bundled mesh driver checks.

APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-1b334a2/NovaPS5-0.9.36-android-arm64.apk

VersionName `0.9.36-android`, versionCode **89**. APK size **20,613,740 bytes**; SHA-256 `d4ba7c9b12b939baf101546f493ff7bf5bc2a38207263d43a7bed6d06c6a3823`. Signing certificate SHA-256 remains `21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0`; package `com.kaminofilms.novaps5`.

Files changed in the implementation commit:

- `tools/ci/patch-ever-gpu-labels.py` (new production overlay)
- `tools/ci/novaRenderCosts.h` (`eop_gpu` attribution)
- `tools/ci/build-android-kyty.sh` (overlay and regression gate)
- `tests/test_ever_gpu_labels.py` (new production-body/Vulkan tests)
- `tests/test_gpu_completion.py` (deferred constant-label and IRQ ordering)
- `.github/workflows/android-native.yml` (versionCode 89, release notes)

Applied Kyty source changes: `src/graphics/guest_gpu/graphicsRun.cpp`, `src/graphics/host_gpu/renderer/cache/bufferCache.cpp`, `src/graphics/host_gpu/renderer/cache/bufferCache.h`, plus the installed timing header. This handoff and the top-level watchpoint handoff are documentation-only follow-ups. Actual Ever Forward device FPS, visual/transition correctness and CPU protected-page behavior on NX809J remain unverified for this APK.
