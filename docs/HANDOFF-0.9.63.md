# Nova PS5 Android: handoff at 0.9.63 (for another AI assistant)

**Repository:** `kaminofilms/NovaPS5-Android`. Moved from `kaminofilms/novaps5-android`; both URLs work.

**Branch:** `perf/0952-eop-drain`. The CI workflow `.github/workflows/android-native.yml` runs only through `workflow_dispatch`:

```
gh workflow run android-native.yml --ref perf/0952-eop-drain -R kaminofilms/NovaPS5-Android
```

**Release tag:** each run publishes a prerelease `v<version>-android-<sha7>`. Its logs go to the `lab-logs` branch under `runs/android-<run id>-<sha8>/`.

**Owner's device:** Red Magic 11 Pro (nubia NX809J), SM8850 / Adreno 840, Android 16. Turnip `v26.3.0-20261012-A8xx` is bundled; the System (Qualcomm) driver is also selectable.

**Owner's rules (must follow):**
- Ask before starting any APK build.
- Prefer large, pre-tested batched builds.
- Keep the same signing key (`tools/ci/novaps5-ci-test.keystore`).
- Research root causes and cite sources.
- Never bundle or distribute Lossless.dll. The owner imports their own copy.

## How the code is built

Nova is Kyty (`KYTY_COMMIT`), patched at build time by Python overlays in `tools/ci/patch-*.py`. Each overlay asserts its text anchors, and each has a structural test in `tests/test_*.py`. The order is set in `tools/ci/build-android-kyty.sh`.

Other components:
- **NovaFEX** (x86-64 → arm64, FEXCore): `native/novafex/`. Diagnostics live in `novafex.cpp`: freeze reports, `NOVA_THREAD_CPU`, stack dumps.
- **Frame generation:** `native/novalsfg/`. It is built from lsfg-vk-android 3e89e54 (MIT) by `tools/ci/build-android-lsfg.sh`, and the CI build now fails if the library is missing.
- **Launcher (Java):** `nova-android/src/com/kaminofilms/novaps5/`. `GraphicsSettings.java` maps per-game settings to environment variables.

**Local checks without an NDK:**
1. Apply the patches to a copy of the Kyty tree.
2. Run `clang++ -std=c++20 -fsyntax-only -D__ANDROID__ -DKYTY_ANDROID -DVK_USE_PLATFORM_ANDROID_KHR` with stub Android headers.
3. The only expected errors are the missing `GPU_*_SPV` shader symbols.

Java is tested with stub `android.*` classes and javac.

## What happened, 0.9.56 → 0.9.62

| Version | Change | Result on device |
|---|---|---|
| 0.9.57 | Dead Cells WAIT_REG_MEM give-up restored; Ever Forward deferred write faults; guest exit report; Turnip workaround setting | Dead Cells fixed (owner confirmed) |
| 0.9.58 | guest `puts()` echo; Lossless Scaling frame generation (user DLL) | lsfg library failed to compile (missing `VK_USE_PLATFORM_ANDROID_KHR`) |
| 0.9.59 | lsfg build fix; lsfg build now required | Frame generation works, about 3 ms per generated frame. Real FPS fell 12–15 → 8 because pacing slept on the flip thread. |
| 0.9.60 | Pacing moved to `VK_GOOGLE_display_timing`; diagnostics `NOVA_GPU_TIME` (Vulkan timestamps), `NOVA_PASS_BREAK` (EndRendering call sites), `NOVA_THREAD_CPU` | Diagnostics work |
| 0.9.61 | Pass merging: skip redundant PM4 global barriers inside a pass; deferred-write-fault downloads at pass end; Unreal `/app0/ue4commandline.txt` virtual empty file; busy-thread stack dump | Passes ended halved (Ever about 11k → 6k per 5 s), but FPS unchanged. Super Meat Boy 3D now gets in-game (about 6 FPS), then stalls with low free RAM. |
| 0.9.62 | GPU turbo; 2x2 variable-rate shading; real GPU timestamps; frame-pointer stack walk | **Ever Forward 12 → 20–25 FPS, Wonder Boy 9–10 → 12–24.** All three active on Turnip (`NOVA_VRS: 2x2 ... pipelineFragmentShadingRate=1`). Ever GPU now about 74% busy. Phone gets hot (worst in Wonder Boy). Internal resolution gives no FPS (it reaches about 8% of draws). |
| 0.9.63 | Event-loop spin fix; read-to-read image barrier skip; Unreal DCC fill absorb; Luna/Super Meat Boy report 1080p | **Needs a device test** |

