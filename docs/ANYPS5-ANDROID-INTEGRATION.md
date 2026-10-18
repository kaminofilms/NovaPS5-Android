# AnyPS5 native Android integration

Branch: `work/anyps5-full-android`, based on NovaPS5 0.9.39 source
`ad1794525d34f45d0bf708c4c8d4589540934286`.

Upstream source is pinned as the `external/anyps5` git submodule at
`9caecfd2d5a822be9daf84c69c7c33c7fafe52b9`. Its GPL-2.0 license and
third-party submodule licenses remain with the upstream source.

## Scope and current status

This branch is an in-progress full-backend port, not a completed merge or
replacement APK. `native/anyps5` builds the entire upstream shader recompiler,
including decoding, control flow, translation, optimization, SPIR-V generation,
and SPIRV-Tools optimization. The bridge returns the full upstream result,
including descriptors and runtime ABI metadata. It does not flatten this into
SPIR-V alone or feed incompatible descriptors to Kyty.

The existing 0.9.39 APK does not use this backend. The new module is not connected
to game rendering yet. Android compilation, host compilation, and actual device
execution are separate validation steps.

## Reproduce the component build

```
git submodule update --init --depth 1 external/anyps5
git -C external/anyps5 submodule update --init --depth 1 \
  3rdparty/SPIRV-Headers 3rdparty/SPIRV-Tools 3rdparty/glslang
cmake -S native/anyps5 -B build/anyps5-android -G Ninja \
  -DANYPS5_SOURCE_DIR="$PWD/external/anyps5" \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 \
  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release
cmake --build build/anyps5-android --parallel 4
```

Use the existing Nova NDK r30 toolchain. For host compiler regression tests,
omit the Android toolchain, ABI, platform and STL options, then run
`ctest --test-dir build/anyps5-host --output-on-failure`.

## Runtime integration boundaries

- AnyPS5 runtime descriptor ABI version 14 includes shader data, BDA page tables,
  fault buffers, flattened SRT data, sampler and image tables. Kyty pipeline
  layouts cannot consume that ABI directly.
- Keep AnyPS5 AGC command execution, resource tracking and shader ABI together.
  Adapt guest-memory reads, writes, allocation queries and write tracking to
  NovaFEX and Nova's existing GPU memory ownership. Never dereference a guest VA
  directly or report completion before actual Vulkan work finishes.
- AnyPS5 provides PresentationWindow callbacks for Vulkan surface creation and
  drawable dimensions. Connect these to Android window lifetime and Nova's
  selected adrenotools driver. Its desktop `libvulkan.so.1` loader needs an
  Android-specific loader path using that selected driver.
- Desktop libkernel/libc exports use AnyPS5's relinked guest ABI. Connect the
  needed HLE exports through NovaFEX's existing guest-call gates; native ARM64
  functions cannot be installed as x86-64 function pointers.
- The AGC guest-memory implementation has x86 SSE masked write-back code and
  desktop arena/write-watch assumptions. Port those explicitly while preserving
  changed-byte write semantics and CPU/GPU ordering.

## Device baseline: Ever Forward PPSA04703

User's 0.9.39 log reports 3.6–4.7 game FPS. In approximately five-second windows,
render-thread wait scopes take about 3.4–3.7 seconds; EOP label reads take about
2.1–2.7 seconds, and readbacks about 1.1–1.6 seconds. Scopes overlap and must not
be summed. Warm shader lookup/compilation is much smaller, though cold compute
shader compilation causes substantial spikes. Compare the same scene with warm
and cold caches separately. Windows FPS is a reference, not Android validation.

## Verification completed during this port

- NDK r30 / Android API 29 / arm64-v8a: full upstream compiler and optimizer
  linked successfully with `--no-undefined`.
- Android window adapter compiled against the upstream PresentationWindow API.
  It owns an acquired ANativeWindow reference and uses the caller-provided
  Vulkan instance function from the selected driver. Its owner must outlive the
  AnyPS5 Vulkan surface/device; runtime attach/detach is not wired yet.
- Four Android regression executables compiled and linked: bridge compute
  compilation, upstream Float16Conversion, Spirv13Image and PositionInvariance.
  These executables have not been run on an Android device.
- The shared module has 16 KiB ELF load alignment. Only NovaAnyPS5 bridge and
  adapter symbols are exported; bundled glslang/SPIRV-Tools symbols are hidden.
- The upstream checkout and all three compiler dependency submodules are
  unmodified and remain at their pinned revisions.
- Host GCC 13.3: all four tests passed. The bridge produced a 117-word compute
  SPIR-V module, which also passed standalone spirv-val for Vulkan 1.3.
  These are compiler tests, not an Android GPU or game-compatibility test.
