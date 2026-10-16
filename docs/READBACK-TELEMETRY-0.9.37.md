# NovaPS5 0.9.37 readback attribution

Branch: `fix/novaps5-0936-luna-watchpoint`. Parent: `102fbee4e0de4298dde422efec85dc68fb9d0254`.
The supplied recovery artifact is versionCode 85; the current branch has released 90.
The owner selected versionCode **91**, versionName **0.9.37-android**, to preserve normal update installation.

## Reproducible implementation

`tools/ci/patch-novaps5-readback-telemetry.py` validates every anchor before publishing edits.
It runs after existing renderer/PM4 patches in `build-android-kyty.sh`; new normal and
ASan/UBSan tests run before Android compilation. `novaReadbackTelemetry.h` is copied into
the staged renderer by this patch, not installed by editing temporary CI source alone.

Explicit contexts cross `HandleFault`, `InvalidateMemory`, `ReadMemory`, the synchronous
GPU command capture, and both download template instantiations. Compute LDS and texture
metadata are explicit callers. The additional kernel `TryReadBufferBacking` caller is
`Other`, never silently attributed to a fault. Garbage collection is explicit too.

Nonempty classification follows the original zero-copy early return. GPU copy source
offsets are relative to the buffer's guest base. Half-open intersections use subtraction,
so no end-address addition wraps. A one-byte fault describes only the known fault address;
disjointness cannot prove that the instruction's complete access is disjoint.

Promotion candidates compare the original download request with the actual memory-tracker
callback spans. Sparse dirty bytes within an unchanged request do not imply promotion.
Overlap and promotion are independent. No full instruction-width claim is made.

Per-caller fields: nonempty calls, zero-copy calls, copied bytes, copy ranges, tracker
ranges, direct overlaps, address-disjoint calls, promotion candidates, synchronous GPU
wait time, priority-publication wait time, publication/invalidate/memcpy time, and deferred
priority-worker GPU wait time. Deferred metadata is owned by its queue item; no thread-local
attribution crosses threads. Timers surround existing operations and introduce no GPU waits.

`NOVA_RENDER_COST` samples cumulative relaxed atomic totals at the existing five-second
cost-window boundary. Producers never take a diagnostic mutex. A dumper-only atomic flag
serializes snapshots; counters are not reset. Independently sampled fields can straddle
adjacent windows; use multiple windows before calculating rates. Deferred worker waits
and synchronous waits can overlap; do not add inclusive measurements as exclusive costs.

Ever Forward PPSA04703 is enabled by default. Other titles remain disabled unless explicitly
enabled through `NOVA_READBACK_TELEMETRY=1`, or Android property `debug.novaps5.readback=1`.
The profile is cached; restart the app after changing the property.

## Lifetime and ordering review

Shared download ring allocations commit the current GPU tick. Before reuse,
`StreamBuffer::WaitPendingOperations` waits for both GPU completion and priority publications.
Temporary allocations remain captured by the publication callback's unique owner.
Synchronous downloads wait for earlier priority publications before their own memcpy.
GC batches downloads, waits for GPU and publication completion, then removes protections
and retires buffers. A CPU write fault's synchronous GPU command cannot return through
these paths before the required publication barrier completes.

The RELEASE_MEM host fallback waits for GPU completion and priority publications before
the guest store and interrupt. The existing Ever GPU-label path records the label in the
real GPU stream and resolves CPU observations through coherent readback. This patch does
not alter either path or introduce a new label-publication mechanism.

The ordering test executes the production priority worker/queue/wait methods and production
stream reuse method against a controlled host timeline. It holds publication after GPU
completion, verifies queued/active barriers, memcpy-before-label, reuse-after-publication,
and a later CPU write. This is not complete FEX/page-fault/Vulkan concurrent runtime proof.

## Validation and remaining gates

Local: 19 expanded source/header tests pass; production ordering harness passes ten repeated
runs. Both suites pass ASan+UBSan execution with `ASAN_OPTIONS=detect_leaks=0` because this
host's LeakSanitizer cannot inspect processes under its execution environment. No ASan or
UBSan checks were disabled. The initially supplied standalone test also passed with leak
detection disabled. Existing render costs, PM4 fetch, GPU-completion and RELEASE_MEM host
checks passed. GPU-label Vulkan harness compiled, but actual Vulkan execution was skipped
locally because the ICD/layers are absent. SPIR-V binary validation also needs CI tools.

All patch anchors were additionally verified against the exact corresponding source from
versionCode 90 run `38915865949`, artifact `12052548631`, not just the older recovery source.

CI must pass required normal/sanitizer/Vulkan/ARM64 tests, full renderer compilation and
APK verification before publication. Existing signing key, alias and package are preserved.
No saves, shader caches, synchronization predicates or guest completion values are changed.
No device FPS, visual correctness or performance improvement is claimed.

## Device test and continuation

