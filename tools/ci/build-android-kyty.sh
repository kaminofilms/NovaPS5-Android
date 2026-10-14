#!/bin/bash
# Kyty for Android (bionic arm64): libmain.so (SDL_main) + libSDL3.so, linked with libnovafex.so.
#   build-android-kyty.sh <repo> <workdir> <outdir> <novafex-dist> <ffmpeg-dist>
#   <outdir>/lib/*.so  <outdir>/sdl-java/org/libsdl/app/*.java  <outdir>/logs/
set -euo pipefail
repo=$(realpath "$1"); work=$(realpath -m "$2"); out=$(realpath -m "$3"); novafex=$(realpath "$4"); ffmpeg=$(realpath "$5")
NDK=${ANDROID_NDK:-${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-}}}
API=${ANDROID_API:-33}
KYTY_COMMIT=${KYTY_COMMIT:-df5b9b92be7dfd463b47756b707d6d356a9f0550}
mkdir -p "$work" "$out/lib" "$out/logs"
export CCACHE_DIR=${CCACHE_DIR:-$HOME/.cache/ccache}
cd "$work"
if [[ ! -d kyty/.git ]]; then
    git init -q kyty
    git -C kyty remote add origin https://github.com/KytyPS5/KytyPS5.git
    git -C kyty fetch -q --depth 1 origin "$KYTY_COMMIT"
    git -C kyty checkout -q FETCH_HEAD
    git -C kyty submodule update --init --recursive --depth 1 -q
fi
if [[ ! -d adrenotools/.git ]]; then
    git clone -q https://github.com/bylaws/libadrenotools adrenotools
    git -C adrenotools checkout -q 8fae8ce254dfc1344527e05301e43f37dea2df80
    git -C adrenotools submodule update --init --recursive -q
fi
git -C kyty checkout -q -- . && git -C kyty clean -qfd -e build
for p in $(grep -v '^#' "$repo/patches/linux-core.series"); do
    git -C kyty apply "$repo/patches/$p" || { echo "patch failed: $p"; exit 1; }
done
cmake -S kyty -B build-kyty-android -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-$API -DANDROID_STL=c++_static \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DCMAKE_C_FLAGS="-Wno-error=implicit-function-declaration" -DKYTY_BUILD_LAUNCHER=OFF -DBUILD_TESTING=OFF \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384" \
    -DNOVAFEX_DIR="$novafex" -DFFMPEG_PREBUILT_DIR="$ffmpeg" -DNOVA_ADRENOTOOLS_SRC="$work/adrenotools" \
    > "$out/logs/kyty-android-cmake.txt" 2>&1 || { tail -80 "$out/logs/kyty-android-cmake.txt"; exit 1; }
status=0
cmake --build build-kyty-android --target kyty_emulator --parallel "$(nproc)" -- -k 0 > "$out/logs/kyty-android-build.txt" 2>&1 || status=$?
grep -E "error:|undefined (reference|symbol)|FAILED:" "$out/logs/kyty-android-build.txt" | head -400 > "$out/logs/kyty-android-errors.txt" || true
if [[ $status -ne 0 ]]; then head -150 "$out/logs/kyty-android-errors.txt"; exit "$status"; fi
cp "$(find build-kyty-android -name libmain.so | head -n 1)" "$out/lib/"
cp "$(find build-kyty-android -name libSDL3.so | head -n 1)" "$out/lib/"
cp "$novafex/lib/libnovafex.so" "$out/lib/"
for hook in hook_impl main_hook file_redirect_hook gsl_alloc_hook; do
    cp "$(find build-kyty-android -name "lib$hook.so" | head -n 1)" "$out/lib/"
done
TC=$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin
"$TC/llvm-strip" --strip-unneeded "$out/lib/libSDL3.so"
rm -rf "$out/sdl-java"; mkdir -p "$out/sdl-java"
cp -r kyty/3rdparty/SDL3/android-project/app/src/main/java/org "$out/sdl-java/"
for lib in "$out"/lib/*.so; do
    echo "== ${lib##*/}"; "$TC/llvm-readelf" -d "$lib" | grep -E "NEEDED|SONAME"
done | tee "$out/logs/android-libs.txt"
ls -la "$out/lib"
