# Nova PS5 0.9.15 Android shader feature compatibility

This native Android build retains NovaFEX and Kyty, including the limited
AnyPS5-derived completion and shader-fence adaptations documented in
[ANYPS5-GPU-INTEGRATION.md](ANYPS5-GPU-INTEGRATION.md). It does not replace
Kyty with AnyPS5's renderer or use a separate AnyPS5 boot mode.

## Device evidence

The user's 0.9.14 system-Vulkan log from nubia NX809J / SM8850 / Android 16
shows Super Meat Boy 3D (`PPSA31162`) reaching PM4 compute dispatch and then
failing `vkCreateComputePipelines` in `shaders.cpp:619`. The excerpt omits
the actual Vulkan result and failing shader requirements. The earlier
four-second report is followed by more shader compilation, so it does not
establish a permanent empty-queue stall. No game frame is confirmed.

Luna Abyss (`PPSA36257`) reaches one vertex shader, eight compute shaders and
audio initialization in the supplied excerpt. That excerpt contains no
fatal error. It does not establish the same compute-pipeline failure.

## Implemented correction

The existing backend can emit native 64-bit LDS atomics using Workgroup
memory with explicit layout. Device initialization permits drivers without
the needed optional features, but shader selection previously did not
consult them. This build selects the existing storage-buffer LDS backend
for compute shaders using 64-bit shared atomics when either enabled
`shaderSharedInt64Atomics` or `workgroupMemoryExplicitLayout` is absent.
Ordinary LDS stays in Workgroup memory; the existing shared-memory-size
fallback remains intact. Storage-buffer 64-bit atomics use the already
required `shaderBufferInt64Atomics` feature.

The emitter's effective storage class now also controls descriptor-limit
validation. Both LDS size fallback and native-atomic profile enter the
compute-program cache key, preventing incompatible variant reuse.
No dispatch, wait, pipeline failure or GPU completion is treated as success.

This corrects a real capability-selection defect. The device log does not
prove that the rejected shader uses this feature, so this is not yet a
confirmed fix for either game. A failure now prints the exact Vulkan result,
shader hash, workgroup dimensions, wave/subgroup size, LDS backing and
64-bit/derivative requirements in `NOVA_COMPUTE_PIPELINE_FAILED`.

## Source and verification

`patches/kyty-android-shader-features.patch` modifies eight effective Kyty
files and is applied by `tools/ci/build-android-kyty.sh` after the 0.9.14
completion overlay. Android CI compiles this patched Kyty checkout, not the
repository's historical vendor snapshot. No additional AnyPS5 files are
copied in this follow-up. Existing notices and corresponding-source release
archives are retained.

`tests/test_shader_features.py` compiles extracted production selection,
emitter-constructor and cache-key code, checks all eight feature and backing
combinations, and verifies vertex-stage isolation. With spirv-tools it also
validates a storage-buffer 64-bit atomic compute module targeting Vulkan 1.1.
The workflow runs this alongside existing startup, PM4 completion and shader
memory-fence checks before compiling and packaging ARM64 Android code.

Device follow-up should capture `NOVA_SHADER_FEATURES` and, if present,
`NOVA_COMPUTE_PIPELINE_FAILED`, plus the complete fatal tail. Neither game
nor Dead Cells has been run in this development environment. Resolution
scaling and FSR remain unavailable; the existing presentation FPS cap remains.

Vulkan's storage-class-specific atomic requirements are specified in
[Runtime SPIR-V validation](https://docs.vulkan.org/refpages/latest/refpages/source/RuntimeSpirv.html)
and the [Vulkan atomics guide](https://docs.vulkan.org/guide/latest/atomics.html).
