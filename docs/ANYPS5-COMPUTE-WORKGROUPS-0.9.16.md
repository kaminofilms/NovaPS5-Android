# Nova PS5 0.9.16: compute workgroup lowering

## Evidence and scope

The user's 0.9.15 system-Vulkan test on nubia NX809J / SM8850 / Android 16
still fails Super Meat Boy 3D (`PPSA31162`) at `vkCreateComputePipelines`:

```
result=ErrorUnknown (-13) hash=0xd1a9115d6e0e3be6
local=4x4x4 guest_wave=64 host_subgroup=64 lds_bytes=0 storage_lds=0
shared_i64=0 buffer_i64=0 fp64=0 derivatives=0
```

This rules out the 0.9.15 LDS-atomic fallback as the cause of this shader's
failure. It establishes a pipeline rejection, not its exact internal driver
cause. A 4x4x4 workgroup and required subgroup 64 can be legal Vulkan.
The early four-second watchdog report precedes more compilation; its
disabled GPU-write trace ring is not proof of absent GPU execution.

This release adapts another coherent compiler component from AnyPS5's
workgroup lowering architecture into the existing Kyty compiler. It does
not import the full AnyPS5 renderer/compiler or establish a game menu boot.

## Implemented behavior

- Compute workgroups with multiple Y/Z invocations are emitted with a
  canonical 1D physical shape when the entire group fits the device's
  `maxComputeWorkGroupSize[0]`. The rejected shader's 4x4x4 shape becomes
  64x1x1. Workgroup membership, dispatch counts and guest dimensions remain.
- Guest LocalInvocationID is reconstructed from LocalInvocationIndex using
  the original X/Y/Z dimensions. GlobalInvocationID is reconstructed from
  that local ID plus WorkgroupID times the original dimensions. This extends
  the existing paired-wave remapping rather than merely changing LocalSize.
- The existing paired wave64-on-32 lowering remains intact. Compute quad
  derivatives retain their native arrangement. Over-limit groups retain
  their original shape. No thread is deliberately skipped or duplicated.
- The device's X limit enters the compute cache key. Pipeline creation
  requests the host subgroup actually selected for compilation, rather
  than unconditionally requesting the guest wave size. Supported wave32
  shaders record a 32-wide host when that size is requested.
- Android validates generated shader SPIR-V with the already linked
  SPIRV-Tools before creating Vulkan modules. Validation failures print
  `NOVA_SPIRV_INVALID` with hash and exact validation messages. Pipeline
  failures remain fatal, with the actual required subgroup and linear
  layout selection included in the failure record. Nothing fakes completion.

The canonical layout is a semantics-preserving compiler compatibility
path, not a proven explanation for Adreno's ErrorUnknown. Device testing
must determine whether it resolves this particular pipeline rejection.

## AnyPS5 reference and license

Reference repository: https://github.com/boykopovar/AnyPS5
Reference commit: `131171e77218a26d5746a8074a8216ec66f4dcb0`.

Components studied/adapted:

- `core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvInputOutput.cpp`:
  guest invocation-index and coordinate reconstruction.
- `core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvEmitterHelpers.cpp`:
  adding LocalInvocationIndex and WorkgroupID to remapped stages.
- `core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvModuleSetup.cpp`:
  physical local-size emission distinct from guest dimensions.
- `core/libs/prx/libSceAgcDriver/Execution/src/VulkanDevice.cpp`:
  compiler-selected host subgroup agreement with compute pipeline creation.

AnyPS5's original two-lane implementation is extended here to canonical
single-lane compute layouts. This is not a verbatim whole-file import.
GPL-2.0 and existing Kyty MIT notices remain; attribution stays with the
AnyPS5 contributors. Existing corresponding-source archives accompany the
binary, including these exact patched sources and build scripts.

## Build and tests

The Android workflow builds the external pinned and patched Kyty checkout,
not `vendor/kytyps5`. `kyty-anyps5-compute-workgroups.patch` is checked and
applied after the 0.9.14/0.9.15 overlays. Eight production files are changed.

`tests/test_compute_workgroup.py` compiles the actual production layout
predicate, SPIR-V LocalSize emission, logical-index helper and coordinate
emission against an SSA evaluator. It checks 984 local/global coordinates,
the reported 4x4x4 case, non-power-of-two dimensions, paired wave64, device
limits and overflow exclusion, and derivative preservation. Existing shader
profile/cache, SPIR-V atomic/fence and PM4 completion tests remain required.
These tests establish mapping correctness, not Adreno driver acceptance.

VersionName is `0.9.16-android`, versionCode 64. Native Android ARM64,
NovaFEX, SDL3, AAudio, package identity and signing key are retained.
The previous EOP completion and shader memory-fence changes remain.

## Remaining limits and next logs

No game is executed in CI. Super Meat Boy 3D and Luna Abyss menus remain
unverified; Dead Cells performance regression remains untested. The
synchronous EOP fallback can reduce performance. Internal resolution, FSR
and sharpening remain unavailable; presentation FPS caps and bilinear
presentation remain functional.

For the next device run, inspect the first `NOVA_SPIRV_INVALID` or
`NOVA_COMPUTE_PIPELINE_FAILED` record and full fatal tail. A valid module
can still be rejected by a driver or violate device-specific limits;
SPIR-V validation alone is not a successful GPU execution test. If this
same hash still fails, obtain its actual SPIR-V and inspect the first
concrete unsupported construct. Do not bypass dispatches or fake flips.
