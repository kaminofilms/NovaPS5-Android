# NOVA PS5 0.9.16 — SOL IMPLEMENTATION HANDOFF TO GPT-6

Continue Nova PS5 development from Sol's final implementation. Inspect the actual committed code and verified build artifacts before making further changes. Use the user's new device boot logs to identify the next compatibility blockers. Do not restart the project, downgrade the emulator, or replace the completed integration.

## Current identities and build

Repository: https://github.com/kaminofilms/NovaPS5-Android
Branch: `feature/anyps5-android-gpu`
Final implementation commit: `27ecb649cab2bc3f7cf9f755f53f6fb3515013a5`
Commit: https://github.com/kaminofilms/NovaPS5-Android/commit/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5

GitHub Actions run ID: `38676740728`. Run: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38676740728

Build result: **completed — success; all six jobs passed** (FEX, FFmpeg, ARM64 FEX execution test, Kyty, APK, logs).

Verified release: https://github.com/kaminofilms/NovaPS5-Android/releases/tag/v0.9.16-android-27ecb64

Verified APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/NovaPS5-0.9.16-android-arm64.apk

APK size: 20469374 bytes; versionName `0.9.16-android`; versionCode `64`; ARM64-v8a.

APK SHA-256: `cdc0883b1da1a01cd9937124f12a4056e5a019955b81e591927acdf93f513149`. Uploaded release digest matches the CI build output.

Verified Actions APK artifact: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38676740728/artifacts/11947580225

APK checks: `NOVA_NATIVE_APK: ALL PASS`; original package `com.kaminofilms.novaps5`, original Nova test signing key, AArch64-only native ELF, 16 KB native alignment, Android-resolvable dependencies, no glibc versions, required SDL/JNI/FEX/controller exports.

CI results: production compute workgroup lowering PASS (984 coordinate checks); compiler/pipeline host subgroup source guard PASS; shader device profile/cache regression PASS; storage-backed i64 atomic SPIR-V validation PASS; GPU completion and store-before-IRQ PASS; actual SPIR-V memory-fence emitter PASS; suspended WAIT_REG_MEM PASS; minimal Vulkan 1.1 fence validation PASS; startup, high guest VA and RELEASE_MEM PASS; full Android ARM64 compilation/link and APK packaging PASS; FEX ARM64 `ALL PASS (0 failures)`.

No physical-device test of 0.9.16 has been executed here. CI establishes compilation/packaging and stated regression results, not game boot or Adreno pipeline acceptance.

Corresponding sources, checksum and verification report were verified uploaded with the APK:

- [FEX-Android-corresponding-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/FEX-Android-corresponding-source.tar.gz) — 34321726 bytes; sha256:b37b52e925109890e83db4768df8051713389966600a63a42549283f7aa22c9e.
- [Kyty-Android-corresponding-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/Kyty-Android-corresponding-source.tar.gz) — 60607184 bytes; sha256:74765d2d0339ef748076f5ad300385fef0c8006bbe03f9fcf3f58dd1496c2832.
- [NovaPS5-0.9.16-android-arm64.apk](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/NovaPS5-0.9.16-android-arm64.apk) — 20469374 bytes; sha256:cdc0883b1da1a01cd9937124f12a4056e5a019955b81e591927acdf93f513149.
- [NovaPS5-build-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/NovaPS5-build-source.tar.gz) — 57285922 bytes; sha256:b89d4741d01c7b05aefd2f07f4572168772e6a8aa15747d8037806002f5b142e.
- [SHA256SUMS.txt](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/SHA256SUMS.txt) — 99 bytes; sha256:e1dcf5b1dd12e7c76b951f72a001e9f0361a5d62cc733fca8aa8705e85fb8469.
- [verify.txt](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.16-android-27ecb64/verify.txt) — 1905 bytes; sha256:c7304ed36ddb83de4f76b29ac4fd7e5b043c5cfd27a7b7d61f54a51078a6aaf2.

## Current device evidence and required scope honesty

The user's latest 0.9.15 test proves the Meat Boy failure persists, and the shader's flags rule out the LDS-atomic fallback as its cause. The pipeline result is ErrorUnknown (-13), hash `0xd1a9115d6e0e3be6`, guest local size 4x4x4, guest wave 64, compiled host subgroup 64. It uses zero LDS, no shared/buffer i64 atomics, no FP64 and no compute derivatives. The internal cause of the driver rejection is unknown. Do not represent the new workgroup normalization as a confirmed root-cause fix.

The user wants the full AnyPS5 renderer/compiler. That full import remains unimplemented. It needs a real resource-layout/IR/runtime adapter, not just linking another library or a boot switch. This follow-up adapts an executable compiler lowering component into the existing renderer, preserving NovaFEX. The canonical 1D layout may avoid a driver/compiler issue, while strict validation will expose structurally invalid generated modules. Only a new device test can establish acceptance of this shader or progression beyond it.

No actual game menu is confirmed. Luna Abyss's last excerpt still lacks a fatal record. Dead Cells regression/performance remains unverified on the device. Do not claim that CI or coordinate tests prove commercial game compatibility.

## Exact repository files changed in 0.9.16

All links are pinned to the final implementation commit:

