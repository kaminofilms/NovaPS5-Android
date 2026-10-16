# Ever Forward performance update — versionCode 87

The owner redirected work from Luna loading to playable Ever Forward and Meat Boy,
with Ever Forward first. Native Android ARM64 Kyty + embedded NovaFEX is retained.
The protected 0.9.35 baseline is unchanged.

## Evidence and limits

Read only the Latest game log portion of ever.txt (PPSA04703, process 31281,
October 16 08:48:21), stopping before Previous game log. Ever Forward samples:
0.4, 0.5, 2.9, 2.5, 3.4, 3.6 game FPS, ending at 196 game frames. Every sample
reports hostemu=0. Shader counts continue growing to VS122 / PS359 / CS18.
The driver cache was invalidated at startup, shader disk hits reach hundreds,
and graphics libraries are actively reused. There is no CPU/GPU timing breakdown
in that capture. Compilation may contribute; it is not proven to be dominant.

Meat Boy's separate latest capture loads its existing 18,710,658-byte driver
cache, reaches 1.3/1.7 FPS, has intermediate 15.0/38.5-FPS intervals, then returns
to 1.1 FPS. Repeated AgcCreatePrimState native memory traps remain. Neither the
intermediate high-rate scene nor sustained 30/60-FPS gameplay is established.
Do not mix the previous game's appended samples into either game's figures.

## Implemented changes

1. Pipeline cache snapshots still retrieve Vulkan data on the owning rendering
   thread. Immutable prefix, payload, and path copies are sent to one disk writer.
   Only one executing job plus one pending job are retained; a newer complete
   snapshot replaces the pending snapshot. Existing file flush, temporary file,
   checksum/signature and atomic rename behavior remain. Shutdown drains older
   writes before the final synchronous snapshot and Vulkan cache destruction.
   No Vulkan handles or PipelineCache pointers are captured by the worker.
2. Shader permutation lookup tests the most recently used index first. Every
   lookup still materializes current runtime resources, checks specialization,
   push-data layout, and linked callee code. Misses search all remaining variants.
   Index storage stays valid across vector reallocations. This avoids a linear
   scan on stable tail-variant hits without assuming guest resource immutability.
3. NOVA_RENDER_COST records bounded five-second per-thread inclusive host scopes:
   draw, dispatch, shader, pipeline, submit, wait, present and snapshot. Records
   include calls, total milliseconds and maximum milliseconds. Nested scopes
   overlap: never sum them as exclusive time. Wait duration is host blocking,
   not a GPU timestamp or measured GPU execution duration. No renderer bypass,
   shader alteration, wait removal, resolution reduction or forced completion.

AnyPS5 reference inspected: boykopovar/AnyPS5 at
82ddae75b6761757f3d3ba9c0723647469270f76, notably
core/libs/prx/libSceAgcDriver/Graphics/src/PipelineCache.cpp and pipeline-cache
synchronization call sites. Its saver thread and snapshot locking reinforce the
need to separate cache I/O from Vulkan use. The Nova implementation keeps all
Vulkan operations on the existing owner thread; no alternative backend is added.

## Validation

Local normal and ASan/UBSan tests passed, exercising the production lookup method,
resource updates, all 128 lookup candidates, exact push layout/callee misses,
2,048-entry vector reallocation, deterministic latest-job replacement, blocking
drain, destructor drain, and nested timing windows. A stable last-of-128 hit makes
one specialization comparison instead of 128. This is an algorithmic result,
not a phone frame-rate benchmark. Local sanitizer execution disables leak scanning
because this environment cannot run LSan under tracing; CI retains its normal
sanitizer environment. Python compilation, shell syntax and whitespace checks pass. An additional local
production-closure I/O harness checks exact written bytes and retention of the
previous cache under create, short-write, flush, and rename failures; all pass.
This additional harness was an ad hoc local check, not a separate CI gate.

Release source: e16c3251b50731992f2aff246873e87ae72bde1f
CI: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38904660114
Kyty/SDL/NovaFEX compilation and native ARM64 regressions passed. Both normal
and ASan/UBSan production MRU/writer/timing tests passed on CI. APK packaging, ARM64/native dependency checks, 16-KiB alignment and signature
verification passed. The signed APK is published.

## Changed repository files

- tools/ci/patch-ever-render-costs.py
- tools/ci/novaLatestTask.h
- tools/ci/novaRenderCosts.h
- tests/test_ever_render_costs.py
- tools/ci/build-android-kyty.sh
- .github/workflows/android-native.yml
- docs/EVER-FORWARD-PERFORMANCE-20261016.md
- docs/HANDOFF-0.9.36-WATCHPOINT.md (handoff link)

The patch changes staged pipeline/pipelineCache.cpp and .h, commandScheduler.cpp,
masterSemaphore.cpp, renderDraw.cpp, renderCompute.cpp, and presentation/window/
swapchain.cpp, and installs two renderer headers. FEX and all guest store paths
are unchanged by this update. The app ID, signing identity, cache format and game
save locations remain unchanged. Killing Android during an asynchronous write
can lose the newest cache snapshot, but atomic rename retains the last complete
file; this does not affect saves or guest execution correctness.

## Next device test / continuation prompt

Continue NovaPS5 native Android performance work on
fix/novaps5-0936-luna-watchpoint. Ever Forward PPSA04703 is first priority;
Meat Boy PPSA31162 follows, and Luna remains paused. Read this document and
HANDOFF-0.9.36-WATCHPOINT.md. Install the newest verified APK as an update,
retain shader caches and saves, and capture Diagnostics → Export while playing
the same Ever Forward area. Compare the first and repeat visits on the same
build. Confirm the matching build before attributing improvements.

Group NOVA_RENDER_COST by tid and time window. A high shader/pipeline contribution
points to CPU translation or pipeline creation; large draw time outside those
scopes points elsewhere in resource preparation/recording. Large wait/present
regions justify deeper GPU/queue investigation but do not prove GPU shader time
or deadlock. Use GPU timestamps or targeted measurements before claiming a GPU
bottleneck. Scopes are inclusive and must not be added together. Keep previous
log sections separate. Determine whether stable warmed gameplay, not menus or
loading, improves. Do not promise 30/60 FPS from algorithmic microtests.

No fake completions, removed waits, disabled correctness checks, backend swap,
cache wiping, hardcoded initialization or unverified FPS claims. Batch further
fixes based on the new evidence, run existing gates, and return the actual signed
APK plus CI/source identifiers. The current changes reduce known CPU work but
cannot establish the dominant bottleneck or full-speed feasibility without the
next phone comparison.

## Published release

APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-e16c325/NovaPS5-0.9.36-android-arm64.apk

- Source: e16c3251b50731992f2aff246873e87ae72bde1f
- Version: 0.9.36-android / versionCode 87
- Package: com.kaminofilms.novaps5
- Size: 20,613,740 bytes
- APK SHA-256: 5c584b5c1741a08dc4f6d463ef9e3476589705bcdbc6d9193c4e9797d107c233
- Signing certificate SHA-256: 21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0
- Actions APK artifact: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38904660114/artifacts/12048256605

The signature, application ID and higher versionCode are compatible with an
update from earlier development releases. Actual installation and Ever Forward
performance on NX809J remain device tests. No 30/60-FPS result is claimed.
