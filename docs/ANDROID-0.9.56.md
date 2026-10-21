# Nova PS5 Android 0.9.56

## Background shader compilation (`patch-0956-async-pipelines.py`)

Graphics pipelines used to compile on the GPU thread, so every new shader combination froze the game (`NOVA_PIPELINE_TIME` up to about 120 ms in owner logs). Eden/yuzu ("asynchronous shaders") and other Kyty-based Android builds (`async_pipelines` option) build them in the background instead.

- A draw whose pipeline is missing queues it on one worker thread. The draw then waits up to `NOVA_ASYNC_WAIT_US` (2000 µs by default), so pipelines already in the driver or disk cache are still used straight away. If the pipeline is not ready by then, the draw is skipped for that frame.
- Never skipped: draws whose shaders write buffers, images or addresses; rect-list and tessellation draws; every draw when `NOVA_ASYNC_PIPELINES=0` (Graphics > Background shader compilation).
- The job owns copies of every input. That includes the compiled-shader metadata, whose storage in the shader cache can move.
- One mutex serializes `CreatePipelineInternal`, because both paths share the pipeline-library maps. The pipeline table itself stays on the GPU thread.
- The worker is joined before any Vulkan object is destroyed.
- Log line every 5 s: `NOVA_ASYNC_PIPELINES: queued=… ready_in_time=… skipped_draws=… pending=…`.

## Readback default back to Relaxed (`patch-0956-readback-relaxed.py`)

0.9.54 made "Off" the default. With Off, a CPU write to a GPU-written page drops the GPU copy without downloading it, so when both wrote the same page one result erased the other. Other Kyty-based Android ports describe this same class of CPU/GPU shared-memory bug. Off also did not raise FPS in the 0.9.54 and 0.9.55 owner logs. It now has to be selected explicitly.

## Safe profile (launcher)

Luna Abyss (PPSA36257) and Super Meat Boy 3D (PPSA31162) booted on 0.9.52 and crash at start since the faster defaults. Without a per-game choice they now get their 0.9.52 settings:

- Accurate sync
- Precise readback
- No write-fault window
- 4K output report
- No periodic submits
- No background shaders

The settings use new versioned keys (`*_v56`), so values saved by 0.9.53–0.9.55 do not carry over.

## Cheaper scaled clears (`patch-0956-raster-clear.py`)

A scaled render pass copies each attachment down to the low-resolution proxy at the start and back up at the end. When the pass clears the attachment, the down copy is skipped. The `NOVA_RESOLUTION_RASTER` log line now includes `cleared_copies_skipped=`.

These two copies per pass are why internal resolution has helped little so far. A real full-scene rescaler would render to low-resolution targets throughout and fix up every consumer (sampling, copies, CPU readback), which is a larger change.

## Heat and clock telemetry (`Telemetry.java`)

Every 5 s the engine log records:

```
NOVA_THERMAL: fps=… thermal=… headroom=… battery_c=… gpu_mhz=… gpu_busy=… cpu_mhz=…
```

The values come from Android's thermal status and headroom, the battery temperature, and the kgsl/cpufreq sysfs entries. Anything Android does not let apps read is logged as `n/a`.

## Validation

`tests/test_0956.py` runs the production worker under normal, ThreadSanitizer and ASan/UBSan builds. It covers in-order single-thread execution, the skip timeout, the blocking wait for non-skippable draws, and draining on destruction. It also checks the switches, the readback default, the structure of the skip path (no render-target or pipeline work before the skip) and the raster counter. The launcher defaults were checked with a JVM test against stubs.