Install the signed update over the existing app. Keep caches and saves. Run Ever Forward
for at least 15 seconds in the same warm gameplay area, then export its boot log.
For Super Meat Boy use its actual installed title ID from the exported log; do not infer it.
To opt another title into the diagnostic counters using ADB:

```sh
adb shell setprop debug.novaps5.readback 1
# Close/reopen NovaPS5, launch the title, then capture 15 seconds and export the boot log.
adb shell setprop debug.novaps5.readback 0
# Restart the app to return to the default Ever-only scope.
```

Compare caller wait milliseconds, nonempty counts, bytes/ranges, overlap/disjoint/promotion
rates across several windows and actual `game_fps` heartbeats. Optimize only the measured
dominant dependency after confirming whether the copied bytes are truly required. Never
skip coherent GPU results based solely on an address-disjoint one-byte fault.

Follow-up handoff must record the final commit, CI run/job/artifact IDs, APK verification
and signing results, and any failures. CI/device results supersede these local observations.

## Final release evidence — October 16, 2026

APK source commit: **`5e007e6ac85a4dc1bb2936d122df3aa0eb240dc1`**.
Initial implementation: `1d59cfd6641b65e2c1a7ca9c58f3a1a556c2ff9b`; the final commit
corrects the first sampling window to use actual time from counter initialization.
Branch remains `fix/novaps5-0936-luna-watchpoint`. A documentation-only follow-up records
these results and does not change the compiled APK source.

All six jobs succeeded in run **38940869683**:
https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38940869683

| Job | ID | Result |
| --- | --- | --- |
| FFmpeg | 117108230781 | Passed/cache restored |
| NovaFEX NDK | 117108230867 | Passed |
| Native ARM64 tests | 117108938236 | Passed |
| Kyty renderer | 117109046318 | Passed |
| Signed APK verification/publication | 117111572581 | Passed |
| Log archival | 117112067903 | Passed |

CI explicitly ran both 19-test normal/sanitizer readback suites, ten normal plus ten
sanitized production ordering runs, existing render-cost/PM4/RELEASE_MEM regressions,
SPIR-V validation and the Vulkan label harness. The latter executed 512 production staged
32/64-bit writes with **zero synchronization validation errors**. Full Android ARM64
renderer compilation passed. The CI ASan/UBSan executions passed without the local
LeakSanitizer workaround. These are component/runtime-harness sanitizer checks, not a
claim that the complete Android emulator was compiled with ASan or tested on the phone.
No test failures were bypassed. The earlier run `38940399980` was superseded/cancelled
for the initial-window correction and is not the release evidence.

| Artifact | ID |
| --- | --- |
| android-apk | 12062599879 |
| android-kyty | 12062364448 |
| android-novafex | 12063666510 |
| android-novafex-test | 12062942240 |
| android-ffmpeg | 12062618044 |

APK only (20,621,932 bytes):
https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.37-android-5e007e6/NovaPS5-0.9.37-android-arm64.apk

Release:
https://github.com/kaminofilms/NovaPS5-Android/releases/tag/v0.9.37-android-5e007e6

VersionName **0.9.37-android**, versionCode **91**. The owner explicitly selected 91
instead of the handoff's stale 88 so Android can update the current versionCode 90.
APK SHA-256: `a77395f4e801f568d6d1368a62514135d33648aa97f41fc97d989f99ec6e8faa`.
Signing certificate SHA-256: `21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0`.
`verify_native_apk.py` reported signed with the Nova test key, package/version checks,
Android-resolvable AArch64 libraries, 16 KB alignment, required exports and ALL PASS.
Packaged Turnip verification passed. Signing still uses `tools/ci/novaps5-ci-test.keystore`.

Committed implementation files:

- `tools/ci/patch-novaps5-readback-telemetry.py`
- `tools/ci/novaReadbackTelemetry.h`
- `tools/ci/build-android-kyty.sh`
- `tests/test_novaps5_readback_safety_expanded.py`
- `tests/test_novaps5_readback_ordering.py`
- `tests/novaps5_readback_telemetry_sanitizer.cpp`
- `tests/readback_wait_contract.txt`
- `.github/workflows/android-native.yml`
- `docs/READBACK-TELEMETRY-0.9.37.md`

The reproducible overlay changes staged buffer-cache declarations/definitions, renderer
fault/compute/texture callers, kernel backing reads, scheduler declarations/definitions,
and the installed cost/telemetry headers. GPU commands, wait counts and completion
conditions are unchanged. Full device concurrency, visual correctness and FPS still need
owner logs. Sampling skew across independently sampled fields and unknown instruction
access width remain interpretation limits, not evidence that a readback can be skipped.

Next engineer: start from the APK source SHA and this branch. Obtain 15-second warm
Ever Forward and explicitly opted-in Super Meat Boy exports; use the latter's actual
logged title ID. Rank per-caller wait time over several windows, separate synchronous
GPU waits from publication waits and deferred-worker waits, and compare actual `game_fps`.
No next performance optimization is justified until these device measurements arrive.
