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

## Dead Cells: Accurate sync by default

Dead Cells' 0.9.50 freeze fix (`patch-deadcells-labels.py`) depends on completion labels being written only after the GPU has finished the work before them. 0.9.53's Fast sync publishes labels while packets are processed and turns that Dead Cells path off, so the game can again wait on a label that never matches. That is the same freeze recorded in versionCode 88. Without a per-game choice, Dead Cells now starts with Accurate sync. Every other 0.9.56 change still applies to it.

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

## 0.9.57: Dead Cells freeze, the real cause

Owner logs from 0.9.56 show Dead Cells freezing about 30 s into play every time. It happens with the system Vulkan driver and with Turnip, and with both Fast and Accurate sync. In each case a GPU queue waits on the 64-bit flag `0x20edb76d0` (equal, ref 1, value 0), which nothing in the emulated system sets.

0.7.3 (`feb5fe7`) let such a wait continue after 2 s, and later waits on a remembered address after 100 ms. Dead Cells ran at 60 FPS on 0.8.1 and 53–57 FPS on 0.9.10 with it. 0.9.14 (`dd48245`) removed that give-up for every title, and the freeze has been there in every build since. The Accurate-sync default from 0.9.56 was based on a wrong theory and is reverted: Dead Cells is back on Fast, its 0.9.10 setting.

`patch-0957-deadcells-wait.py` restores the 0.9.10 logic for Dead Cells only. `NOVA_GPU_WAIT_GIVEUP=1` enables it for any title, and `=0` disables it. `tests/test_0957_deadcells_wait.py` executes the production block (thresholds, the remembered-address table, title gating, overrides) in normal and ASan/UBSan builds.

## 0.9.57: Luna Abyss and Super Meat Boy 3D end on their own

0.9.56 owner logs: both titles end during memory setup, before any frame, with the safe profile active. `FORTIFY: pthread_mutex_lock called on a destroyed mutex` shows static destructors running, so the process called `exit()`. Kyty's guest `exit` HLE (libkernel `6Z83sYWFlA8`) calls `::exit` without logging, so the crash backtraces in those logs (`Config::HideCursorEnabled`, `Config::GetVblankFrequency`) are other threads touching state that was already destroyed. Neither title calls an EXIT/abort path. The last device evidence of progress is from the 0.9.36 era (Meat Boy gameplay at about 1 FPS, Luna 959 frames), so the regression lies between 0.9.36 and 0.9.53.

`patch-0957-guest-exit-report.py` prints one report before the exit: the code, the guest return address and the stack modules (module+offset), any text on the stack (8-bit or UTF-16), and the thread's last 16 host calls with return values (new NovaFEX `DumpRecentHostCalls`). It then dumps the kernel memory trace. The exit itself is unchanged. Note: the "24 guest slots" pattern in both logs is the log limit of the slot message, not an allocation limit.

## 0.9.57: Ever Forward deferred write faults

`patch-0957-deferred-write-faults.py` (see its header for the full rules). In the 0.9.56 owner log, 978 of 978 write faults per window were `address_disjoint`, and they cost about 3 s of every 5 s in GPU waits. A qualifying fault now records an asynchronous copy of the page's GPU-written ranges and snapshots their guest bytes. It then releases the page without waiting. A later GPU-thread merge writes the GPU value into every byte the CPU has not changed since. While a merge is pending, uploads skip GPU-owned dirty bytes, and every shortcut treats them as GPU-modified.

The path is on by default only for Ever Forward and only with Relaxed readback; `NOVA_DEFERRED_WRITE_FAULTS=1/0` overrides it. `tests/test_0957_deferred_write_faults.py` executes the production upload exclusion and merge (clean merge, CPU-kept bytes, re-dirtied page, pending copy, already-downloaded range, unreadable memory) in normal and ASan/UBSan builds, and checks the structural guards. The log line is `NOVA_DEFERRED_WRITE_FAULTS: deferred=… merged=… cpu_kept=… dropped=… pending=…`.

## 0.9.57: Turnip workaround setting

Graphics > Turnip driver workaround sets `TU_DEBUG` before the driver loads: off, `nolrz`, `sysmem`, or both. It is for GPU hangs and device loss such as Wonder Boy's; the system driver ignores it.
