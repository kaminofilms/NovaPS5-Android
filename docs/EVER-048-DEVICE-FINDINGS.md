# 0.9.48 owner-device findings and next gates

Device: NX809J / SM8850 / Android16, bundled Turnip26.3.0-20261012-A8xx. Ever Forward PPSA04703, session2026-10-18 23:03:38. Dead Cells PPSA15552, session23:05:48.

## Measured outcome

Ever Forward remains slow: owner heartbeats show game_fps3.9 and4.1. The requested640x360 launch arguments are logged, but repeated1920x1080 passes have four/five color attachments, and4096x4096 depth-only passes remain. There is no evidence of360p main rendering. The540p/270p smaller passes are consistent with a post-processing pyramid; they do not establish that a launch request changed scene resolution. The UI now describes this as a probe with no observed effect, rather than suggesting an effective internal scaler.

Queue-poll waits take2347–2631ms in representative5000ms windows, roughly47–53% of the PM4 thread's wall time, across13850–15445 waits (~169–170microseconds each). These are timed100microsecond condition-variable waits plus scheduling/mutex overhead. This is not proof that half the frame time can be removed: the queue may still depend on real GPU work, CPU writes or priority publication. Existing wait/readback scopes overlap. Readback consumes roughly900–1100ms per five seconds; this must not be added to its nested waits.

The pasted log has no NOVA_BDA activation marker. The prior BDA optimization therefore has no demonstrated active path or benefit in this session. Keep its result classified as unverified; do not credit it with an FPS gain.

Dead Cells has a36.9game_fps heartbeat and later presentation throughput around200frames/5seconds. EOP draining occupies3563–4101ms per five seconds after warmup. The0.9.32 handoff records owner50–57FPS, while the owner's earlier60FPS reports are also part of the regression baseline. Comparing different scenes, cache states and drivers cannot locate a regression commit by itself. The source comparison shows the synchronous drained-store fallback remains selected for Dead Cells, so it is not established that0.9.48 introduced that drain.

## Web findings

- Unity documents screen-width/screen-height as standalone-player arguments, not a guaranteed PS5 render-scale interface: https://docs.unity3d.com/2021.2/Documentation/Manual/PlayerCommandLineArguments.html
- KytyPlus explicitly says its presentation upscaler does not yet implement internal-resolution reduction: https://github.com/Coder787-source/KytyPlus/blob/main/README.md
- Game-specific resolution changes exist for other titles (not portable proof for Ever Forward): https://github.com/boykopovar/AnyPS5/discussions/4697 and https://github.com/KytyPS5/KytyPS5/issues/1048 . The GT7 report says changing TV output status was insufficient; it used that game's operation-submode selection. Do not apply that mode to Ever without evidence.
- Public searches including Reddit, Kyty forks and GitHub title-ID/issue queries did not establish a tested Android Ever Forward fix. PC/Switch/iOS tweaks are not evidence for this ARM64 PS5 runtime.
- Upstream099de8dea62cbf17c8e06a6c24e72b38475d1566 fixes PM4 WRITE_DATA exact-word publication: https://github.com/KytyPS5/KytyPS5/commit/099de8dea62cbf17c8e06a6c24e72b38475d1566 . A bulk memcpy may store a completion word more than once, allowing a consumer's newly reused word to be overwritten. This missing correctness fix is now ported, with per-word translation retained for disjoint guest-VA slots. It is not a measured speed fix.

## Implemented source work

`patch-pm4-word-publication.py` patches the actual WRITE_DATA method. Scalar volatile32-bit destination stores preserve incrementing and repeated-address packets. Source and destination addresses translate per word; no completion value, wait predicate, ownership or page-protection rule is bypassed.

The test extracts the production method and includes production guestMemory.h, substitutes the address-translation boundary with disjoint host allocations, and exercises zero length, invalid selectors, host memory, translated memory, two-slot boundaries, incrementing output, repeated output and scalar overlap order. Normal and ASan/UBSan runs pass. This is not a hardware concurrency/ARM64 timing or gameplay result. The next native build runs the same tests before compilation.

## Requirements for a permanent FPS fix

1. Internal resolution: either identify Ever Forward's own version-specific render-size/quality controls in its game data/code, or implement a full renderer scaling path that coordinates render targets, depth, sample coordinates, resolves, storage-image compute, transfers and readbacks. Clamping a viewport or shrinking Android output alone is insufficient. Logs do not supply the executable/data needed to derive a verified game-specific patch.
2. Scheduling: distinguish time until a real GPU timeline completes from delay after completion, plus CPU-written-label and publication waits. Only the avoidable delay can be removed. Do not just declare all queue sleep wasted or force labels ready.
3. Dead Cells: reproduce the same warmed scene against0.9.32, retain identity guest VA and the existing driver for the comparison, record effective cap/presentation settings, and bisect the native source changes. Any asynchronous label path needs coherent CPU/PM4 reads, actual GPU-before-publication ordering and race/lifetime tests.

The source-only commit does not create another APK and makes no30/60FPS or effective low-resolution claim. Batch a device build after the remaining performance work has a defensible implementation and validation target.