## Key measurements (0.9.61, Turnip)

**Ever Forward (PPSA04703, Unity):**
- About 12 FPS.
- `NOVA_GPU_TIME` 86–88% busy, about 72 ms GPU per frame.
- Render thread about 30–45% of one core; guest threads are not saturated.
- **The limit is the phone GPU.**

**Wonder Boy (PPSA27841, Unity):**
- 9–10 FPS, GPU 90–92% busy.
- It renders 3840x2160 even though Nova reports a 1080p display (`VideoOutGetOutputStatus` returns 1080p when `NOVA_VIDEO_OUT_4K` is not set).
- The resolution scaler reaches only about 13% of draws.

**Nova's resolution scaler (`NovaRaster`, 0.9.54):**
- Only 16:9 passes ≥540p with no stencil, no storage/BDA writes, no feedback, and `CanRasterScale`.
- It renders at a smaller size, then blits down and up.
- Most Unity passes fail these conditions; stencil (deferred lighting) is the likely reason.

**A host thread at 100% of one core** in every title:
- It is the lowest Kyty `SDLThread` tid, not a guest thread.
- The 0.9.61 stack dump shows it inside vdso `clock_gettime` called from libc, so it is a loop that keeps reading the clock.
- 0.9.62 walks the frame-pointer chain (`NOVA_FEX:   fp#NN module+offset`). libmain.so ships unstripped, so offsets can be symbolized with `llvm-symbolizer` against the release APK's `lib/arm64-v8a/libmain.so`.
- It is not the VideoOut present thread, `SleepMicro` (clock_nanosleep) or the SDL event loop (ALooper wait).

