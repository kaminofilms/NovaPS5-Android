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
# Apply the actual 0.9.9 patches. The generated large Kyty diff may contain
# stale line counts in one or more @@ hunk headers; --recount recomputes those
# counts from the patch content, preserving all 0.9.9 code rather than
# substituting the 0.9.8 implementation.
while IFS= read -r p || [[ -n "$p" ]]; do
    [[ -z "$p" || "$p" == \#* ]] && continue
    patch_file="$repo/patches/$p"
    echo "NOVA_PATCH: validate $p"
    if [[ "$p" == "kyty-nova-arm64.patch" ]]; then
        # Git --recount repairs stale hunk lengths in modified-file diffs but can
        # incorrectly classify new-file hunks as depending on existing content.
        # Keep all 0.9.9 code: split at diff boundaries and apply new files
        # without recounting their already-correct /dev/null hunks.
        revised="$work/kyty-modified-files.patch"
        created="$work/kyty-new-files.patch"
        python3 - "$patch_file" "$revised" "$created" <<'PY'
import pathlib, re, sys
src = pathlib.Path(sys.argv[1]).read_bytes()
parts = re.split(rb'(?=^diff --git )', src, flags=re.MULTILINE)
modified, new_files = [], []
for section in parts:
    if not section.strip():
        continue
    if not section.startswith(b'diff --git '):
        raise SystemExit('NOVA_PATCH: invalid patch preamble')
    if re.search(rb'^new file mode ', section, re.MULTILINE):
        new_files.append(section)
    else:
        modified.append(section)
if not modified or not new_files:
    raise SystemExit('NOVA_PATCH: expected modified and new-file sections')
pathlib.Path(sys.argv[2]).write_bytes(b''.join(modified))
pathlib.Path(sys.argv[3]).write_bytes(b''.join(new_files))
print('NOVA_PATCH: grouped', len(modified), 'modified-file diffs and',
      len(new_files), 'new-file diffs')
PY
        git -C kyty apply --recount --check "$revised" || {
            echo "NOVA_PATCH: modified-file patch validation failed"; exit 1;
        }
        git -C kyty apply --check "$created" || {
            echo "NOVA_PATCH: new-file patch validation failed"; exit 1;
        }
        git -C kyty apply --recount "$revised"
        git -C kyty apply "$created"
    else
        git -C kyty apply --check "$patch_file" || { echo "patch check failed: $p"; exit 1; }
        git -C kyty apply "$patch_file" || { echo "patch failed: $p"; exit 1; }
    fi
done < "$repo/patches/linux-core.series"
# Execute the host regressions against the sources that are about to be compiled.
python3 "$repo/tests/test_native_startup.py" "$work/kyty"
python3 "$repo/tests/test_release_mem.py" "$work/kyty"
# SDL's AAudio backend: report stream errors, disconnects and underflows (debug LOGI is off
# upstream) so the session log shows why audio stops.
aaudio=kyty/3rdparty/SDL3/src/audio/aaudio/SDL_aaudio.c
git -C kyty/3rdparty/SDL3 checkout -q -- src/audio/aaudio/SDL_aaudio.c
python3 - "$aaudio" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old = '#if 0\n#define LOGI(...) SDL_Log(__VA_ARGS__);'
assert old in s, 'SDL_aaudio.c LOGI block not found'
s = s.replace(old, '#if 1\n#define LOGI(...) SDL_Log(__VA_ARGS__);', 1)
# The per-callback underflow line would flood the log; keep a count instead.
s = s.replace('LOGI("Audio playback underflow, missed %zu frames", (callback_bytes - size) / framesize);',
              '{ static int n = 0; if (n++ % 500 == 0) SDL_Log("NOVA_AAUDIO: playback underflow #%d (missed %zu frames)", n, (callback_bytes - size) / framesize); }', 1)
s = s.replace('LOGI("SDL AAudioStream_requestStart OK");', '', 1)
open(p, 'w').write(s)
PY
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


