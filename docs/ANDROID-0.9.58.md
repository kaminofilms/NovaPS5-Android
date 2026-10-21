# Nova PS5 Android 0.9.58 (versionCode 112)

## Lossless Scaling frame generation

Uses the owner's own `Lossless.dll` from Lossless Scaling (Steam). Nova never ships it, and the
APK check fails if one is packaged.

* **Import:** Settings → *Lossless Scaling DLL* (Android file picker). The file must be a Windows PE
  (`MZ`) of at most 256 MB. It is copied to `files/lsfg/Lossless.dll` in app storage and can be
  replaced or removed there.
* **Per-game Graphics settings:**
  * *Frame generation*: Off / 2x / 3x / 4x.
  * *Flow scale*: 100/75/50/35/25 %; the default is 50 %.
  * *Performance mode*: default on.
* **Environment set by the launcher:**
  * `NOVA_FRAMEGEN=2..4`
  * `NOVA_LSFG_DLL`
  * `NOVA_FRAMEGEN_FLOW`
  * `NOVA_FRAMEGEN_PERF`
  * `NOVA_PRESENT_MODE=fifo`, forced while frame generation is on.

  If frame generation is selected but no DLL has been imported, nothing is set and the boot log
  says so.
* **Library:** `libnovalsfg.so` is built from lsfg-vk-android (pinned `3e89e54`), which is
  lsfg-vk 1.0.0 plus Android AHardwareBuffer sharing, both MIT. Nova's patch makes the
  frame-generation Vulkan instance use the same driver as the game (Turnip through adrenotools, or
  the system driver). The library exports only `nova_lsfg_*`. Shaders are read from the user's DLL
  and translated from DXBC to SPIR-V at start.
  * Later lsfg-vk releases are CC BY-NC-ND and are not used.
  * If this library fails to build in CI, the APK ships without it, and frame generation reports
    `off (dlopen …)`.
* **Presenter** (`native/novalsfg/novaFramegen.h`, applied by `tools/ci/patch-0958-framegen.py`):
  1. In the normal present command buffer, the finished game frame is blitted into one of two
     shared input images (AHardwareBuffer, RGBA16F).
  2. After that submit completes, the frames are generated (`presentContext` + `waitIdle`).
  3. Each generated frame is blitted into its own swapchain image and presented. The real frame is
     presented last.
  4. Presents are spaced at `interval / multiplier`. The interval is an EMA of the real-frame
     interval, clamped to 4–100 ms, so the total wait stays under one real frame.
  5. The swapchain is given at least `multiplier + 1` images.

  Any failure prints `NOVA_FRAMEGEN: off (<reason>)` once, and the game continues on the normal
  path.
* **Log:**
  * `NOVA_FRAMEGEN: initialized …`
  * `NOVA_FRAMEGEN: on Nx at WxH …`
  * Every 5 s: `NOVA_FRAMEGEN: generated=… real=… generate_ms_avg=…`

**Limits:** frame generation does not raise the game's own frame rate, and input lag rises by about
one real frame. Pick a multiplier so that real FPS × multiplier ≤ the display refresh rate. If the
DLL's shader resources do not match lsfg-vk 1.0.0, the log says which shader is missing.

## Guest `puts()` echo

libc `puts` text is also written to the log as `NOVA_GUEST_PUTS: <text>`. This captures the 28-character
message that Luna Abyss and Super Meat Boy 3D print just before
`KernelDebugRaiseExceptionOnReleaseMode(0xa0020005)` and `exit(0)`.

## Tests

* `tests/test_0958_framegen.py`: patched-tree structure, ordering and pacing.
* `tests/verify_native_apk.py`: libnovalsfg exports, and no DLL in the APK.
* `tests/verify_performance_features.py`: new markers.
* Local checks not run in CI:
  * Host and Android-mode (stub headers) builds of libnovalsfg.
  * Error-path test.
  * A Java test of the settings/env mapping.
