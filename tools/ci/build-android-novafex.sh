#!/bin/bash
# Builds libnovafex.so (pinned FEXCore + native/novafex) for Android (bionic, arm64-v8a) with the
# NDK, plus a static bionic novafex_test that runs on any Linux arm64 machine.
#   build-android-novafex.sh <repo> <workdir> <outdir>
#   <outdir>/lib/libnovafex.so  <outdir>/include/novafex.h  <outdir>/novafex_test_static
set -euo pipefail
repo=$(realpath "$1"); work=$(realpath -m "$2"); out=$(realpath -m "$3")
NDK=${ANDROID_NDK:-${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-}}}
[[ -d $NDK ]] || { echo "Android NDK not found"; exit 2; }
API=${ANDROID_API:-33}
FEX_COMMIT=${FEX_COMMIT:-14c92681f4d62cf84d901460e0358de09c8847a7}
mkdir -p "$work" "$out/lib" "$out/include" "$out/logs"
export CCACHE_DIR=${CCACHE_DIR:-$HOME/.cache/ccache}
cd "$work"
if [[ ! -d fex/.git ]]; then
    git init -q fex
    git -C fex remote add origin https://github.com/FEX-Emu/FEX.git
    git -C fex fetch -q --depth 1 origin "$FEX_COMMIT"
    git -C fex checkout -q FETCH_HEAD
    git -C fex submodule update --init --depth 1 External/fmt External/range-v3 External/rpmalloc \
        External/unordered_dense External/vixl External/xxhash External/jemalloc_glibc Source/Common/cpp-optparse
fi
git -C fex checkout -q -- . && git -C fex clean -qfd -e build
# FEX only knows "Linux"; Android is Linux with bionic.
sed -i 's/elseif (NOT (WIN32 OR CMAKE_SYSTEM_NAME STREQUAL "Linux"))/elseif (NOT (WIN32 OR CMAKE_SYSTEM_NAME STREQUAL "Linux" OR CMAKE_SYSTEM_NAME STREQUAL "Android"))/' fex/CMakeLists.txt
# bionic has pthreads in libc; there is no libpthread.
sed -i "s/^set(PTHREAD_LIB pthread)/if(CMAKE_SYSTEM_NAME STREQUAL \"Android\")\n  set(PTHREAD_LIB \"\")\nelse()\n  set(PTHREAD_LIB pthread)\nendif()/" fex/CMakeLists.txt
for p in "$repo"/patches/fex-android/*.patch; do
    [[ -e $p ]] || continue
    git -C fex apply "$p" || { echo "FEX patch failed: $p"; exit 1; }
done
echo 'add_subdirectory(NovaFex/)' >> fex/Source/Tools/CMakeLists.txt
rm -rf fex/Source/Tools/NovaFex && cp -r "$repo/native/novafex" fex/Source/Tools/NovaFex

cmake -S fex -B build-fex-android -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-$API -DANDROID_STL=c++_static \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DENABLE_LTO=OFF -DBUILD_FEXCONFIG=OFF -DBUILD_TESTING=OFF -DBUILD_THUNKS=OFF -DENABLE_CCACHE=OFF \
    -DENABLE_JEMALLOC_GLIBC_ALLOC=OFF -DENABLE_OFFLINE_TELEMETRY=OFF -DTUNE_CPU=none -DTUNE_ARCH=armv8.2-a \
    -DNOVAFEX_ANDROID=ON > "$out/logs/fex-android-cmake.txt" 2>&1 || { tail -60 "$out/logs/fex-android-cmake.txt"; exit 1; }
status=0
cmake --build build-fex-android --target novafex novafex_test_static --parallel "$(nproc)" -- -k 0 \
    > "$out/logs/fex-android-build.txt" 2>&1 || status=$?
grep -E "error:|undefined (reference|symbol)|FAILED:" "$out/logs/fex-android-build.txt" | head -200 > "$out/logs/fex-android-errors.txt" || true
if [[ $status -ne 0 ]]; then head -120 "$out/logs/fex-android-errors.txt"; exit "$status"; fi
cp "$(find build-fex-android -name libnovafex.so | head -n 1)" "$out/lib/"
cp "$(find build-fex-android -type f -name novafex_test_static | head -n 1)" "$out/novafex_test_static"
cp "$repo/native/novafex/novafex.h" "$out/include/"
"$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf" -d "$out/lib/libnovafex.so" | tee "$out/logs/novafex-dynamic.txt"
ls -la "$out/lib" "$out"
