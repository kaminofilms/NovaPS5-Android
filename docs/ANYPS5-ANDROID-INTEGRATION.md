# AnyPS5 native Android integration

Branch: `work/anyps5-full-android`, based on NovaPS5 0.9.39
`ad1794525d34f45d0bf708c4c8d4589540934286`.
Upstream AnyPS5: `9caecfd2d5a822be9daf84c69c7c33c7fafe52b9`.

## Architecture

The native ARM64 module contains the full upstream shader compiler and optimizer,
AGC command processor, graphics resources, Vulkan pipelines, AGC SDK API and
VideoOut queue/buffer/event/flip implementation. Android window ownership, input,
process lifetime, virtual-memory mapping and kernel event services come from
Nova. Guest x86-64 execution remains embedded NovaFEX. Audio, UI, saves and the
PKG importer remain Nova services.

The backend is wired into Nova initialization and its export resolver. Export
bindings are generated from actual linked `sceAgc*` and `sceVideoOut*` symbols;
the current module has 335 such exports. Functions use NovaFEX native call gates.
`NOVA_GPU_BACKEND=kyty` selects the existing fallback; otherwise this integration
build selects AnyPS5. This is a native backend port, not a Linux or Wine wrapper.

## Current verification

- Full compiler/optimizer, AGC driver/API and adapted VideoOut linked for Android
  arm64/API29 with NDK r30 and `--no-undefined`.
- Nova's core with the runtime integration linked successfully. Integration
  checks and the final signed APK are still being completed.
- Four compiler host tests passed and generated compute SPIR-V passed spirv-val.
- Android compiler regression executables compiled; not run on a physical device.
- Renderer uses the upstream descriptor/BDA ABI together with its resource
  implementation. AnyPS5 SPIR-V is not fed to Kyty's incompatible layouts.
- Guest bulk accesses use translated Nova memory services; imported Vulkan host
  pointers require a contiguous translated host span. Native GPU labels retain
  aligned atomic release stores.
- Mapping changes hold the actual upstream allocation-registry mutation while
  native mappings change. Existing GPU leases are waited on before mutation;
  changed mappings/protections are then published to the renderer registry.
- VideoOut retains real GPU completion callbacks, buffer reuse, vblank and event
  delivery. SDL2 desktop window/input ownership is replaced by Nova's native
  Android window and existing controls.
- Shader/compiler dependencies are hidden from dynamic symbol interposition.
  Android ELF load segments use 16 KiB alignment.

No game boot, compatibility or FPS improvement is established until device logs
show it. Ever Forward baseline supplied by the owner is 3.6–4.7 game FPS. The
large render wait, EOP label and readback scopes in that log overlap and must not
be summed. Windows FPS is not Android validation.

## Reproduction

Initialize `external/anyps5` and its pinned SPIRV-Headers, SPIRV-Tools, glslang and
Vulkan-Headers submodules. Build with the same NDK r30 as Nova's existing core.

```
cmake -S native/anyps5 -B build/anyps5-android -G Ninja \
  -DANYPS5_SOURCE_DIR="$PWD/external/anyps5" \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 \
  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release \
  -DNOVA_ANYPS5_BUILD_AGC=ON \
  -DNOVA_ANYPS5_HOST_GLSLANG=/absolute/path/to/host/glslang
cmake --build build/anyps5-android --target nova_anyps5_renderer --parallel 4
python3 native/anyps5/renderer/export_manifest.py \
  "$ANDROID_NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm" \
  build/anyps5-android/renderer/libnova_anyps5_renderer.so \
  native/anyps5/anyps5_exports.inc
python3 native/anyps5/apply_kyty.py /absolute/path/to/staged/kyty \
  "$PWD/external/anyps5" "$PWD/build/anyps5-android"
```

Rebuild the staged Nova core with its existing build options, package the new
renderer alongside libmain.so and existing native libraries, retain the existing
signing certificate, and run APK verification. Do not clear user caches or saves.
For host tests omit the Android toolchain options, use the pinned Vulkan-Headers,
and run ctest. Host software Vulkan tests do not establish Android driver results.

Upstream source and dependencies retain their licenses and pinned revisions.
`renderer/stage.py` applies replayable platform changes to a build copy, leaving
the upstream checkout unmodified.
