#!/bin/bash
# libnovalsfg.so: Lossless Scaling frame generation for Nova (see native/novalsfg/novalsfg.h).
#   build-android-lsfg.sh <repo> <workdir> <outdir>   (outdir/lib/libnovalsfg.so)
# Source: lsfg-vk-android (MIT, lsfg-vk 1.0.0 + Android AHardwareBuffer patches), pinned.
# HOST_BUILD=1 builds for the host (compile check only; no AHardwareBuffer path).
set -euo pipefail
repo=$(realpath "$1"); work=$(realpath -m "$2"); out=$(realpath -m "$3")
LSFG_REPO=https://github.com/FrankBarretta/lsfg-vk-android.git
LSFG_COMMIT=${LSFG_COMMIT:-3e89e54}
API=${ANDROID_API:-33}
mkdir -p "$work" "$out/lib"
src="$work/lsfg-vk-android"
if [[ ! -d "$src/.git" ]]; then
    git clone -q --branch release https://github.com/FrankBarretta/lsfg-vk-android.git "$src"
fi
git -C "$src" checkout -q "$LSFG_COMMIT"
git -C "$src" submodule update --init --recursive --depth 1 -q
git -C "$src" checkout -q -- framegen/src/core/instance.cpp
# Create the frame-generation instance on Nova's driver (Turnip via adrenotools or the
# system driver) so the physical device and AHardwareBuffer import match Nova's device.
python3 - "$src/framegen/src/core/instance.cpp" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
old = '    volkInitialize();\n'
if s.count(old) != 1:
    raise SystemExit('NOVA_LSFG: framegen instance anchor changed')
s = s.replace(old, '''    if (auto gipa = NovaLsfgGetInstanceProcAddr()) volkInitializeCustom(gipa);
    else volkInitialize();
''')
s = s.replace('using namespace LSFG::Core;', 'PFN_vkGetInstanceProcAddr NovaLsfgGetInstanceProcAddr();\n\nusing namespace LSFG::Core;', 1)
p.write_text(s)
print('NOVA_LSFG: framegen instance uses the caller driver')
PY
build="$work/novalsfg-build"
rm -rf "$build"
if [[ "${HOST_BUILD:-0}" == "1" ]]; then
    cmake -G Ninja -S "$repo/native/novalsfg" -B "$build" -DLSFG_SOURCE="$src" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ ${VULKAN_INCLUDE:+-DCMAKE_CXX_FLAGS=-I$VULKAN_INCLUDE -DCMAKE_C_FLAGS=-I$VULKAN_INCLUDE}
else
    NDK=${ANDROID_NDK:-${ANDROID_NDK_LATEST_HOME:-}}
    [[ -f "$NDK/build/cmake/android.toolchain.cmake" ]] || { echo "Android NDK not found"; exit 2; }
    cmake -G Ninja -S "$repo/native/novalsfg" -B "$build" -DLSFG_SOURCE="$src" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a \
        -DANDROID_PLATFORM=android-$API -DANDROID_STL=c++_static
fi
cmake --build "$build" -j"$(nproc)" --target novalsfg
cp "$build/libnovalsfg.so" "$out/lib/"
mkdir -p "$out/licenses"
cp "$src/LICENSE.md" "$out/licenses/lsfg-vk-MIT.md"
echo "NOVA_LSFG: built $(du -h "$out/lib/libnovalsfg.so" | cut -f1) libnovalsfg.so"
if [[ "${HOST_BUILD:-0}" != "1" ]]; then
    "$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm" -D --defined-only "$out/lib/libnovalsfg.so" | grep -E ' T ' | tee "$out/exports.txt"
fi
