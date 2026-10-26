# 0987 real flip lifecycle diagnostics — APK BLOCKED

Branch: `fix/wonder-native60-no-apk`. No APK was built and no Actions workflow was started.

This checkpoint does not claim that the six requested tasks are complete. It moves the
ready-queue/presentation/EOP investigation forward without synthesizing a completion,
discarding a frame, or changing guest-visible queue semantics.

## Implemented

- `patches/0987-flip-lifecycle.patch` records host-clock timestamps for Reserved,
  Recording, Ready and Presenting transitions on each flip request.
- The freeze report now distinguishes missing group owners, GPU members not yet Ready,
  CPU/slave members that block the group, failed `IsFlipDueLocked` retries, background
  state and the presenter's real paused state.
- Per-port atomics count actual flip publication calls and the real
  `KernelTriggerEvent` results (`OK`, `EBADF`, `ENOENT`). The request retains the event
  state shared pointer captured at reservation, so close/reopen cannot race the freeze
  report's ownership read.
- The former report read `flip_status` fields without the port mutex while holding the
  queue mutex. Taking that mutex would invert the presentation lock order. 0987 removes
  those unsynchronized reads and derives blockers only from queue-owned state.
- `tools/ci/patch-0987-flip-lifecycle.py` is fail-closed and applies only after 0985.
  `tests/test_0987_flip_lifecycle.py` verifies that the report cannot trigger events or
  mutate request state and that publication counters are attached only to real flip
  event delivery.

## Validation completed here

- The 0987 patch applies cleanly to the historical 0980 core after the 0985 overlay.
- The structural lifecycle regression passes.
- All twelve previously selected production translation units, including the complete
  modified `videoOut.cpp`, compile to AArch64 ELF objects with Android NDK r29 Clang 21,
  API 33, C++20/O2 and the production bionic forced include. The real Android framework
  power probe still links with `--no-undefined`.
- This remains object-level validation, not a full core link, Android execution or game
  timing result.

## Still unresolved; APK remains prohibited

1. General GPU-written/BDA/storage ownership, safe transfer scheduling, and exact
   CPU-store-aware reconciliation are not implemented.
2. Real Adreno validation of read-only depth/store behavior and remaining G-buffer
   write-to-sample dependencies is absent.
3. The version-aware binding caches still need a full Android core link plus real Vulkan
   command/lifetime and hit-rate validation.
4. 0987 can now identify the exact Ready/group/due/event-publication edge, but no device
   freeze trace from this instrumentation exists yet. It deliberately does not force
   completion or manufacture a UnityFTMFlipQueue event.
5. Guest CRI/FEX attribution and on-device audio queue/sound validation remain open.
6. ADPF/worker policy remains opt-in and needs Android service, lifecycle, cpuset,
   thermal and performance validation. No CPU IDs or clocks are forced.

The recovered `active-source/repo` is not the latest complete frontend. Do not package
it. A future APK is allowed only after the full current application is refreshed,
native link/runtime gates pass, and device telemetry demonstrates the requested result.
