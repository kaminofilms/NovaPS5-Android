# NovaPS5 0.9.72: resolution compatibility and AMD FSR 1

Native Android ARM64 Kyty plus NovaFEX remains the architecture. This builds on
`build/0971-local-apk` and preserves its timing, frontend, thermal and installer work.
No GitHub Actions runner is used for the local APK.

## Behavior

- Native/1080p/720p/540p/360p targets use temporary raster attachments for eligible
  16:9 color/depth passes. Guest backing images keep their original dimensions;
  compute, storage, unsupported render passes and CPU readback remain native.
  The selector no longer enables the permanent-backing promotion path implicated
  in the supplied Wonder Boy crash. This is a compatibility change, not a proven
  diagnosis of the driver's failure: the original log omitted the Vulkan result.
- Prepared presentation frames use the requested height without supersampling a
  smaller source. Full-frame downsampling replaces the old cropped-copy behavior.
  sRGB-to-UNORM preparation preserves texel bits before resizing, avoiding gamma
  changes. Per-frame intermediates share the prepared-frame ownership lifetime.
- Nearest/Bilinear/AMD FSR 1 output filters and 0/25/50/75/100% FSR sharpness.
  FSR uses AMD's pinned MIT EASU and RCAS implementations, FP32 shaders, explicit
  image barriers and a scratch pair per swapchain image. Acquire waits cover all
  commands; resize teardown waits for the queue before releasing resources.
  Allocation/format/HDR incompatibilities retain normal presentation. FSR is SDR
  only and is not combined with the separate Lossless Scaling frame generation
  path in this build. Zero sharpness bypasses RCAS sharpening, retaining EASU.
- Optional 2x/4x/8x/16x anisotropy applies only to already-anisotropic samplers,
  clamps to device limits, and preserves unnormalized-coordinate restrictions.
- Shader disk identities change to avoid reusing the previous fragment-coordinate
  and push-constant ABI. Vulkan wait failures print the actual result and ticks;
  unsuccessful waits are never reported as completed work.
- All settings apply after restarting a game. No live image reallocation or guest
  clock changes are introduced. Framebuffer scaling remains conditional, so a
  720p selection does not claim every game pass runs at 720p.

## Validation

- Full Android ARM64 Kyty compilation and linking, complete Java/SDL frontend and
  APK signing. Unchanged NovaFEX, optional AnyPS5 backend, framegen and installer
  libraries are preserved from the signed 0.9.71 APK; FFmpeg and SDL are rebuilt.
- Production FSR shaders pass Vulkan 1.1 SPIR-V validation. The exact production
  FSR state passes headless Vulkan tests for constant colors, sRGB conversion,
  sharpness, odd dimensions, bounds, three-slot reuse and reset/resize, with zero
  synchronization validation errors.
- Production raster/pass/emitter commands pass at native/720/540/360p with four
  color attachments and depth, clear/LOAD reuse, native readback and guest-space
  fragment coordinates, with zero synchronization validation errors.
- Production prepared-frame copy commands pass at all four targets for UNORM and
  sRGB input, repeated copies, color preservation and output bounds, with zero
  synchronization validation errors.
- Existing timing, clock-probe encoding, thermal policy and updated Java settings
  tests pass. APK package/version/signature, ARM64 dependencies, alignment,
  compiled feature and bundled-driver checks are required before delivery.

No target-device 0.9.72 game run, RedCore activation, FPS gain, heat reduction or
Wonder Boy/Luna/Ever Forward stability is verified by these host tests.

## Screenshot settings assessment

FSR/sharpness, anisotropy and existing VSync/pipeline-cache options have direct
uses in this Vulkan renderer. The Switch NVDEC/ASTC options describe different
guest hardware and are not added as PS5 controls. Cache-invalidation skips and
GPU-fence bypasses are not transferred. Extra shader-worker threads require a
separate shared-cache concurrency audit and are not exposed as an unimplemented
control. Existing device-supported dynamic-state negotiation is preserved.
