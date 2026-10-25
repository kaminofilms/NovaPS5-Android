# Wonder Boy native 60 investigation — source only, 2026-10-25

Title: PPSA27841, Wonder Boy: Asha in Monster World. Device: nubia NX809J,
SM8850 / Adreno 840, Android 16, Turnip 20261012. No APK built for this work.

## Device evidence and limits

The supplied wonderboooo.txt contains a latest 0.9.72 RedCore-package run plus
older runs. Do not mix their process/thread IDs. Latest settings: native target,
bilinear filter, frame generation off, FIFO, inherited cap, nolrz enabled.
Completed/presented FPS match: some light windows reach 60; heavy windows reach
roughly 9–13. That is not sustained 60 FPS gameplay. Clock ratios are near 1.
Renderer wait/readback costs are low in many heavy windows; the completion
worker's long wait is not by itself wasted critical-path CPU time.

CRI Audio Output often consumes most of one core. An older-run snapshot inside
AudioOut2ContextPush also reports that thread sleeping in hrtimer_nanosleep.
A thread name or one stack snapshot cannot prove a guest decode or busy-poll bug.
Measure CPU inside the AudioOut boundary separately before replacing CRI code.

## Changes staged

1. Deadline budgets now start when work starts. A frame that exceeds 16.67 ms
   must not sleep another full 16.67 ms after completion. Rebase at actual starts
   to avoid catch-up bursts. The new overrun regression fails on the old header
   and passes on the new one. Separate guest vblank timing remains intact.
2. Image transitions derive fixed-function destination stages from access masks.
   Shader accesses stay conservative; unknown/generic memory accesses fall back
   to ALL_COMMANDS. Preserve barriers, layouts, ranges, and ordering.
3. One-time Wonder profile targets 60 real FPS, original native rendering,
   framegen off, and clears saved nolrz. Later manual changes remain respected.
   Android thermal protection remains active; 60 is not promised when hot.
4. Audio output reuses thread-local PCM scratch. SDL3 copies submitted bytes;
   buffers are not shared between calling threads. No rate/sample changes.
5. Audio queue backpressure computes bounded 1–5 ms waits from excess queued
   bytes, reducing polling while retaining the queue target and 200 ms stalled
   device recovery. Nonblocking calls still do not sleep.
6. Opt-in NOVA_AUDIO_PROFILE reports per-thread AudioOut CPU/wall time and CPU
   outside that boundary. Enabled for Wonder by the launch profile. Outside
   time includes guest mixing/decoding and other native calls: not decode-only.

## Resource audit

- AnyPS5: https://github.com/boykopovar/AnyPS5 at
  7a25f87620a9b862dc194dd0f659686b0f6cc8b0.
  AudioOut/AudioOut2 include queue pacing and per-context locking. Its x86-64
  relinking architecture does not remove NovaFEX translation on Android ARM64.
  No wholesale backend replacement or unsupported opcode-coverage claim.
- Bachata ARM64 source: https://github.com/zenithblue-oss/shadps4-arm64 at
  be6bc2e9c60799e071dd2fafa6216e8d80ec619c.
  AudioOut uses blocking output synchronization. Native NGS2/AJM work is relevant
  to games using those libraries; the Wonder log does not establish that as its
  CPU bottleneck. Do not transplant unrelated Gravity Rush patches.
- Bachata releases: https://github.com/JICA98/Bachata-S4/releases/tag/v0.2.5
  describe native NGS2, render/cache/barrier fixes and game-specific patches.
- Kyty U59: https://github.com/Jetsku/KytyPS5/blob/main/docs/CHANGES-U59.md
  describes dependency-aware barrier batching, stable depth layouts and caches.
  Full recorder/depth-feedback changes require wider resource-lifetime and
  synchronization validation; they are not silently enabled in this patchset.
- Khronos: https://docs.vulkan.org/samples/latest/samples/performance/pipeline_barriers/README.html
  explains the cost of broad synchronization and narrower stage dependencies.
- SDL: https://wiki.libsdl.org/SDL3/SDL_PutAudioStreamData documents copied input,
  establishing the scratch-reuse lifetime boundary.
- Reddit / PS5 homebrew/jailbreak searches found no reproducible fix for
  PPSA27841's Android ARM64 gameplay slowdown. Hardware overclock/unlock reports
  and unrelated games' patches are not evidence of a fix here.

## Validation completed

Host ASan/UBSan checks: deadline overruns, stalls, pause/resume and 30/60/120 Hz;
image stage combinations and conservative fallback; audio queue units/limits,
CPU accounting and buffer reuse. The patched Image::Transit body compiles with
the pinned Vulkan-Hpp headers. The actual patched QueueSdlAudio body runs against
a deterministic SDL queue, including stalled devices and nonblocking calls.
Production GraphicsSettings compiles/runs with Android stubs and checks the
one-time 60 FPS profile plus inheritance and legacy turbo rejection.

Not completed: full Android native rebuild, device Vulkan synchronization
validation, comparative heavy-scene captures, and sustained 60 FPS verification.
Remaining substantial candidates: resource-safe pass retention/barrier batching,
critical-path CPU scheduling, and measured CRI/AudioOut2 hot-code attribution.
Do not describe all bottlenecks as fixed or add the overlapping scope costs.
