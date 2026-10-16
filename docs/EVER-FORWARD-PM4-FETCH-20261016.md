# Ever Forward exact PM4 fetch — versionCode 90

The owner's versionCode 89 phone log confirms the GPU-label path is active (`eop_gpu` about 3,400–4,000 calls per five seconds). EOP drained CPU-store time fell to roughly 7–14 milliseconds, but readback rose to roughly 3.6–3.9 seconds and game FPS remained 2.7–3.0. This is not a demonstrated gameplay speedup. Shader warmup and lower available memory are additional variables; neither explains away the measured readback bottleneck.

## Change

For Ever Forward PPSA04703 only, command submissions retain their guest identity. The parser fetches the exact header and required packet payload through `TryReadBufferBacking`, which synchronizes actual intersecting GPU-dirty bytes and reads clean bytes through the backing alias. It no longer dereferences a protected host mapping merely because unrelated label bytes share a 4 KB page. Other titles retain the prior translated pointer path.

Each packet is fetched anew on retry. Conditional skips, indirect calls/chains, original remaining/total cursor arguments, packet decoding and real WAIT_REG_MEM predicates remain in place. The temporary packet lives through its handler invocation. Command handlers consume/copy their inline data synchronously. Ordinary R_ZERO NOP padding consumes only its first payload word; marker and custom NOPs retain full payload reads and side effects. Invalid headers, truncated packets and failed backing reads fail closed. Genuine GPU-written command bytes still require completion/readback.

This removes a concrete unnecessary-readback mechanism. The supplied log does not identify every readback caller, so its contribution to overall phone FPS is unproven. New `pm4_fetch`, `readback_read` and `readback_write` host scopes help separate residual costs. Inclusive scopes overlap and must not be summed.

## Files

- `tools/ci/patch-ever-pm4-fetch.py`: fail-closed source overlay, parser/identity changes, read/write readback attribution.
- `tests/test_ever_pm4_fetch.py`: executes the production fetcher with protected guest aliases, adjacent dirty labels, genuine GPU-written packet bytes, refetch on retry, NOP/marker handling, maximum packet, slot-boundary range, bounds/error checks and title profiles; normal and ASAN/UBSAN modes.
- `tools/ci/novaRenderCosts.h`: new scope names.
- `tools/ci/build-android-kyty.sh`: applies overlay after GPU-label integration and runs both new test modes.
- `.github/workflows/android-native.yml`: versionCode 90 and release notes.

Applied Kyty files: `src/graphics/guest_gpu/graphicsRun.cpp`, `src/graphics/host_gpu/renderer/cache/bufferCache.cpp`, installed timing header. Retains versionCode 89 GPU-label changes and other titles' versionCode 88 paths. Protected development baseline is untouched.

## Verification and release

Source `59de40023d449288b6421f4d737df8f4fc58aaf8`, branch `fix/novaps5-0936-luna-watchpoint`.
CI: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38915865949

Local production-fetch normal and ASAN/UBSAN tests pass in Ever/Dead Cells/missing-title profiles. EOP ordering tests also pass. The source-level packet test uses a backing fixture; actual FEX translation, full renderer integration and Vulkan ordering remain separate CI gates and phone validation is required. All six CI jobs passed. The actual CI log confirms all six new normal/sanitizer/profile fetch tests passed, along with the 512-write Vulkan synchronization test with zero errors. Existing profile/Finish/ring, EOP ordering, native ARM64 cross-slot faults and APK verification gates passed.

APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-59de400/NovaPS5-0.9.36-android-arm64.apk

VersionName remains `0.9.36-android`; versionCode is **90**. Size **20,617,836 bytes**, SHA-256 `0fb27e9890363a3162187a8e57aa8f2e2af8c9650cdc7829efe592f81d645780`. Package and signing certificate match prior updates. No device FPS or visual-correctness result is claimed for versionCode 90.

## Next phone test and continuation prompt

> Continue NovaPS5 native Android ARM64 performance work from the versionCode 90 source/run above on branch `fix/novaps5-0936-luna-watchpoint`. Read this file, `EVER-FORWARD-GPU-LABELS-20261016.md` and the next full phone export. VersionCode 89 moved EOP drain cost into synchronous readback and still measured about 3 FPS. VersionCode 90 avoids parser page faults on clean PM4 bytes adjacent to GPU labels, using exact coherent backing reads and minimal ordinary NOP payload reads. Verify `pm4_fetch`, `readback_read`, `readback_write`, EOP counters and game FPS in the same warm gameplay area. Do not claim a performance gain unless the phone log supports it. If readbacks remain dominant, attribute callers and guest ranges, distinguish real command/resource dependencies from false page sharing, and preserve exact GPU-modified data, protected-page ownership, interrupt order and genuine wait predicates. No fake labels, dropped waits or backend swaps. Keep Dead Cells working and Luna deferred. Implement and test the next evidence-based fix, then build a signed update only after the normal/sanitizer/Vulkan/native ARM64 gates pass. Return the actual APK and a fresh handoff, not a proposal.
