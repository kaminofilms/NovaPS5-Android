# 0981–0986 source candidates — APK BLOCKED

Branch: fix/wonder-native60-no-apk. No APK and no Actions run.
The full overlay chain from the recovered Android 0967 source through 0986
applies successfully. This does not establish Android compilation or 60 FPS.

## Implemented source in this checkpoint

- 0981: command-buffer-local descriptor, vertex binding and push-constant caches.
  Fixed storage; complete descriptor payload/layout keys, not pointer identity;
  unsupported/dynamic/pNext/oversized writes fall back. All resource preparation
  still runs. EndRendering invalidates knowledge even with no active pass, because
  raw tiler/transfer helpers can change Vulkan bindings. Existing pipeline cache
  is invalidated there too. Push ranges track each byte and shader stage.
- 0982: AudioOut2 formerly held g_audioout2_state_mutex throughout blocking
  AudioOutOutputs. Owned PCM/gain snapshots now release that lock before output.
  Only a per-context mutex serializes output. Native port leases delay close
  until an outstanding snapshot finishes; context destruction cannot free its
  PCM/gains while the backend uses them. Different contexts can make progress.
- 0983: truly read-only native depth/stencil passes use STORE_OP_NONE (Vulkan
  core 1.3) and a stable READ|SHADER_READ access superset. Disabled for real
  depth/stencil writes, clears, storage bindings, scaled bridge and older APIs.
  Layout selection and genuine write dependencies are preserved. This is not
  permission to elide arbitrary COLOR_ATTACHMENT -> SHADER_READ transitions.
- 0984: ContextPush previously slept forever for a missing/destroyed context
  when blocking=1. It now returns the existing INVALID_PARAM error after
  releasing the state mutex. Valid device/sample-clock pacing remains.

0985 additionally labels freeze requests with actual state names, group/owner,
generation and prepared-frame presence. This changes diagnostics only.

0986 fixes a coverage gap: the initial guest thread bypasses RunThread. Its
real TID now registers at PthreadInitSelfForMainThread using a TLS registration
so native pthread_exit can release it. This adds no affinity or clock override.
The host service test covers this exit path; Android lifecycle testing remains.

Complete C++ diff: patches/0981-0986-core.patch against the historical 0980
patched core (before the three new helper headers). git apply --check passes.
Use either that complete diff or the numbered build overlays, not both.

## Actual validation

- All 0968–0984 overlays applied together, in build order, to a fresh 0967
  corresponding-source checkpoint; each script's compatibility anchors passed.
- Five ASan/UBSan suites passed: worker topology; actual ADPF header against a
  simulated service; binding cache with 10,000 randomized overlapping push
  updates; actual AudioOut2 snapshot function with concurrent context destruction
  and a blocked backend; read-only-depth policy guards.
- A sixth ASan/UBSan suite runs the actual ContextPush body: invalid handles,
  destruction during unlocked sleep, async queue-full, valid device and grain
  pacing. Passed. Leak detection disabled because process inspection is restricted.
- Complete integrated libAudio2.cpp passes host C++20 syntax compilation using
  its real headers and a generated Linux config. Complete context.cpp also
  passes. This is NOT an ARM64 Android compile/link or GPU runtime test.
- All twelve real modified translation units compile to AArch64 objects with
  Android NDK r29 Clang 21, API 33, C++20/O2 and the production novaBionic forced
  include. Includes renderDraw, descriptors, context, libAudio2, audio, pthread,
  commandScheduler, graphicsRun, videoOut, bufferCache, image and semaphore.
  The ADPF/affinity header probe also links with real Android API 33 libandroid
  and --no-undefined. ELF headers verify AArch64. This is NOT a full core link,
  Android execution, timing benchmark, or final CMake release build.
- Recovered an isolated Mesa software Vulkan runtime. The dynamic-rendering
  depth/stencil clear/LOAD replay compares baseline STORE with guarded NONE:
  48 read-only passes using NONE for both aspects, all 256 depth and stencil pixels match, and zero
  core/synchronization validation errors. Both cases retain 66 layout changes.
  No shader draws, feedback loops, texture sampling, Adreno or FPS validated.
- Reproducible native check: tools/ci/check-candidate-android.py CORE --out OUT
  --ndk NDK --repo REPO. It compiles objects and a framework link probe only.
  Reproducible Vulkan test: tests/readonly_depth_vulkan.cpp, compiled with the
  repo and pinned Vulkan-Headers include paths and linked to libvulkan; run
  with an explicit ICD and the Khronos validation layer.

## Important freeze correction from the actual source

FlipQueue::RequestState is {Reserved=0, Recording=1, Ready=2, Presenting=3}.
Complete() sets Ready only AFTER the real GPU completion callback is invoked.
Thus state=2 in the supplied log does not itself indicate a missed completion
callback. Pending ready frames can instead be waiting for presentation/group
eligibility. Inspect group/master association, pause/background state, real
present acquisition and event subscriptions. Do not force-retire those frames
or manufacture UnityFTMFlipQueue events. The 0971 source already releases port
mutexes around Present; do not reintroduce the older blocking lock scope.

## Unresolved gates: no APK until these are resolved

1. General GPU-written/BDA/storage ownership, safe transfer scheduling and exact
   CPU-store-aware fault reconciliation. A one-byte fault address cannot justify
   discarding the rest of a GPU-dirty page. The bounded CPU-owned stream path is
   implemented; arbitrary disjoint-fault bypass/automatic promotion is not.
2. Actual GPU validation of read-only stores, aspect/layout/feedback behavior,
   and remaining real G-buffer sampling dependencies. No general MRT pass merge.
3. Full Android core link/build and Vulkan execution/lifetime tests of the binding caches;
   measure hit rates and CPU cost before assigning an FPS gain.
4. Exact ready-queue/presentation/EOP freeze edge remains unresolved. Existing
   notification hardening preserves timeline ordering; no invented event fix.
5. Guest CRI/FEX hotspot attribution remains unresolved. The global-lock and
   invalid-context bugs are real independent fixes, not proof of the logged
   98% core's cause. Test sound quality and queue behavior on the phone.
6. Android ADPF and worker-policy lifecycle/device validation. Both remain opt-in,
   no guessed CPU IDs or forced clocks. Simulated-service tests are insufficient.

No 30/60 native FPS or thermal improvement has been measured. Preserve original
identity, signing key, latest Welcome Hub and native Kyty + NovaFEX architecture.

Candidate integration is opt-in in build-android-kyty.sh with
NOVA_VALIDATE_COMPLETION_CANDIDATES=1. This selects overlays and host checks
for a native core validation build; it does not certify or authorize an APK.
Power policy remains independently opt-in and has no forced clocks.

Local validation tools recovered for subsequent source work: NDK r29 is at
/workspace/novaps5-toolchain/android-ndk-r29; isolated Mesa ICD/layer packages
are under /workspace/novaps5-toolchain/vulkan-host. Select lvp_icd.json explicitly
and set that directory's usr/lib/x86_64-linux-gnu in LD_LIBRARY_PATH; the system
loader alone has no ICD. Actual check outputs remain in active-source/android-check.
These paths are setup notes, not portable release requirements.
