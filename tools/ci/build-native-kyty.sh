#!/bin/bash
# Builds the native AArch64 Kyty core on a Linux ARM64 host:
#   libnovafex.so (pinned FEX + native/novafex), Kyty (pinned source + patches/linux-core.series)
# and packages it for the DroidDeck rootfs with its own glibc/libstdc++ (interpreter rewritten
# to the installed location). Usage: build-native-kyty.sh <repo> <workdir> <outdir>
#   <outdir>/native/        packaged core for the APK (provision.py --native-dir)
#   <outdir>/ci/            same core with the host loader (for CI boot tests)
#   <outdir>/logs/          build logs
set -euo pipefail
repo=$(realpath "$1"); work=$(realpath -m "$2"); out=$(realpath -m "$3")
FEX_COMMIT=${FEX_COMMIT:-14c92681f4d62cf84d901460e0358de09c8847a7}
KYTY_COMMIT=${KYTY_COMMIT:-df5b9b92be7dfd463b47756b707d6d356a9f0550}
INSTALL_DIR=/opt/novaps5/linux-runtime/native
mkdir -p "$work" "$out/logs" "$out/native" "$out/ci"
export CCACHE_DIR=${CCACHE_DIR:-$HOME/.cache/ccache} CCACHE_MAXSIZE=${CCACHE_MAXSIZE:-4G}
cd "$work"

if [[ ! -d fex/.git ]]; then
    git init -q fex
    git -C fex remote add origin https://github.com/FEX-Emu/FEX.git
    git -C fex fetch -q --depth 1 origin "$FEX_COMMIT"
    git -C fex checkout -q FETCH_HEAD
    git -C fex submodule update --init --depth 1 External/fmt External/range-v3 External/rpmalloc \
        External/unordered_dense External/vixl External/xxhash External/jemalloc_glibc Source/Common/cpp-optparse
    echo 'add_subdirectory(NovaFex/)' >> fex/Source/Tools/CMakeLists.txt
fi
rm -rf fex/Source/Tools/NovaFex && cp -r "$repo/native/novafex" fex/Source/Tools/NovaFex
cmake -S fex -B build-fex -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DENABLE_LTO=OFF -DBUILD_FEXCONFIG=OFF \
    -DBUILD_TESTING=OFF -DBUILD_THUNKS=OFF -DENABLE_JEMALLOC_GLIBC_ALLOC=OFF -DENABLE_CCACHE=OFF > "$out/logs/fex-cmake.txt" 2>&1
cmake --build build-fex --target novafex novafex_test --parallel "$(nproc)" > "$out/logs/fex-build.txt" 2>&1 || { tail -80 "$out/logs/fex-build.txt"; exit 1; }
mkdir -p novafex-dist/include novafex-dist/lib
cp "$repo/native/novafex/novafex.h" novafex-dist/include/
cp "$(find build-fex -name libnovafex.so | head -n 1)" novafex-dist/lib/
"$(find build-fex -type f -name novafex_test -perm /111 | head -n 1)" > "$out/logs/novafex-test.txt" 2>&1 || true
grep -q 'NOVAFEX_TEST: ALL PASS' "$out/logs/novafex-test.txt" || { cat "$out/logs/novafex-test.txt"; exit 1; }

if [[ ! -d kyty/.git ]]; then
    git init -q kyty
    git -C kyty remote add origin https://github.com/KytyPS5/KytyPS5.git
    git -C kyty fetch -q --depth 1 origin "$KYTY_COMMIT"
    git -C kyty checkout -q FETCH_HEAD
    git -C kyty submodule update --init --recursive --depth 1 -q
fi
git -C kyty checkout -q -- . && git -C kyty clean -qfd -e build
for p in $(grep -v '^#' "$repo/patches/linux-core.series"); do
    git -C kyty apply "$repo/patches/$p" || { echo "patch failed: $p"; exit 1; }
done
cmake -S kyty -B build-kyty -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_C_FLAGS="-Wno-error=implicit-function-declaration" -DKYTY_BUILD_LAUNCHER=OFF -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DNOVAFEX_DIR="$work/novafex-dist" > "$out/logs/kyty-cmake.txt" 2>&1 || { tail -60 "$out/logs/kyty-cmake.txt"; exit 1; }
status=0
cmake --build build-kyty --target kyty_emulator --parallel "$(nproc)" -- -k 0 > "$out/logs/kyty-build.txt" 2>&1 || status=$?
grep -E "error:|undefined reference|FAILED:" "$out/logs/kyty-build.txt" | head -300 > "$out/logs/kyty-errors.txt" || true
if [[ $status -ne 0 ]]; then head -80 "$out/logs/kyty-errors.txt"; exit "$status"; fi

core=$(find build-kyty -type f -name kyty_emulator -perm /111 | head -n 1)
for dir in "$out/native" "$out/ci"; do
    cp "$core" "$dir/kyty_emulator"
    cp novafex-dist/lib/libnovafex.so "$dir/"
done
# The DroidDeck rootfs ships a newer glibc/libstdc++ than this build host (its libasound needs
# GLIBC_2.43), so the core uses the system C runtime; only Nova's own libraries are bundled.
ldd "$out/ci/kyty_emulator" | tee "$out/logs/ldd.txt"
# DroidDeck's touch overlay and hardware pads are fake evdev nodes (FAKE_EVDEV_MEMFD_PATHS);
# its reader is preloaded so SDL sees them as gamepads. Native AArch64 build of the same source.
g++ -shared -fPIC -O2 -w -pthread -std=c++17 -static-libstdc++ -static-libgcc -Wl,--exclude-libs,ALL \
    -o "$out/native/libfakeinput.so" "$repo/vendor/droiddeck-0.1.7/app/src/main/cpp/fakeinput_steam.cpp" -ldl
patchelf --set-rpath '$ORIGIN' "$out/ci/kyty_emulator"
patchelf --set-rpath '$ORIGIN' "$out/native/kyty_emulator"
"$out/ci/kyty_emulator" --help > "$out/logs/cli-preflight.txt" 2>&1 || true
python3 - "$repo" "$out" "$KYTY_COMMIT" <<'PY'
import hashlib, json, sys
from pathlib import Path
repo, out, commit = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
series = [n for n in (repo/'patches/linux-core.series').read_text().split() if n.endswith('.patch')]
manifest = {'sha256': h(out/'native/kyty_emulator'), 'source_commit': commit,
            'patches': {n: h(repo/'patches'/n) for n in series},
            'files': {p.name: h(p) for p in sorted((out/'native').iterdir())}}
(out/'native-core.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
PY
ls -la "$out/native"