**Luna Abyss (PPSA36257) and Super Meat Boy 3D (PPSA31162), Unreal:**
- They exited with "File root is /devlog/app/" and then "GEngineLoop.PreInit Failed!".
- **Cause:** a missing `/app0/ue4commandline.txt`, which Unreal uses to pick `/app0` as its file root. Sources: [AnyPS5 discussion #6275](https://github.com/boykopovar/AnyPS5/discussions/6275), and "Best Practices For Running On The PS4" (cnblogs AnKen), which says a blank file is enough.
- Fixed in 0.9.61. Both now boot, slowly.
- Super Meat Boy then stalls after about 2 minutes: every guest thread is in a condvar wait, `RHIFrameFlipThread` is in a timed wait, and free RAM is down to about 500 MB.
- They use the "safe" profile: 4K output, precise readback, accurate sync. Next step: try the normal profile for them.

## 0.9.62 contents (`tools/ci/patch-0962-gpu-boost.py`, `tests/test_0962_gpu_boost.py`)

1. **`NOVA_GPU_TURBO=1`** (default on): sets KGSL `PWRCTRL` to 0 via `IOCTL_KGSL_SETPROPERTY`, the same call as `adrenotools_set_turbo`.
   - It is re-asserted every second, as in Eden's turbo mode (SharpDroid `docs/vulkan.md` describes it).
   - A launch without turbo clears it.
   - Log line: `NOVA_GPU_TURBO`.
2. **`NOVA_VRS=2`** (default on for PPSA04703 and PPSA27841): `VK_KHR_fragment_shading_rate` pipeline rate as dynamic state, set per draw.
   - 2x2 only for 1-sample colour passes of at least 1280x720 that are not video-out images.
   - HUD/display, MSAA and depth-only passes stay 1x1.
   - It is enabled only if `pipelineFragmentShadingRate` and a 2x2 one-sample rate are reported.
   - **Unverified:** whether the bundled Turnip exposes it. The log says `NOVA_VRS: ...`. If it is unavailable, try the System driver.
   - Log line: `NOVA_VRS_REPORT draws_2x2 / draws_1x1`.
3. **`NOVA_REAL_GPU_TIME=1`** (default on for the same two titles): GPU timestamps (fast EOP labels and COPY_DATA reference clock) are written at packet time, then rewritten in a priority operation after the GPU finishes that command buffer.
   - Rationale: yuzu's "Use Fast GPU Time" reports a fast GPU so dynamic-resolution games stay at maximum resolution (yuzu progress report, August 2021). Nova's fast labels do the same by accident.
   - Whether Ever Forward and Wonder Boy use dynamic resolution is **unknown**. Look for a changing `NOVA_RESOLUTION` render area, or for FPS changes.
   - Log line: `NOVA_GPU_TIMESTAMPS`.
4. NovaFEX stack dumps walk the frame-pointer chain.

All three are per-game Graphics settings, so the owner can turn each off.

## Research notes: how other emulators reduce GPU work

- **RPCS3 (PS3):**
  - Resolution scale applies through the surface cache to render targets above a "minimum scalable dimension".
  - Shaders and coordinates are adjusted per surface.
  - Many speed options trade accuracy, e.g. write-colour-buffers off and ZCULL approximate.
- **yuzu/Eden/Citron (Switch):**
  - A real resolution rescaler: render targets are allocated scaled, and the shader recompiler patches `gl_FragCoord`, texel fetches and image ops for rescaled textures, with per-game blacklisting.
  - Downscaling to 0.5x or 0.75x for performance.
  - "Fast GPU Time" (see above).
  - GPU accuracy "normal" skips some sync work.
  - Turbo mode via KGSL.
- **Nova's per-pass blit scaler** is much cheaper to build but reaches few passes. The long-term fix for GPU-bound games is a yuzu-style rescaler: scaled image allocation plus shader patches for FragCoord, texelFetch and imageLoad/Store, and textureSize queries.

## 0.9.62 device results that drove 0.9.63

**The 100% host thread is now identified.** The frame-pointer stack was:

```
libmain HostInputWaitEvent -> SDL_WaitEventTimeout -> (SDL events) -> SDL_UpdateJoysticks -> SDL_GetTicks -> clock_gettime
```

SDL3's Android wait loop pumps joysticks without blocking.

**Ever Forward** at 20 FPS:
- `NOVA_PASS_BREAK` shows `image.cpp:237` (`Image::Transit`) causing about 15,500 pass ends per 5 s, about 155 per frame.
- `commandScheduler.cpp:446` (submit) about 5,000 per 5 s.
- About 64 command buffers per frame.

**Super Meat Boy 3D:**
- 1–2 FPS.
- The GPU thread spends about 3.8 s of every 5 s in readbacks: `readback_read` with about 280 calls and a 426 ms maximum.
- `readback_caller=TextureMetadata` accounts for 35–45 MB per 5 s. That is `TextureCache::MaterializeColorClear` downloading GPU-written DCC/CMask metadata.
- Unreal writes it with a constant-fill compute shader. SharpEmu `ConstantFillDetector.cs` (GPL-2.0-or-later) documents this; Nova's own implementation is independent.
- It also reported a 4K display because of the safe profile.

**Wonder Boy:**
- The CRIWARE audio thread uses about 96% of a core mixing a 12-channel (7.1.4) AudioOut2 port, with "Voice buffer underrun".
- Not changed yet. Next idea: check whether the game honours a stereo or 8-channel speaker report.

## 0.9.63 contents

- **`patch-0963-cpu-thermal.py` (`tests/test_0963_cpu_thermal.py`):**
  - On Android, `HostInputWaitEvent` uses `SDL_PollEvent` plus `SDL_Delay` of up to 4 ms (`NOVA_EVENT_POLL_MS`).
  - `Image::GetBarriers` (whole-image state only) skips a barrier when the layout stays the same and both old and new access are read-only. It merges the stages and accesses into the tracked state, so a later write waits for every reader.
  - Log line: `NOVA_IMAGE_BARRIERS`. `NOVA_IMAGE_BARRIER_MERGE=0` restores 0.9.62.
  - Per-subresource states are deliberately excluded, because that branch rewrites the tracked state afterwards.
- **`patch-0963-unreal-dcc.py` (`tests/test_0963_unreal_dcc.py`):**
  - The texture cache records colour-metadata ranges in `MaterializeColorClear`.
  - In `TryConsumeComputeImageClear`, a uniform buffer fill (`ResolveComputeBufferFill`) that is not a whole-image clear, and lies wholly inside a known colour-metadata range with no pending GPU writes, is written to guest memory by the CPU (`InvalidateMemory` + `WriteBacking`). The dispatch is then skipped.
  - Log line: `NOVA_DCC_FILL absorbed / ran_on_gpu`. `NOVA_DCC_FILL_ABSORB=0` restores 0.9.62.
  - **Unverified:** whether Super Meat Boy's fill shader is recognised by Kyty's `uniform_fill` analysis. If `NOVA_DCC_FILL` stays at 0/0, port SharpEmu's pattern detector (v_lshl_add_u32 / s_buffer_load_dword / v_mov_b32 / buffer_store_format_x).
- **Launcher:**
  - The console video output setting moved to key `video_out_v63`, default 1080p for every title, including the safe-profile Unreal titles (they were 4K).
  - Old `video_out_v56` choices are ignored.

## Next steps

1. Owner tests 0.9.62 on Ever Forward and Wonder Boy. Check:
   - `NOVA_VRS`, `NOVA_GPU_TURBO`, `NOVA_GPU_TIMESTAMPS`
   - `NOVA_GPU_TIME` busy %
   - FPS
   - render area changes
2. Symbolize the 100% host thread from the `fp#` lines and fix the spin.
3. Super Meat Boy / Luna: memory pressure and the stall; try leaving the safe profile.
4. If VRS is unavailable on Turnip, test the System driver, or extend NovaRaster to stencil passes. Better still, start a yuzu-style rescaler.

## 0.9.63 device results (owner, Red Magic "rise" performance mode)

- **Spinning-core fix works.** The `SDLThread` at 100% is gone in every title (cooler).
- **Unreal DCC absorb works.**
  - Super Meat Boy: `NOVA_DCC_FILL absorbed=462 ran_on_gpu=50`, and TextureMetadata readbacks fell from about 280 to 55 per 5 s.
  - But Super Meat Boy is still 2–5 FPS, with the GPU 76% busy, so the next bottleneck is elsewhere. Look at `NOVA_RENDER_COST` readback_read/wait and `NOVA_PASS_BREAK` in its log.
- **Luna Abyss now gets past loading:** 5 → 15 FPS while loading, `absorbed=914`. A new milestone.
- **Read-to-read barrier skip does nothing:** `read_to_read_elided=0` in every log.
  - The condition in `NovaReadToRead` never matches. Kyty's tracked access masks probably always contain a write bit (e.g. `eMemoryWrite` or an attachment write), or the transitions are real read↔write changes.
  - **Next:** log a histogram of the old/new access, layout and stage at `Image::Transit` call sites to see what the ~155 per frame transitions really are.
- **Wonder Boy:** 12–15 FPS, GPU 73%. The CRIWARE audio thread is still at 94% of a core (12-channel AudioOut2).
- **The owner reports no FPS gain from 0.9.63 in any title.** On the phone's "balanced" mode they run slower; use performance ("rise") mode.
- **Owner request: an "auto max FPS" profile.** Proposed defaults per title:
  - present FIFO, GPU turbo on, VRS 2x2 on, real GPU time on, internal resolution Native, video out 1080p
  - frame generation off
  - FPS cap 30 for Wonder Boy (heat)

## Prepared for 0.9.64 (committed, NOT built; ask the owner before building)

- `tools/ci/patch-0964-transit-histogram.py`: diagnostic `NOVA_TRANSITIONS` lines, the top 8 (layout, access) old→new pairs of emitted image barriers every 5 s. Compiles in Android mode.
- The workflow is already bumped to 0.9.64 / versionCode 118. Update the release notes text before building.
- **Use it to fix the read-to-read skip.** Decode the access flags; for example, 0x20 is SHADER_READ and 0x100 is COLOR_ATTACHMENT_WRITE. If the top pairs are COLOR_ATTACHMENT_WRITE→SHADER_READ, those barriers are real; look at render-target-as-texture patterns instead.

## Research to do next (owner asked: Unreal / Unity / emulator sources)

1. **Unity games (Ever Forward, Wonder Boy):**
   - Check whether either game uses `ScalableBufferManager` dynamic resolution. A changing render area in `NOVA_RESOLUTION` with `NOVA_REAL_GPU_TIME=1` would show it.
   - If not, the real fix is a **yuzu-style resolution rescaler**: allocate render targets scaled; in the shader recompiler, patch `gl_FragCoord`, texelFetch/imageLoad coordinates and textureSize for rescaled images; blacklist targets that fail.
   - Nova's NovaRaster blit scaler reaches only about 8–13% of draws. Stencil passes are the main exclusion.
2. **Unreal (Super Meat Boy 2–5 FPS, Luna about 15):**
   - Profile their remaining readbacks and waits (`NOVA_RENDER_COST`, `readback_caller`).
   - Port SharpEmu's `BoundedFillDetector` / `ComputeImageClear` (GPL-2.0-or-later, compatible with Nova) for fills Kyty's `uniform_fill` misses (`ran_on_gpu=50`).
   - Consider leaving the safe profile (Precise readback, Accurate sync) for these titles now that the real PreInit cause is fixed.
3. **Wonder Boy audio:** CRIWARE mixes 12 channels (AudioOut2 7.1.4) at 94% of a core. Check how AnyPS5 (`boykopovar/AnyPS5`) and shadPS4 report AudioOut2 speaker info and port formats, and whether a game accepts 8 or 2 channels.
4. **Adreno 840 / Turnip:**
   - Test the System (Qualcomm) driver against Turnip for each title.
   - Test `TU_DEBUG` variants.
   - Check SharpDroid's `docs/vulkan.md` notes on memory types: HOST_CACHED staging buffers make guest stores much cheaper.
5. **Auto max-FPS profile** (owner request): one launcher button applying, per title:
   - FIFO present, GPU turbo, VRS 2x2, real GPU time
   - Native internal resolution, 1080p video out
   - frame generation off
   - an FPS cap of 30 where the game swings above 30 (Wonder Boy, for heat)

## CapyPS5 v0.0.1 source review (owner supplied the source; GPL-2.0, KytyPS5 + FEX, the same base as Nova)

**Source:** <https://git.capyps5.org/CapyPS5/CapyPS5>, tag `v0.0.1`; mirror `github.com/Ghael-V/CapyPS5`. Its licence is compatible with Nova's GPL-2.0. Credit it when porting.

They report Dead Cells, Blasphemous, Animal Well, Greak and Isaac at 60 FPS on an AYN Odin 3 (Adreno 830, system driver). Unreal games start at 25% resolution.

**Owner decision: do NOT copy CapyPS5 code.** Use it only as evidence of what is possible. Nova writes its own implementations, designed below from general, well-documented techniques (yuzu's rescaler concept, Vulkan specialization constants).

**What they have, in priority order (for reference only):**

1. **A real resolution scaler. This is the feature Nova lacks.**
   - `core/src/graphics/host_gpu/renderer/cache/textureCache.cpp`: `TextureCache::ResolutionScale()` and `ChooseScale(desc)`. These scale RenderTarget, DepthTarget and VideoOut 2D colour images that are 1-sample, 1-mip and ≥1280x720. Their comment explains why display buffers must be scaled too (Greak).
   - `image/image.cpp`: `IsScaled()` paths, around lines 404 and 447.
   - Shader side: specialization constant `IR::ResolutionScaleSpecId = 100` (`ir/ShaderIR.h`), used in `backend/spirv/spirvEmitterFlow.cpp` (FragCoord, around lines 50 and 148), `spirvEmitterImage.cpp` (texel coordinates, around 186–198) and `spirvEmitterMesh.cpp` (`ResolutionScale()`). It is set in `pipeline/shaders.cpp`.
   - `renderCompute.cpp:153`: compute dispatches over scaled images.
   - The Android launcher has a per-game "Resolution scale", with a separate default for Unreal games (25%). See `android/app/.../Settings.kt` `ueResolution()` and `GameItem.isUnreal`, which detects `ue4commandline.txt`/`uecommandline.txt` or an engine folder.
   - This replaces Nova's NovaRaster blit scaler, which reaches only about 8–13% of draws.
2. **Video-out 1080p report** (`videoOut.cpp`, around line 1820). Nova already does this (`NOVA_VIDEO_OUT_4K`). Their note: Unreal rendered 4800x2700 for a "4K" output.
3. **Unreal yield backoff** (`kernel/pthread.cpp` `SchedulerBackoffOnce`): "Unreal polls completion with millions of guest yields". An optional short sleep after 32 yields within 2 ms (`debug.capy.yield_us`) saves power and heat.
4. **Unreal memory layout:**
   - `kernel/memory.cpp` (comments around lines 195, 1213, 3867, 3934, 3992) and `memoryAddressSpace.inc`.
   - UE4 reserves 512 GiB, UE5 reserves 256 GiB at a fixed address, and Unreal hands out pools 128 GiB apart.
   - Compare with Nova's guest-VA folding when debugging Super Meat Boy and Luna.
5. **`cpu/cpuBackend.cpp`** (around lines 458 and 475): JIT notes that Unreal's render thread is about 10%. Compare their FEX configuration with NovaFEX.
6. **Dead Cells at 60 FPS:** diff their `guest_gpu/graphicsRun.cpp`, the EOP/label and WAIT_REG_MEM paths, against Nova's `patch-0957-deadcells-wait.py` and the fast-label path. They use the system driver on an Adreno 830.

## Nova's own resolution scaler (design; implement as `tools/ci/patch-0964-nova-rescale.py`)

**Goal:** GPU-bound titles render their large targets at S×S of guest size (S = 0.5–0.75; Unreal defaults to 0.5). That cuts pixel work by 1/S², without the per-pass blits of NovaRaster.

1. **Which images to scale.** Decide once, when the texture cache creates an image:
   - 2D colour or depth/stencil images used as render or depth targets, or video-out images
   - 1 sample, 1 mip, extent ≥1280x720
   - Store `scale` on the Image and allocate the backing at `ceil(w*S) x ceil(h*S)`.
   - Never scale images that are also written or read by the CPU path, uploaded from guest memory, or used as storage (imageStore), and never block-compressed images. Those keep S = 1.
2. **Every consumer must agree.** When an image is used as an attachment, scale the render area, viewports and scissors by its S. A draw whose attachments disagree on S falls back: rebuild that pass at S = 1 by blitting scaled images up, then log it.
3. **Shader side.** Add our own specialization constant for scale (pick an unused ID and document it) to the fragment, vertex and compute shaders the recompiler emits:
   - Fragment `FragCoord.xy` is divided by S, so the guest sees guest-size coordinates.
   - Integer texel fetches and `imageLoad`/`imageSize`/`textureSize` on a scaled image are multiplied or divided by S. This needs a per-binding "scaled" flag, so make it a push-constant bitmask rather than per-pipeline.
   - Normalised sampling (UV) needs no change.
   - Pipelines are specialised by the scale value; cache keys must include it.
4. **Readback and CPU paths.** When guest memory of a scaled image must be read by the CPU (downloads, `MaterializeColorClear`, video-out presentation), blit it to a native-size temporary first. Track that per image so it only happens when needed.
5. **Presentation.** Video-out images are scaled too, and the presenter blits them to the swapchain with linear filtering. Without this, a game that draws into a display buffer while a scaled depth buffer is bound renders into only part of it.
6. **Settings.** Per-game "Resolution scale" (Native / 75% / 50% / 33%), with an "Unreal default" (detect `ue4commandline.txt`/`uecommandline.txt` or an engine folder in the game folder). Environment variable `NOVA_RESCALE_PERMILLE`. Log `NOVA_RESCALE: scaled_images= fallbacks=`.
7. **Tests.**
   - Structural tests for each patch.
   - A host test of the extent rounding and the fallback rule.
   - On device: Ever Forward and Wonder Boy at 50%; check `NOVA_GPU_TIME` and the FPS; look for wrong coordinates (UI offset, shadows misaligned).

Remove NovaRaster (the 0.9.54 blit scaler) once this works.

Ask the owner before building.
