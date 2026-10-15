# NovaPS5 0.9.27: GPU guest memory performance

Device evidence: PPSA31162, NX809J/SM8850, Android 16, bundled Turnip 26.3.0-20261012.
0.9.26 reaches game frame 941 but reports 0.1 game FPS while shader counts rise.
This proves continued work during the stall, not the relative cost of compilation,
GPU execution, guest translation, or kernel mapping. The excerpt does not establish
a deadlock or cache hit rate. The zero GPU-write trace count is intentional release
instrumentation suppression, not evidence that the GPU writes nothing.

Implemented:

* Occlusion event 0x39 now resolves the 256-byte interleaved result span once,
  preserving volatile stores, ready bits, counter progression and untouched end slots.
* Both interpolant mapping functions snapshot guest shader descriptors and alias
  semantic tables and output registers. Guest descriptor pointers are never mutated.
  Views spanning a 1-GiB translation slot retain existing fallback behavior.
* Android explicitly selects a persistent Mesa shader-cache directory before SDL
  loads the Vulkan driver. Driver support for the configured cache is not assumed.
* Cache-miss shader translation/module and driver pipeline creation operations
  taking at least 100 ms report elapsed wall time. No per-draw timing on cache hits.
* The 0.9.26 Vulkan cache signature is retained: shader output semantics are unchanged.

Validation: 8000 randomized comparisons of real original/patched interpolant
functions with nonidentity high guest addresses; unchanged guest descriptors;
real occlusion branch verifies every written and untouched result slot; UBSan.
Existing native packet, completion, metadata and cache regressions remain in CI.

References inspected:

* https://github.com/boykopovar/AnyPS5/blob/main/docs/dev/ARCHITECTURE.md
* https://github.com/boykopovar/AnyPS5/issues/6118
* https://docs.mesa3d.org/envvars.html

AnyPS5's persistent compiled variants and graphics pipeline libraries are relevant
to compilation performance. They are not drop-in replacements for Kyty pipeline
layouts, resource specialization, mesh stages and renderer synchronization. This
patch does not claim that larger renderer integration has been completed.

Remaining: cold shader compilation, synthetic always-visible occlusion behavior
(may increase GPU load), other measured host-memory traps, memory pressure and
unmeasured GPU time. No 30/60 FPS or device speedup is claimed. Retest the same
scene on two launches; compare game FPS, long stalls, cache logs, compilation times
and hostemu deltas, not UI frame count alone.
