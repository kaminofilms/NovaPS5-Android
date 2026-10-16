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
