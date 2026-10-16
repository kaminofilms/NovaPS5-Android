# NovaPS5 0.9.38 — measured label-read bottlenecks

Branch: `fix/novaps5-0936-luna-watchpoint`; starting commit
`4031e68b7da4489ad88f915d1c22e3ede0c76cbb`. Native Android Kyty + NovaFEX remains intact.
Target: versionName **0.9.38-android**, versionCode **92**, existing development signing key.

## Owner evidence and title correction

- **Ever Forward, PPSA04703:** 0.9.37 heartbeats show 8.6, 7.0 and 6.6 game FPS.
  `Other` coherent reads consume roughly 1.6–2.9 seconds per five-second window while
  downloading only about 21–59 KB through thousands of tiny requests. Publication time
  is small; GPU completion/readback roundtrips dominate. Inclusive scopes overlap.
- **Super Meat Boy, PPSA31162:** the owner explicitly corrected the title identification.
  It is NOT Luna. The 20.7 FPS sample is loading/menu, NOT gameplay. Subsequent gameplay
  shows 1.3 FPS; EOP drain time reaches 3.4–4.15 seconds per roughly five-second window.
- The phone became very hot. No temperature/clock telemetry was supplied, so thermal
  throttling is not established. Do not claim a heat reduction or gameplay gain from this patch.

## Actual implementation

Ever's `Other` path is `TryReadBufferBacking`, including genuine GPU-generated label
reads in WAIT_REG_MEM. Nova already knows the immutable bytes uploaded for constant EOP
labels. Previously these bytes were sent to the GPU, copied back through a staging
download and synchronously published simply to evaluate a small internal coherent read.

`novaEopLabels.h` retains only those recorded constant upload bytes, their guest range,
and the actual scheduler tick. Entries are GPU-thread-owned, own their bytes, support
contained 4-byte reads from 8-byte labels, and are bounded to 4096 entries. Eviction
causes normal coherent readback, never an assumed value.

`BufferCache::TryReadEopLabel` applies only to Ever Forward and Super Meat Boy. It requires
an exact GPU-dirty covered range, a retained label and no texture alias. It then waits for
the label's REAL GPU tick and earlier priority publications, revalidates the entry and
ownership, and copies the known bytes to the internal reader. This does not write guest
CPU backing, clear GPU ownership or remove CPU page protections. Guest CPU faults still
reconcile actual GPU contents through the existing readback path. Unknown GPU results,
timestamps, texture aliases, invalid ranges and cache misses retain their existing path.

Clean PM4 reads bypass this lookup entirely: it is attempted only inside the existing
exact GPU-dirty check. A successful lookup avoids a GPU download/copy submission; repeated
reads of an already completed label do not submit new work merely to retrieve its value.
The real completion dependency remains, so the owner must measure whether this improves FPS.

All buffer GPU write registrations invalidate overlapping retained labels. Downloads
invalidate them when transferring GPU ownership. Texture-to-buffer copies invalidate the
actual copied range; buffer retirement invalidates its full guest range. New constant
labels replace prior overlapping entries only AFTER their staging copy/command is recorded,
and capture the scheduler tick after any staging-ring reuse wait. No map reference survives
a scheduler call. Any entry change during the wait fails closed to real readback.

Super Meat Boy explicitly opts into the already tested GPU constant-label and exact PM4
fetch paths through `GpuLabelProfile()`. Other titles retain their prior profiles. This
targets its measured per-label EOP drains without dropping waits, inventing completion,
changing original WAIT_REG_MEM predicates or enabling the path for unidentified Luna.
Ever-only shader/Finish/cache policies remain Ever-only.

The new `eop_label_read` cost scope reports successful retained-label reads and their
inclusive real wait time. Compare this with `Other` download counts/waits and actual
gameplay `game_fps`; a movement between timing categories alone is not a speedup.

## Reproducibility and checks

`tools/ci/patch-eop-label-reads.py` applies after all existing source overlays and telemetry
checks. Every anchor is validated before publishing the changes. The telemetry-only
static wait-count contract still runs against the telemetry stage. Separate optimization
tests then verify the new real-tick and publication barriers, followed by complete Android
compilation. This is a change to how known values are retrieved, not a telemetry-only patch.

`tests/test_eop_label_reads.py` executes the production lookup and kernel routing bodies:
real-tick/publication ordering, blocked completion, immutable ownership, partial overlaps,
repeated polls, CPU-reconciled and unknown GPU-write invalidation, texture fallback,
capacity/overflow boundaries and profile isolation. It runs normally and with ASan/UBSan.
Fixtures control the host timeline; they do not simulate a proven phone speedup.

The Vulkan label harness checks retained bytes against actual GPU-upload/download results
after real fence completion. Existing EOP, seven WAIT_REG_MEM predicates, PM4 refetch,
shader fences and render-cost regressions run for the new profile and unchanged titles.
Tests remain compatible with the earlier baseline stage and run again on optimized source.

Local normal and ASan/UBSan checks passed. Local sanitizer execution requires
`ASAN_OPTIONS=detect_leaks=0` due the host's process-inspection limitation; ASan/UBSan
themselves remain enabled. The Vulkan harness compiled, but local ICD/layers and SPIR-V
tools are absent; actual Vulkan, SPIR-V, full NDK, ARM64 and APK validation remain CI gates.

Files: the new overlay/header/test; updates to `build-android-kyty.sh`, `android-native.yml`,
`test_ever_gpu_labels.py`, `test_gpu_completion.py`, `test_ever_pm4_fetch.py`,
`test_ever_render_costs.py`, and this handoff. Saves, shader caches and signing identity
are preserved. No fake GPU result, timeout-success wait or removed guest synchronization.

## Device verification

Let the phone cool before a short test. Install over the existing app and retain caches.
Prioritize the same Ever Forward gameplay area for 15 seconds, then export the boot log.
Compare `Other` download counts/waits, `eop_label_read`, total frame times and real
`game_fps`. Test Super Meat Boy gameplay separately; discard loading/menu FPS when
judging improvement. Check both for visual/progression regressions. No further change
or claimed improvement is justified by menu FPS alone.