- [patches/kyty-anyps5-compute-workgroups.patch](https://github.com/kaminofilms/NovaPS5-Android/blob/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5/patches/kyty-anyps5-compute-workgroups.patch)
- [tests/test_compute_workgroup.py](https://github.com/kaminofilms/NovaPS5-Android/blob/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5/tests/test_compute_workgroup.py)
- [tests/test_shader_features.py](https://github.com/kaminofilms/NovaPS5-Android/blob/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5/tests/test_shader_features.py)
- [tools/ci/build-android-kyty.sh](https://github.com/kaminofilms/NovaPS5-Android/blob/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5/tools/ci/build-android-kyty.sh)
- [.github/workflows/android-native.yml](https://github.com/kaminofilms/NovaPS5-Android/blob/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5/.github/workflows/android-native.yml)
- [docs/ANYPS5-COMPUTE-WORKGROUPS-0.9.16.md](https://github.com/kaminofilms/NovaPS5-Android/blob/27ecb649cab2bc3f7cf9f755f53f6fb3515013a5/docs/ANYPS5-COMPUTE-WORKGROUPS-0.9.16.md)

Eight effective Kyty source files modified by the new overlay:

- `src/graphics/shader/shader.h`: checked layout predicate and device X limit.
- `src/graphics/shader/shader.cpp`: X limit in compute static cache key.
- `src/graphics/shader/recompiler/backend/spirv/SpirvEmitter.cpp`: compute-only canonical layout selection, separate from paired waves and graphics stages.
- `src/graphics/shader/recompiler/backend/spirv/spirvEmitterInternal.h`: effective layout in emitter state.
- `src/graphics/shader/recompiler/backend/spirv/spirvEmitterModule.cpp`: remapping built-ins and physical LocalSize emission.
- `src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp`: guest local/global ID reconstruction.
- `src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp`: device limits, supported wave32 host profile, and Android SPIR-V validation/errors.
- `src/graphics/host_gpu/renderer/pipeline/shaders.cpp`: request the compiled host subgroup and report the selected profile on pipeline failure.

The inherited Android build still uses an external patched Kyty clone, not vendor-only changes. The new overlay is applied after the two earlier GPU overlays. All exact source is in the corresponding-source release assets.

## Direct AnyPS5 source references

- [core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvInputOutput.cpp](https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvInputOutput.cpp)
- [core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvEmitterHelpers.cpp](https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvEmitterHelpers.cpp)
- [core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvModuleSetup.cpp](https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvModuleSetup.cpp)
- [core/libs/prx/libSceAgcDriver/Execution/src/VulkanDevice.cpp](https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/libs/prx/libSceAgcDriver/Execution/src/VulkanDevice.cpp)

## GPU, memory, presentation and settings

No new PM4 opcode, guest address mapping, allocator, CPU translator, display flip or fake completion path is added in 0.9.16. The existing 0.9.14 completion-before-label-before-IRQ, real waits, and memory fence changes are retained. Per-workgroup memory ownership is unchanged: the same original workgroup members execute and share the same LDS/storage region; only physical local coordinates change, and guest coordinates are reconstructed. Dispatch counts, WorkgroupID and NumWorkgroups do not change. Paired wave64 lowering and derivative quad layout retain their previous paths.

The actual renderer remains Android Vulkan using Kyty, with SDL3 and NovaFEX; no desktop runtime or second Vulkan device is introduced. FPS caps and bilinear presentation remain functional. Internal resolution scaling, FSR EASU/RCAS and sharpening remain unavailable. EOP draining can still reduce performance.

## Next work for GPT-6

1. Verify this commit, build and uploaded APK before editing. Read the actual overlay and reconstructed source in the source archives.
2. Use a new 0.9.16 system-Vulkan log. Inspect the FIRST `NOVA_SPIRV_INVALID` (exact validation error/hash) or `NOVA_COMPUTE_PIPELINE_FAILED` record. Do not diagnose a four-second watchdog as the final failure if compilation continues afterward.
3. Compare the exact hash `0xd1a9115d6e0e3be6` and `linear_group`, `required_subgroup`, guest dimensions, guest wave and compiled host subgroup. The failure record's local dimensions remain guest dimensions; canonical physical size is their product x1x1 when selected.
4. If the module validates but the same hash still fails, capture/disassemble its actual emitted SPIR-V and audit resources, subgroup instructions and enabled device capabilities. ErrorUnknown alone does not prove a wave-size bug. Use the existing shader-dump machinery; obtain the exact file from the user's device rather than guessing its contents.
5. Correct the first concrete invalid operation/ABI requirement, preserving the passing coordinate mapping and queue semantics. Do not skip failed dispatches, suppress errors or force flips. Also track `Shader: emitted zero-position clip guard` and VS/PS counts. That marker exists in the supplied logs; if compute acceptance improves, inspect whether the vertex stage is an intentionally position-less helper or a missing real export. Do not equate pipeline acceptance with visible menu rendering.
6. Run separate Luna and Dead Cells tests with the same driver. Compare real frames/FPS and completion drain frequency. No Dead Cells regression result has been obtained here.
7. A full AnyPS5 compiler adapter must reconcile decoded inputs, IR specialization, descriptor/buffer/image layouts, shader data, BDA/guest-memory ABI, pipeline layouts and Vulkan feature profiles. Do not label another isolated patch as the full import. Preserve the current working renderer until that adapter actually compiles and executes.

## Current implementation details

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


---

# Historical 0.9.15 and 0.9.14 records

The records below retain prior source provenance and test artifacts. Their current-identity and no-device-test statements apply to those earlier handoffs only. Use the 0.9.16 identities and newer user evidence above for current development. In particular, the new Meat Boy log disproves any assumption that the 0.9.15 LDS fix resolved its fatal.

# NOVA PS5 0.9.15 — SOL IMPLEMENTATION HANDOFF TO GPT-6

Continue Nova PS5 development from Sol's final implementation. Inspect the actual committed code and verified build artifacts before making further changes. Use the user's new device boot logs to identify the next compatibility blockers. Do not restart the project, downgrade the emulator, or replace the completed integration.

## Current follow-up and device evidence

The preceding 0.9.14 integration is limited to AnyPS5-derived GPU completion and shader-fence semantics, alongside existing AnyPS5 audio. Boot and rendering remain Kyty plus NovaFEX. There is no AnyPS5 boot-mode toggle and no full AnyPS5 compiler or renderer transplant. 0.9.15 corrects a device-capability selection bug in this existing shader compiler; it copies no additional AnyPS5 source. The historical 0.9.14 handoff follows below for exact original provenance and details.

Repository: https://github.com/kaminofilms/NovaPS5-Android
Branch: `feature/anyps5-android-gpu`
Current implementation commit: `8029fcfeb18ae41119323735842ef5047159d694`
Commit: https://github.com/kaminofilms/NovaPS5-Android/commit/8029fcfeb18ae41119323735842ef5047159d694
Actions run ID: `38674596300`
Run: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38674596300

Build result: **completed — success**, all six jobs passed (FEX, ARM64 execution test, FFmpeg, Kyty, APK and logs).

Release: https://github.com/kaminofilms/NovaPS5-Android/releases/tag/v0.9.15-android-8029fcf

Verified APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/NovaPS5-0.9.15-android-arm64.apk

APK size: 20465181 bytes. VersionName: `0.9.15-android`; versionCode: `63`.

APK SHA-256: `b52dfcf94f00a0b1b34503a541cefb76e9abe70fea8b23cfd5068ba3c34ce804` (CI build output matches uploaded asset digest).

Actions APK artifact: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38674596300/artifacts/11945718037

APK verification: `NOVA_NATIVE_APK: ALL PASS`; package `com.kaminofilms.novaps5`, existing Nova test signing key, ARM64 only, required SDL/FEX/JNI/controller entrypoints, native ELF dependencies resolvable on Android, no glibc symbol versions, 16 KB native-library page alignment.

CI confirmed: shader feature/backing combinations, cache variants and vertex isolation PASS; storage-buffer 64-bit atomic SPIR-V Vulkan 1.1 validation PASS without WorkgroupMemoryExplicitLayout; GPU completion, store-fence, suspended WAIT_REG_MEM, high guest VA/startup and RELEASE_MEM tests PASS; native Android linking PASS; FEX ARM64 execution `ALL PASS (0 failures)`.

Corresponding-source archives, checksum and verification report were all verified uploaded and nonempty:

- [FEX-Android-corresponding-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/FEX-Android-corresponding-source.tar.gz) — 34327751 bytes; sha256:f9a501b3cc464e2bbc7a806cbc596008dbbf777fe5899a129498e49bd3cff114.
- [Kyty-Android-corresponding-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/Kyty-Android-corresponding-source.tar.gz) — 60609798 bytes; sha256:0c42132d4e6196e10c8108ed1595bcca8032847320ab32a7ea9242e88b8626a9.
- [NovaPS5-0.9.15-android-arm64.apk](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/NovaPS5-0.9.15-android-arm64.apk) — 20465181 bytes; sha256:b52dfcf94f00a0b1b34503a541cefb76e9abe70fea8b23cfd5068ba3c34ce804.
- [NovaPS5-build-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/NovaPS5-build-source.tar.gz) — 57280401 bytes; sha256:8dae2321442ac75d6859014d8a484a45d1f63e64dbe3eb465a3bc9ff8a43ae6d.
- [SHA256SUMS.txt](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/SHA256SUMS.txt) — 99 bytes; sha256:1604bfebbbf7c10f683cc5af80e7ddfb2feba42dddadab5685ce6eda1e271cf0.
- [verify.txt](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.15-android-8029fcf/verify.txt) — 1905 bytes; sha256:c7304ed36ddb83de4f76b29ac4fd7e5b043c5cfd27a7b7d61f54a51078a6aaf2.

Device: REDMAGIC 11 Pro, nubia NX809J, SM8850 / Adreno 840, Android 16, system Vulkan. The user's 0.9.14 logs show:

- Super Meat Boy 3D (`PPSA31162`) reaches compute dispatch and `vkCreateComputePipelines` fails at effective `shaders.cpp:619`, after VS 1 / PS 0 / CS 17. The exact VkResult was absent. The early four-second freeze report is followed by more shader compilation; it does not prove an empty-queue deadlock. No menu/game frame is confirmed.
- Luna Abyss (`PPSA36257`) reaches VS 1 / PS 0 / CS 8 and audio initialization. The excerpt contains no fatal error. Its root cause is unresolved; do not claim it has Meat Boy's exact failure.
- Both report unresolved NpCppWebApi imports; these are not established causes. Audio peak=0 is not proof of audible output, and audio initialization is not graphics completion.
- Dead Cells was not tested on 0.9.14 or 0.9.15 in this session. Prior user-reported performance remains historical. The drained EOP fallback still has a performance risk.

## 0.9.15 source changes

Actual compiled code is still the patched external Kyty checkout, not `vendor/kytyps5`. The new overlay is checked/applied after the 0.9.14 overlay in `tools/ci/build-android-kyty.sh`.

Repository files added/modified (links pinned to the implementation commit):

- [patches/kyty-android-shader-features.patch](https://github.com/kaminofilms/NovaPS5-Android/blob/8029fcfeb18ae41119323735842ef5047159d694/patches/kyty-android-shader-features.patch)
- [tests/test_shader_features.py](https://github.com/kaminofilms/NovaPS5-Android/blob/8029fcfeb18ae41119323735842ef5047159d694/tests/test_shader_features.py)
- [tools/ci/build-android-kyty.sh](https://github.com/kaminofilms/NovaPS5-Android/blob/8029fcfeb18ae41119323735842ef5047159d694/tools/ci/build-android-kyty.sh)
- [.github/workflows/android-native.yml](https://github.com/kaminofilms/NovaPS5-Android/blob/8029fcfeb18ae41119323735842ef5047159d694/.github/workflows/android-native.yml)
- [docs/ANDROID-SHADER-FEATURES-0.9.15.md](https://github.com/kaminofilms/NovaPS5-Android/blob/8029fcfeb18ae41119323735842ef5047159d694/docs/ANDROID-SHADER-FEATURES-0.9.15.md)

Eight effective Kyty production files changed by the overlay:

1. `src/graphics/host_gpu/graphicContext.h`: store enabled native 64-bit LDS atomic support.
2. `src/graphics/presentation/window/vulkanWindow.cpp`: derive support from enabled `shaderSharedInt64Atomics`, extension presence and `workgroupMemoryExplicitLayout`.
3. `src/graphics/shader/shader.h`: compute `UsesStorageLds(shared_int64_atomics)` from memory-size fallback and actual native feature support.
4. `src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp`: set the device profile after `PrepareProgram`, which initializes the input structure.
5. `src/graphics/shader/shader.cpp`: include LDS backing and native-atomic profile in the compute cache key.
6. `src/graphics/shader/recompiler/backend/spirv/spirvEmitterInternal.h`: choose StorageBuffer for unsupported native shared64 atomics, retaining Workgroup for ordinary LDS.
7. `src/graphics/shader/recompiler/backend/spirv/SpirvEmitter.cpp`: descriptor validation follows the effective storage class.
8. `src/graphics/host_gpu/renderer/pipeline/shaders.cpp`: report precise failed pipeline requirements before the existing fatal error; no forced success.

## Shader, memory and Vulkan semantics

This compiler already implements storage-buffer LDS with per-workgroup offsets, u32/u64 aliases, descriptor binding, compute-dispatch buffer allocation, and UniformMemory barriers. Previously this route was selected only when LDS exceeded the physical shared-memory limit. Native 64-bit LDS atomics could be emitted even when optional native features were absent. The new selection uses the existing storage-backed route for only those compute shaders requiring unsupported shared64 atomics. It requires the already mandatory `shaderBufferInt64Atomics`, without requiring `shaderSharedInt64Atomics` or `WorkgroupMemoryExplicitLayout` for the storage route.

No new allocator, guest address translation, CPU translator, queue or surface is added. Ordinary LDS and graphics shaders keep their previous selection. Over-sized LDS fallback remains. Runtime storage allocation remains bounded by the existing utility buffer and `maxStorageBufferRange`; large workgroup counts can still fail rather than silently overrun storage. A failure in another shader feature is still fatal.

The shader cache key now prevents reusing native/shared-memory and storage-backed variants across device profiles. The effective descriptor-limit check also follows the chosen backing. This is an actual shader resource-execution change, not a diagnostic-only release.

The exact rejected Meat Boy shader has not been captured on a device, so this is a confirmed source bug fix and an unconfirmed game-failure fix. Vulkan pipeline rejection can have other causes. Compute derivatives, FP64 requirements, subgroup layout and descriptor limits should be examined only against the next failure's metadata and enabled features.

0.9.14 GPU commands, real completion-before-label-before-IRQ, wait behavior and presentation limiter are retained. No additional PM4 operations or flip-order changes were introduced in 0.9.15. Functional graphics settings remain presentation FPS cap and bilinear presentation. Internal resolution, FSR EASU/RCAS and sharpening remain disabled/unavailable.

## Tests and next investigation

Local production-body checks pass for all eight feature combinations, all eight backing combinations, ordinary-LDS behavior, vertex-stage isolation and distinct cache variants. The overlay checks/applies cleanly to the reconstructed 0.9.14 effective source and all eight modified files match the intended bytes. Existing GPU-completion, shader-fence, startup, guest-VA and RELEASE_MEM tests passed locally. spirv-tools is unavailable locally and required in CI; CI validates a Vulkan 1.1 storage-buffer 64-bit atomic compute module without WorkgroupMemoryExplicitLayout. Minimal modules and mocked ordering tests do not prove that all game shaders are valid.

GPT-6 should inspect actual source, enabled features and the first failing dispatch before expanding the integration. For the next user device logs:

- `NOVA_SHADER_FEATURES`: native_lds_int64, shared_atomics, explicit_layout and buffer_atomics; compare actual selected driver.
- `NOVA_COMPUTE_PIPELINE_FAILED`: exact Vulkan result/name/code, shader hash, local dimensions, guest wave, host subgroup, LDS bytes, storage_lds, shared_i64, buffer_i64, fp64 and derivatives. Correlate shader hash across runs.
- Complete fatal tail and shader counts; distinguish startup shader compilation from executed/drawn frames.
- `NOVA_GPU_WAIT`, `NOVA_VIDEO` and real game frame counts: zero in a disabled write-trace ring does not prove no GPU execution.
- For Luna, capture a later complete excerpt; do not infer a missing fatal or blame network stubs without evidence.
- Run Dead Cells with the same driver and settings and compare FPS and EOP wait frequency. Correctness draining may cost performance; optimize with properly tracked Vulkan label writes rather than early CPU completion.

If this build still rejects the same shader, inspect its emitted SPIR-V and the newly reported feature flags. Correct the first concrete unsupported requirement. Do not skip failed dispatches, fabricate flips or restore timeout-success waits.

---

# Historical 0.9.14 implementation record

The following is the completed 0.9.14 record, retained for provenance. Its build/APK identities refer to the prior release; use the 0.9.15 identities and updated user-device observations above for current work. Statements that 0.9.14 had not been tested on the phone were true at that earlier handoff and are superseded by the new evidence above.

# NOVA PS5 0.9.14 — SOL IMPLEMENTATION HANDOFF TO GPT-6

Continue Nova PS5 development from Sol's final implementation. Inspect the actual committed code and verified build artifacts before making further changes. Use the user's new device boot logs to identify the next compatibility blockers. Do not restart the project, downgrade the emulator, or replace the completed integration.

## Scope and confirmed implementation

This is a native Android ARM64 build with a **limited AnyPS5 GPU synchronization adaptation**, not a wholesale AnyPS5 renderer or shader compiler import. It retains the existing Kyty RDNA decoder, IR, SPIR-V backend, Vulkan renderer, NovaFEX CPU translation, SDL3 Android surface and AAudio. The release implements GPU completion and shader memory-fence changes; it is not a logging-only build. No commercial game menu or gameplay success has been established in this session.

## Repository, commits and build

- Repository: https://github.com/kaminofilms/NovaPS5-Android
- Branch: `feature/anyps5-android-gpu`
- Starting branch HEAD: `6dab01ef57c318f3b838692ca297dd60b9b84658`.
- Original 0.9.13 baseline: `74e8eb05bf3953497d4168d2139aa48f45214942`.
- Initial implementation commit: https://github.com/kaminofilms/NovaPS5-Android/commit/9531eab8c03782634a4a0747671683a228cb3001
- Follow-up correcting tracked-page completion handling: https://github.com/kaminofilms/NovaPS5-Android/commit/dd48245f98b16a12812dca7af7238b34ac638836
- Final ordering correction: https://github.com/kaminofilms/NovaPS5-Android/commit/914787efa5d17a16165f08187e859e3d729c461f
- Final commit: `914787efa5d17a16165f08187e859e3d729c461f`.
- GitHub Actions run ID: `38671466100`.
- Run: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38671466100
- Build result: native, bridge, GPU, APK packaging and verification jobs all succeeded.
- Release: https://github.com/kaminofilms/NovaPS5-Android/releases/tag/v0.9.14-android-914787e
- Verified APK: https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/NovaPS5-0.9.14-android-arm64.apk
- APK size: 20460990 bytes; versionName `0.9.14-android`, versionCode `62`, ARM64-v8a.
- Verified Actions artifact: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38671466100/artifacts/11944364924
- APK SHA-256: `645763d0a3c56f949211c6032a4573e923d96d88dc0ff3656ce33ef431410fff`. This matches both CI output and the uploaded release asset digest.

Published release assets (verified uploaded, nonzero size):

- [FEX-Android-corresponding-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/FEX-Android-corresponding-source.tar.gz) — 34332779 bytes.
- [Kyty-Android-corresponding-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/Kyty-Android-corresponding-source.tar.gz) — 60608911 bytes.
- [NovaPS5-0.9.14-android-arm64.apk](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/NovaPS5-0.9.14-android-arm64.apk) — 20460990 bytes.
- [NovaPS5-build-source.tar.gz](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/NovaPS5-build-source.tar.gz) — 57273484 bytes.
- [SHA256SUMS.txt](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/SHA256SUMS.txt) — 99 bytes.
- [verify.txt](https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.14-android-914787e/verify.txt) — 1905 bytes.

Use the FINAL build above. The initial implementation's deferred host label writes were superseded by a drained GPU-thread fallback after examining protected-page fault handling. Do not resurrect that earlier callback write path.

## Critical build-path finding

The Android-native workflow does **not** compile `vendor/kytyps5`. It clones KytyPS5 at `df5b9b92be7dfd463b47756b707d6d356a9f0550`, applies the patches listed in `patches/linux-core.series`, recovers its ARM64 patch from Nova commit `740c60496616f265e1edec54f0248ba728946a75`, and applies additional guarded transforms in `tools/ci/build-android-kyty.sh`.

Sol reconstructed that exact effective source locally and added a checked overlay **after** the existing transforms. All future GPU edits must reach that effective source, or CI must first be deliberately migrated with reproducible equivalence tests. Vendor-only edits will not reach this APK.

The overlay is `patches/kyty-anyps5-gpu-completion.patch`.

## Exact AnyPS5 reference components

Inspected upstream snapshot: `131171e77218a26d5746a8074a8216ec66f4dcb0` in https://github.com/boykopovar/AnyPS5.

1. https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/libs/prx/libSceAgcDriver/Execution/src/Pm4.cpp
   - RELEASE_MEM label widths, destination and timestamp behavior.
2. https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/libs/prx/libSceAgcDriver/Execution/src/Driver/Packets/PacketMemory.cpp
   - Label stores and EOP notifications ordered behind recorded Vulkan work; drained CPU-store fallback.
3. https://github.com/boykopovar/AnyPS5/blob/131171e77218a26d5746a8074a8216ec66f4dcb0/core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvFormatConvert.cpp
   - Device-scope acquire/release memory-fence emission without an execution rendezvous.

These were adapted into Nova's existing interfaces. No large AnyPS5 source subtree or separate Vulkan device was imported. GPL version 2 license text and existing Kyty MIT notices were preserved. CI publishes the actual patched source and initialized dependencies alongside the APK and includes notices in APK assets/licenses.

## Exact Nova repository files modified or added

- `.github/workflows/android-native.yml`: 0.9.14/versionCode 62, spirv-tools dependency, corresponding-source packaging and release assets.
- `patches/kyty-anyps5-gpu-completion.patch`: actual production renderer and shader changes.
- `tools/ci/build-android-kyty.sh`: checks/applies overlay, runs new production-body tests, archives actual patched Kyty/dependencies.
- `tests/test_gpu_completion.py`: executable host harnesses for actual EOP template and SPIR-V fence emitter; WAIT_REG_MEM guard; minimal Vulkan SPIR-V validation when spirv-tools is available.
- `nova-android/src/com/kaminofilms/novaps5/GameActivity.java`: passes FPS preference as `NOVA_FPS_CAP`; logs the selected cap and completion profile.
- `nova-android/src/com/kaminofilms/novaps5/MainActivity.java`: accurate graphics-setting labels and disables unavailable resolution/FSR/sharpening.
- `docs/ANYPS5-GPU-INTEGRATION.md`: reference provenance, semantics, limitations, source distribution.

The overlay modifies these **effective Kyty source files**:

- `src/graphics/guest_gpu/graphicsRun.cpp`
- `src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp`
- `src/graphics/shader/recompiler/ir/passes/ShaderInfoCollection.cpp`
- `src/graphics/presentation/window/swapchain.cpp`

Direct final-source links:

- [.github/workflows/android-native.yml](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/.github/workflows/android-native.yml)
- [patches/kyty-anyps5-gpu-completion.patch](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/patches/kyty-anyps5-gpu-completion.patch)
- [tools/ci/build-android-kyty.sh](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/tools/ci/build-android-kyty.sh)
- [tests/test_gpu_completion.py](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/tests/test_gpu_completion.py)
- [nova-android/src/com/kaminofilms/novaps5/GameActivity.java](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/nova-android/src/com/kaminofilms/novaps5/GameActivity.java)
- [nova-android/src/com/kaminofilms/novaps5/MainActivity.java](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/nova-android/src/com/kaminofilms/novaps5/MainActivity.java)
- [docs/ANYPS5-GPU-INTEGRATION.md](https://github.com/kaminofilms/NovaPS5-Android/blob/914787efa5d17a16165f08187e859e3d729c461f/docs/ANYPS5-GPU-INTEGRATION.md)

## GPU command-processing changes

`CommandProcessor::WriteAtEndOfPipe<T>` formerly published 32/64-bit guest label values immediately during command recording, while an EOP IRQ could remain deferred until GPU completion. This allowed guest CPU pollers to observe completion before preceding Vulkan commands finished.

The new `complete_write` path:

1. Requires a valid destination and active command buffer.
2. Calls the existing `CommandScheduler::Finish()` to submit and wait on the actual timeline semaphore for preceding GPU commands.
3. Retires earlier priority callbacks so IRQ-only completions cannot be overtaken, then samples the reference clock for timestamp-source packets.
4. Copies the label through `GuestMemory::Copy` on the GPU thread.
5. Delivers the requested EOP interrupt after that copy.

The existing GDS-specialized path and interrupt-selector normalization remain intact. Valid cache-writeback 64-bit events 0x2b and 0x2d now accept an IRQ in the same way their non-cache forms do. Unsupported event types still fail; they are not converted into successful no-ops. No broad PM4 opcode expansion is claimed.

The inherited WAIT_REG_MEM timeout-success path was removed: previously it could continue after 2 seconds, remember a label as "bad", then skip future waits after 100 ms. Unsatisfied waits now call `SuspendPm4()` until the comparison actually succeeds. Existing diagnostic reporting remains. This may expose a genuine producer failure that earlier versions concealed; do not reintroduce forced-success behavior to hide it.

## GPU memory and synchronization details

Android high guest VA translation is preserved. Labels remain guest addresses; `GuestMemory::Copy` uses the existing NovaGuest translation and split-range behavior. No Linux address identity assumption was imported.

A proposed asynchronous host callback was rejected during review: a label can lie on a write-protected tracked page, and BufferCache explicitly rejects readback initiated from an asynchronous completion thread. Writing there can also race a subsequent GPU upload of the label. The final drained fallback writes from the GPU thread after real completion, preserving the existing fault and buffer/image invalidation mechanisms.

**Performance limitation:** every supported EOP label write now introduces a real queue completion wait. This is a conservative correctness fallback and may reduce FPS in fence-heavy games. Do not claim Dead Cells performance is preserved without a device measurement. A next optimization should write labels into the actual Vulkan-backed buffer with proper barriers and host visibility, then notify the guest after completion, similar to AnyPS5 `WriteLabelOnGpu`, while retaining the fallback for unsupported mappings.

No new allocator, VMA ownership model, direct desktop buffer import, guest VA layout or FEX implementation was introduced.

## Shader translation integration

The existing PS5 shader -> RDNA decoder -> IR -> SPIR-V -> Vulkan module path remains in use.

`S_WAITCNT_VSCNT(0)` translates to IR `StoreCompletion`. Its SPIR-V emission previously used `OpControlBarrier` at Subgroup execution scope with Device memory scope. A store-completion instruction is not a cross-lane rendezvous; that execution barrier can be invalid under divergent flow.

The final emitter uses `OpMemoryBarrier` with:

- Memory scope: Device (1)
- Semantics: AcquireRelease (8) | UniformMemory (64) | ImageMemory (2048) = 2120

ShaderInfoCollection no longer sets `subgroup_barrier` solely for `StoreCompletion`. Real `S_BARRIER` workgroup synchronization is unchanged. This is a specific shader memory-ordering adaptation, **not** a complete AnyPS5 shader backend import or a new operation suite. No new desktop-only Vulkan extension is required by the changed fence instruction.

## Android Vulkan and presentation

- Existing native Android surface, swapchain, Vulkan queue, driver selection and bilinear image blit are retained.
- Existing frame preparation/completion/flip ordering remains; no forced or blank substitute frame was added.
- FPS cap is consumed in `Presenter::Impl::Present()`, on the real presentation thread, using a monotonic host clock and `sleep_until` before acquiring/submitting the next swapchain image.
- Supported presentation caps: 30/40/60/90/120/unlimited. Default remains unlimited.
- The cap does not change game simulation time and does not guarantee that a slow game can attain the selected FPS.
- No comprehensive device-lost recovery, new descriptor model or second renderer was added.

## Graphics settings

| Preference | Actual behavior in this build |
| --- | --- |
| `graphics_fps_index` | Passed through Java environment to actual Vulkan presentation limiter; game restart required. |
| `graphics_resolution_index` | Retained in preferences, UI control disabled; internal scaling not implemented. |
| `graphics_upscale_index` | UI fixed to existing bilinear presentation; FSR unavailable and disabled. |
| `graphics_sharpen` | Retained, UI disabled; RCAS not implemented. |

Do not claim FSR EASU/RCAS, internal-resolution scaling or sharpening exists in this release.

## Tests and evidence

Local confirmed passes:

- Reconstructed exact effective Android source and checked overlay application into all four production files; resulting bytes matched the implementation source.
- Production EOP template compiled/executed with a recording timeline: GPU completion before 32/64-bit stores, correct store-before-IRQ, cache/non-cache event variants, no-IRQ progress, timestamp sampled after completion, unsupported-event rejection.
- Actual shader-fence emission method compiled/executed: OpMemoryBarrier, Device scope, semantics 2120, no control rendezvous.
- WAIT_REG_MEM source guard: no timeout-success path; suspended wait remains.
- Existing `test_native_startup.py`: allocator/fixed placement/trampoline/FEX callback and translated GPU domain checks passed.
- Existing `test_release_mem.py`: 25 selector combinations and 3 rejected data selectors passed.
- Shell syntax and workflow YAML parsed successfully.

Local constraints:

- `spirv-val`/`spirv-as` were not installed locally; the minimal fence module validation is required in CI, whose dependency step installs spirv-tools.
- Existing structured SIMD host test could compile but failed under this sandbox because `process_vm_readv` is denied with EPERM (confirmed by an independent self-read probe). Do not attribute this to the GPU patch; no NovaFEX source was modified. The same test remains required on GitHub runners.
- No Android SDK/NDK or physical Adreno device was available locally; native linking, Java/APK packaging and binary validation rely on the completed CI evidence below.

Confirmed CI stages (run 38671466100):

- FFmpeg dependency build/cache job: success.
- Structured SIMD decoder regression on Ubuntu: success.
- Android NDK FEX native compilation/link: success.
- ARM64 static-bionic bridge execution: `NOVAFEX_TEST: ALL PASS (0 failures)`.

- GPU completion production-body regression: PASS.
- WAIT_REG_MEM no-timeout-success guard: PASS.
- SPIR-V emitter regression: PASS.
- `spirv-val --target-env vulkan1.1` minimal compute fence module: PASS.
- Startup and high guest VA/GPU-domain regression checks: ALL PASS.
- RELEASE_MEM parser: PASS (25 combinations, 3 rejected data selectors).
- Full Kyty Android NDK compilation and ARM64 linking: success.
- Java compilation, APK packaging and signing: success.
- APK verifier: `NOVA_NATIVE_APK: ALL PASS`.
- Verified package `com.kaminofilms.novaps5`; version `0.9.14-android`, code `62`.
- Verified all native libraries AArch64 ELF, 16 KB page-aligned, no glibc symbol versions, Android-resolvable dependencies, required SDL/JNI/controller entrypoints, expected signing certificate.
- Verified APK, checksum, verification report and three corresponding-source archives uploaded to the release.

Full run conclusion: **completed — success** (all six jobs succeeded)..

The minimal SPIR-V fence module validates instruction legality, not every game shader and not GPU execution. CPU mocks test production method ordering, not Vulkan driver behavior.

## Known limitations and game compatibility status

- **Super Meat Boy 3D (`PPSA31162`)**: user baseline guest execution/audio, no meaningful displayed game menu. This release has not been executed on the phone in this session. No menu/boot success claimed.
- **Luna Abyss (`PPSA36257`)**: user baseline guest execution/audio and RHI/task threads waiting. This release has not been executed on the phone. No menu/boot success claimed.
- **Dead Cells (`PPSA15552`)**: earlier user builds reportedly reached 50–60 FPS. No physical regression test was possible here. CPU/audio/identity/touch/save paths retained; GPU synchronization changed globally, so regression status remains unverified.

## What GPT-6 should inspect next

1. Confirm final commit, APK hash, versionCode and corresponding-source archives against this handoff before editing.
2. Collect fresh separate boot logs for PPSA31162 and PPSA36257, and one Dead Cells performance run, on the same driver/version. Compare system Vulkan and optional Turnip only with concrete evidence.
3. Follow the first genuine unsatisfied WAIT_REG_MEM: packet address/queue, comparison function, reference/mask/current value, expected producer, and whether its command buffer was submitted. A timeout is evidence, not permission to skip it.
4. Determine whether AGC submission reaches the correct graphics/compute queue before touching presentation. If submissions are absent, inspect guest AGC synchronization/API behavior and guest memory writes before expanding the renderer.
5. If draws/dispatches execute, trace resource bindings and shader translation errors before diagnosing flip scheduling. A frame flip is valid only after its producing GPU work completes.
6. Measure how often the drained EOP fallback runs. If it limits Dead Cells, implement Vulkan-backed label writes plus completion-ordered IRQs; avoid restoring early CPU label publication.
7. Add focused SPIR-V validation/capture for the first failing shader on Adreno. Do not assume a desktop feature exists because shader compilation succeeds.

## Boot-log markers to analyze

- `GPU completion: drained label stores; presentation cap:`: Java launch selected this build profile.
- `NOVA_ANDROID:`: process start, core startup and Vulkan driver.
- `NOVA_FEX:`: CPU translator initialization and high-VA mode.
- `NOVA_GPU: RELEASE_MEM int_sel 3 -> interrupt after write`: inherited selector normalization, not independent proof of GPU completion.
- `NOVA_EOP_UNSUPPORTED:`: exact event/selector/cache/source/context values; unsupported events remain fatal.
- `NOVA_GPU_WAIT: queue(event ... ) waits on ...`: first persistent unsatisfied label and its expected comparison.
- `NOVA_GPU_WAIT: commands pending`: submission/queue context. Correlate with wait and producer state.
- `NOVA_FREEZE: no frame`: symptom only.
- `NOVA_GPU: state at freeze (0 GPU writes so far)`: normal releases disable the detailed GPU write ring, so zero is not proof of zero execution.
- `NOVA_GPU_WATCH:`: inherited watched-label diagnostics when active.
- Vulkan `vkQueueSubmit`, timeline wait errors, shader translation errors, unsupported opcodes and `VK_ERROR_DEVICE_LOST` (if reported).
- Audio initialization is not proof of graphics progress; successful CI is not a game compatibility test.

## Recommended next engineering changes

Based on confirmed implementation, not unobserved game outcomes:

- Optimize EOP fallback with real Vulkan label writes, buffer-range barriers, CPU visibility and correctly ordered notifications.
- Add physical-device regression measurements for Dead Cells before widening GPU changes.
- Use the first new unsatisfied wait or rejected PM4/shader operation as the next implementation target.
- Preserve the native Android pipeline and existing NovaFEX/SDL3/AAudio/driver configuration.
- Implement FSR/resolution only after a real rendered frame path is verified; keep unavailable controls disabled until then.

Continue from the committed subset. Do not label it a complete AnyPS5 graphics integration, do not claim a game menu without device evidence, and do not replace working emulator subsystems to conceal the next blocker.
