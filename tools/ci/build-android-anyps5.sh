#!/bin/bash
set -euo pipefail
repo=$(realpath "$1"); work=$(realpath -m "$2"); out=$(realpath -m "$3")
NDK=${ANDROID_NDK:-${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-}}}
source_dir="$work/anyps5"
if [[ ! -d "$source_dir/.git" ]]; then
    git clone --no-checkout https://github.com/boykopovar/AnyPS5.git "$source_dir"
fi
git -C "$source_dir" checkout --detach 9caecfd2d5a822be9daf84c69c7c33c7fafe52b9
git -C "$source_dir" submodule update --init --depth 1 3rdparty/SPIRV-Headers 3rdparty/SPIRV-Tools 3rdparty/glslang 3rdparty/Vulkan-Headers
host_glslang=${NOVA_ANYPS5_HOST_GLSLANG:-}
if [[ -z "$host_glslang" ]]; then
    cmake -S "$source_dir/3rdparty/glslang" -B "$work/anyps5-host-glslang" -G Ninja -DCMAKE_BUILD_TYPE=Release -DENABLE_OPT=OFF -DGLSLANG_TESTS=OFF -DENABLE_GLSLANG_BINARIES=ON
    cmake --build "$work/anyps5-host-glslang" --target glslang-standalone -j "${NOVA_BUILD_JOBS:-4}"
    host_glslang="$work/anyps5-host-glslang/StandAlone/glslang"
fi
cmake -S "$repo/native/anyps5" -B "$work/build-anyps5-android" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 -DANDROID_STL=c++_shared \
    -DANYPS5_SOURCE_DIR="$source_dir" -DNOVA_ANYPS5_BUILD_AGC=ON -DBUILD_TESTING=OFF \
    -DNOVA_ANYPS5_HOST_GLSLANG="$host_glslang"
cmake --build "$work/build-anyps5-android" --target nova_anyps5_renderer -j "${NOVA_BUILD_JOBS:-4}"
tc="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
python3 "$repo/native/anyps5/renderer/export_manifest.py" "$tc/llvm-nm" "$work/build-anyps5-android/renderer/libnova_anyps5_renderer.so" "$repo/native/anyps5/anyps5_exports.inc"
python3 "$repo/native/anyps5/apply_kyty.py" "$work/kyty" "$source_dir" "$work/build-anyps5-android"
mkdir -p "$out/lib" "$out/source"
cp "$work/build-anyps5-android/renderer/libnova_anyps5_renderer.so" "$out/lib/"
cp "$NDK/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so" "$out/lib/"
"$tc/llvm-strip" --strip-unneeded "$out/lib/libnova_anyps5_renderer.so"
tar --exclude=.git -czf "$out/source/AnyPS5-Android-corresponding-source.tar.gz" -C "$work" anyps5 -C "$repo" native/anyps5
