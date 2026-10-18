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
# Existing staged repositories can have missing or interrupted submodule checkouts.
git -C kyty submodule update --init --recursive --depth 1 --jobs "${NOVA_BUILD_JOBS:-1}"
# Recover Kyty from the most recent successfully compiled Android base, preserving
# its entire working runtime. The current monolithic 0.9.9 Kyty patch conflicts
# with memory.cpp and MUST NOT be applied partially. 0.9.9 FEX/ARM64 fixes come
# from the current branch; add the isolated EOP batching change below.
base_sha=740c60496616f265e1edec54f0248ba728946a75
base_patch="$work/kyty-nova-arm64-base.patch"
git -C "$repo" fetch --no-tags --depth=1 origin "$base_sha"
git -C "$repo" show "$base_sha:patches/kyty-nova-arm64.patch" > "$base_patch"
while IFS= read -r p || [[ -n "$p" ]]; do
    [[ -z "$p" || "$p" == \#* ]] && continue
    patch_file="$repo/patches/$p"
    if [[ "$p" == "kyty-nova-arm64.patch" ]]; then
        patch_file="$base_patch"
    fi
    echo "NOVA_PATCH: validate $p"
    git -C kyty apply --check "$patch_file" || { echo "NOVA_PATCH: $p check failed"; exit 1; }
    git -C kyty apply "$patch_file" || { echo "NOVA_PATCH: $p apply failed"; exit 1; }
    if [[ "$p" == "kyty-nova-arm64.patch" ]]; then
        # This specific EOP condition was introduced by the 0.9.9 Kyty diff.
        # Declare it BEFORE selector 3 is normalized to selector 2, so the
        # following batching overlay only affects the combined write+interrupt
        # form and never alters semantics of selector 1/2.
        python3 - "$work/kyty/src/graphics/guest_gpu/command_processor/pm4Handlers.cpp" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
anchor = 'uint32_t interrupt_context_id = buffer[6] & 0x07ffffffu;'
if s.count(anchor) != 1 or 'nova_defer_release_flush' in s:
    raise SystemExit('NOVA_GPU: unexpected RELEASE_MEM source; refusing unsafe edit')
s = s.replace(anchor,
              anchor + '\n\tconst bool nova_defer_release_flush = interrupt_selector == 0x03;',
              1)
p.write_text(s)
print('NOVA_GPU: guarded selector-3 asynchronous EOP handling enabled')
PY
    fi
done < "$repo/patches/linux-core.series"
# Release performance profile: keep all guest GPU correctness and game-boot patches,
# but disable the expensive per-write diagnostic ring in normal device builds.
# NOVA_GPU_TRACE_WRITES=1 restores full write tracing for troubleshooting.
if [[ "${NOVA_GPU_TRACE_WRITES:-0}" != "1" ]]; then
    python3 - "$work/kyty/src/graphics/guest_gpu/graphicsRun.cpp" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
old = 'g_nova_writes[g_nova_write_pos++ % NOVA_WRITES] = {a, value, queue, kind};'
new = '/* NOVA_PERF: omit hot-path GPU diagnostic ring writes in release builds */'
if s.count(old) != 1:
    raise SystemExit('NOVA_PERF: GPU diagnostic anchor changed; refusing edit')
s = s.replace(old, new, 1)
p.write_text(s)
print('NOVA_PERF: hot-path GPU write diagnostics disabled (GPU wait semantics unchanged)')
PY
fi
# GPU EOP compatibility: log exact unsupported packet fields before upstream fatal.
python3 - "$work/kyty/src/graphics/guest_gpu/graphicsRun.cpp" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
anchor = '\tEXIT("unknown event type\\n");'
if s.count(anchor) != 2:
    raise SystemExit('NOVA_EOP: unknown-event anchors changed; refusing edit')
msg = (
    '\tstd::fprintf(stderr, "NOVA_EOP_UNSUPPORTED: policy=0x%x dest=0x%x type=0x%x action=0x%x index=0x%x source=0x%x interrupt=0x%x context=0x%x value=0x%llx\\n",\n'
    '\t             cache_policy, event_write_dest, eop_event_type, cache_action, event_index, event_write_source, interrupt_selector, interrupt_context_id,\n'
    '\t             static_cast<unsigned long long>(value));\n'
)
s = s.replace(anchor, msg + anchor, 1)
p.write_text(s)
print('NOVA_EOP: unsupported RELEASE_MEM packet diagnostics enabled')
PY
# Super Meat Boy 3D: RELEASE_MEM events 0x2d and 0x2b must write their 64-bit values
# and signal the requested EOP interrupt. Keep all other event combinations unchanged.
python3 - "$work/kyty/src/graphics/guest_gpu/graphicsRun.cpp" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
needle = 'if (event_index == 0x00 && !with_interrupt) {'
if s.count(needle) != 2:
    raise SystemExit('NOVA_EOP_FIX: expected two 64-bit no-interrupt guards')
first = s.index(needle)
if 'case 0x2d:' not in s[max(0,first-150):first]:
    raise SystemExit('NOVA_EOP_FIX: first guard is not event 0x2d')
s = s[:first] + s[first:].replace(needle, 'if (event_index == 0x00 && (!with_interrupt || eop_event_type == 0x2d || eop_event_type == 0x2b)) {', 1)
p.write_text(s)
assert s.count('(!with_interrupt || eop_event_type == 0x2d || eop_event_type == 0x2b)') == 1
print('NOVA_EOP_FIX: 64-bit 0x2d write and interrupt enabled')
PY
# AnyPS5-derived GPU completion/shader adaptation must reach the compiled source.
git -C kyty apply --check "$repo/patches/kyty-anyps5-gpu-completion.patch"
git -C kyty apply "$repo/patches/kyty-anyps5-gpu-completion.patch"
git -C kyty apply --check "$repo/patches/kyty-android-shader-features.patch"
git -C kyty apply "$repo/patches/kyty-android-shader-features.patch"
git -C "$work/kyty" apply --check "$repo/patches/kyty-anyps5-compute-workgroups.patch"
git -C "$work/kyty" apply "$repo/patches/kyty-anyps5-compute-workgroups.patch"
git -C "$work/kyty" apply --check "$repo/patches/kyty-mesh-wave32.patch"
git -C "$work/kyty" apply "$repo/patches/kyty-mesh-wave32.patch"
python3 "$repo/tests/test_mesh_workgroup.py" "$work/kyty"
git -C "$work/kyty" apply --check "$repo/patches/kyty-guest-memory-fastpath.patch"
git -C "$work/kyty" apply "$repo/patches/kyty-guest-memory-fastpath.patch"
git -C "$work/kyty" apply --check "$repo/patches/kyty-agc-packet-fastpath.patch"
git -C "$work/kyty" apply "$repo/patches/kyty-agc-packet-fastpath.patch"
python3 "$repo/tests/test_agc_packet_fastpath.py" "$work/kyty"
git -C "$work/kyty" apply --check "$repo/patches/kyty-agc-native-packets.patch"
git -C "$work/kyty" apply "$repo/patches/kyty-agc-native-packets.patch"
python3 "$repo/tests/test_agc_native_packets.py" "$work/kyty"
# Native shader semantic metadata and AJM/Opus input/output guest views.
python3 "$repo/tools/ci/patch-guest-hotpaths.py" "$work/kyty"
python3 "$repo/tests/test_guest_hotpaths.py" "$work/kyty"
# 0.9.25: prevent repetitive native ARM64 guest faults in AGC Cx register patches
# and command buffer cursor paths, without changing PM4 packets or callback ABI.
python3 "$repo/tools/ci/patch-agc-cb-hotpaths.py" "$work/kyty"
python3 "$repo/tests/test_agc_cb_hostviews.py" "$work/kyty"
# Persistent per-title Vulkan pipeline cache: android process exits without Kyty
# destructor; snapshot live driver cache after pipeline warmup. Optimize high
# guest-address AGC vertex metadata copies without altering Vulkan sync.
python3 "$repo/tools/ci/patch-persistent-shaders.py" "$work/kyty"
python3 "$repo/tests/test_persistent_shader_cache.py" "$work/kyty"
# 0.9.27: bounded host views for measured GPU-result/interpolant traps.
python3 "$repo/tools/ci/patch-gpu-hotpaths.py" "$work/kyty"
python3 "$repo/tests/test_gpu_hotpaths.py" "$work/kyty"
python3 "$repo/tools/ci/patch-renderer-performance.py" "$work/kyty"
python3 "$repo/tests/test_translated_shader_disk.py" "$work/kyty"
python3 "$repo/tests/test_render_overhead.py" "$work/kyty"
python3 "$repo/tests/test_pipeline_libraries.py" "$work/kyty"
# 0.9.30: measured wait validation, query reads and shader-relative relocations.
python3 "$repo/tools/ci/patch-measured-accesses.py" "$work/kyty"
python3 "$repo/tests/test_measured_accesses.py" "$work/kyty"
# 0.9.31: truthful GPU wait diagnostics; translated guest views for the timed pthread,
# nanosleep/clock and semaphore entry points (Luna's measured hostemu hot paths).
python3 "$repo/tools/ci/patch-0931-gpu-watch.py" "$work/kyty"
python3 "$repo/tests/test_0931_gpu_wait_diag.py" "$work/kyty"
python3 "$repo/tools/ci/patch-0931-pthread-guest-objects.py" "$work/kyty"
python3 "$repo/tests/test_0931_pthread_xlat.py" "$work/kyty"
# Large Unreal shader cache entries and deterministic guest stack-query outputs.
python3 "$repo/tests/test_large_shader_archive.py"
python3 "$repo/tools/ci/patch-0933-stack-outputs.py" "$work/kyty"
python3 "$repo/tests/test_0933_stack_outputs.py" "$work/kyty"
# 0.9.34: explicit Android cache guards and bounded Luna correlation.
python3 "$repo/tools/ci/patch-0934-cache-activation.py" "$work/kyty"
python3 "$repo/tests/test_0934_cache_activation.py" "$work/kyty"
python3 "$repo/tools/ci/patch-0934-luna-correlation.py" "$work/kyty"
python3 "$repo/tests/test_0934_luna_correlation.py" "$work/kyty"
# 0.9.35: explicit successful-map guest pointer and processed-count publication.
python3 "$repo/tools/ci/patch-0935-batch-map-writeback.py" "$work/kyty"
python3 "$repo/tests/test_0935_batch_map_writeback.py" "$work/kyty"
python3 "$repo/tools/ci/patch-0936-luna-constructor.py" "$work/kyty"
python3 "$repo/tools/ci/patch-controller-output.py" "$work/kyty"
python3 "$repo/tools/ci/patch-ever-render-costs.py" "$work/kyty"
python3 "$repo/tools/ci/patch-ever-gpu-labels.py" "$work/kyty"
python3 "$repo/tools/ci/patch-ever-pm4-fetch.py" "$work/kyty"
python3 "$repo/tests/test_ever_pm4_fetch.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_ever_pm4_fetch.py" "$work/kyty"
python3 "$repo/tests/test_ever_gpu_labels.py" "$work/kyty"
python3 "$repo/tools/ci/patch-novaps5-readback-telemetry.py" "$work/kyty"
python3 "$repo/tests/test_novaps5_readback_safety_expanded.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_novaps5_readback_safety_expanded.py" "$work/kyty"
python3 "$repo/tests/test_novaps5_readback_ordering.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_novaps5_readback_ordering.py" "$work/kyty"
python3 "$repo/tests/test_ever_render_costs.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_ever_render_costs.py" "$work/kyty"
python3 "$repo/tests/test_controller_output.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_controller_output.py" "$work/kyty"
cp "$repo/native/novafex/guest_memory.cpp" "$work/kyty/src/novaGuestMemory.cpp"
cat >> "$work/kyty/CMakeLists.txt" <<'CMAKE'
if(KYTY_ANDROID)
    target_sources(kyty_emulator PRIVATE "${KYTY_SOURCE_DIR}/novaGuestMemory.cpp")
    target_link_options(kyty_emulator PRIVATE -Wl,--wrap=memset,--wrap=memcpy,--wrap=memmove,--wrap=memcmp)
endif()
CMAKE
python3 "$repo/tests/test_compute_workgroup.py" "$work/kyty"
python3 "$repo/tests/test_shader_features.py" "$work/kyty"
python3 "$repo/tests/test_gpu_completion.py" "$work/kyty"
# Execute the host regressions against the sources that are about to be compiled.
python3 "$repo/tests/test_native_startup.py" "$work/kyty"
python3 "$repo/tests/test_release_mem.py" "$work/kyty"
# 0.9.38: owner-measured tiny label reads and Super Meat Boy EOP drains.
# The earlier telemetry-only wait contract runs BEFORE this separate optimization.
python3 "$repo/tools/ci/patch-eop-label-reads.py" "$work/kyty"
python3 "$repo/tests/test_eop_label_reads.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_eop_label_reads.py" "$work/kyty"
python3 "$repo/tests/test_ever_gpu_labels.py" "$work/kyty"
python3 "$repo/tests/test_gpu_completion.py" "$work/kyty"
python3 "$repo/tests/test_ever_pm4_fetch.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_ever_pm4_fetch.py" "$work/kyty"
python3 "$repo/tests/test_ever_render_costs.py" "$work/kyty"
SANITIZE=1 python3 "$repo/tests/test_ever_render_costs.py" "$work/kyty"
python3 "$repo/tests/test_release_mem.py" "$work/kyty"

# Forward-port the independently tested upstream FP16 correctness fix.
python3 "$repo/tools/ci/patch-kyty-latest-fp16.py" "$work/kyty"
python3 "$repo/tests/test_kyty_fp16.py" "$work/kyty"
ASAN_OPTIONS=detect_leaks=0 SANITIZE=1 bash "$repo/tools/ci/test-kytyplus-package.sh"

# Ever Forward: known constant-label fault reconciliation; retain ordinary downloads on misses.
python3 "$repo/tools/ci/patch-ever-label-publication.py" "$work/kyty"
python3 "$repo/tests/test_ever_label_publication.py" "$work/kyty"
ASAN_OPTIONS=detect_leaks=0 SANITIZE=1 python3 "$repo/tests/test_ever_label_publication.py" "$work/kyty"

# 0.9.45: suspend only the PM4 queue waiting for a recorded label, not the GPU thread.
python3 "$repo/tools/ci/patch-ever-cooperative-label-waits.py" "$work/kyty"
python3 "$repo/tests/test_ever_cooperative_label_waits.py" "$work/kyty"
ASAN_OPTIONS=detect_leaks=0 SANITIZE=1 python3 "$repo/tests/test_ever_cooperative_label_waits.py" "$work/kyty"
python3 "$repo/tests/test_ever_label_poll_vulkan.py" "$work/kyty"

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

# FetchContent may repeat PATCH_COMMAND after a reconfigure. Accept only a
# clean forward application or a fully reverse-applicable existing patch.
cat > "$work/kyty/3rdparty/nova-apply-zarchive.cmake" <<'CMAKE'
if(NOT DEFINED NOVA_GIT OR NOT DEFINED NOVA_PATCH)
    message(FATAL_ERROR "zarchive: missing Git executable or patch")
endif()
execute_process(COMMAND "${NOVA_GIT}" apply --reverse --check --ignore-whitespace "${NOVA_PATCH}"
    RESULT_VARIABLE reverse_result OUTPUT_VARIABLE reverse_output ERROR_VARIABLE reverse_error)
if(reverse_result EQUAL 0)
    message(STATUS "NOVA_ZARCHIVE: complete reader patch already applied")
else()
    execute_process(COMMAND "${NOVA_GIT}" apply --check --ignore-whitespace "${NOVA_PATCH}"
        RESULT_VARIABLE check_result OUTPUT_VARIABLE check_output ERROR_VARIABLE check_error)
    if(NOT check_result EQUAL 0)
        message(FATAL_ERROR "zarchive reader patch is incompatible or partially applied:\n${check_output}\n${check_error}\nReverse check:\n${reverse_error}")
    endif()
    execute_process(COMMAND "${NOVA_GIT}" apply --ignore-whitespace "${NOVA_PATCH}"
        RESULT_VARIABLE apply_result OUTPUT_VARIABLE apply_output ERROR_VARIABLE apply_error)
    if(NOT apply_result EQUAL 0)
        message(FATAL_ERROR "zarchive reader patch failed:\n${apply_output}\n${apply_error}")
    endif()
    execute_process(COMMAND "${NOVA_GIT}" apply --reverse --check --ignore-whitespace "${NOVA_PATCH}"
        RESULT_VARIABLE verify_result OUTPUT_VARIABLE verify_output ERROR_VARIABLE verify_error)
    if(NOT verify_result EQUAL 0)
        message(FATAL_ERROR "zarchive reader patch verification failed:\n${verify_output}\n${verify_error}")
    endif()
    message(STATUS "NOVA_ZARCHIVE: reader patch applied and verified")
endif()
CMAKE
python3 - "$work/kyty/3rdparty/CMakeLists.txt" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
old = '\tPATCH_COMMAND "${GIT_EXECUTABLE}" apply --ignore-whitespace\n\t\t"${CMAKE_CURRENT_SOURCE_DIR}/patches/zarchive-reader.patch"'
new = '\tPATCH_COMMAND "${CMAKE_COMMAND}"\n\t\t"-DNOVA_GIT=${GIT_EXECUTABLE}"\n\t\t"-DNOVA_PATCH=${CMAKE_CURRENT_SOURCE_DIR}/patches/zarchive-reader.patch"\n\t\t-P "${CMAKE_CURRENT_SOURCE_DIR}/nova-apply-zarchive.cmake"'
if s.count(old) != 1:
    raise SystemExit('NOVA_ZARCHIVE: expected one pinned patch command; refusing edit')
p.write_text(s.replace(old, new, 1))
PY

bash "$repo/tools/ci/build-android-anyps5.sh" "$repo" "$work" "$out"
cmake -S kyty -B build-kyty-android -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-$API -DANDROID_STL=c++_shared \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DCMAKE_C_FLAGS="-Wno-error=implicit-function-declaration" -DKYTY_BUILD_LAUNCHER=OFF -DBUILD_TESTING=OFF \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384" \
    -DNOVAFEX_DIR="$novafex" -DFFMPEG_PREBUILT_DIR="$ffmpeg" -DNOVA_ADRENOTOOLS_SRC="$work/adrenotools" \
    > "$out/logs/kyty-android-cmake.txt" 2>&1 || { tail -80 "$out/logs/kyty-android-cmake.txt"; exit 1; }
status=0
cmake --build build-kyty-android --target kyty_emulator --parallel "${NOVA_BUILD_JOBS:-1}" -- -k 0 > "$out/logs/kyty-android-build.txt" 2>&1 || status=$?
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
# Build the installer independently of the game CPU/GPU runtime.
cmake -S "$repo/native/pkg" -B "$work/build-novapkg-android" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-$API \
    -DANDROID_STL=c++_static -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build "$work/build-novapkg-android" --target novapkg --parallel "${NOVA_BUILD_JOBS:-1}"
cp "$work/build-novapkg-android/libnovapkg.so" "$out/lib/"
mkdir -p "$out/source"
tar -czf "$out/source/KytyPlus-PKG-corresponding-source.tar.gz" -C "$repo" native/pkg nova-android/src/com/kaminofilms/novaps5/PkgInstaller.java LICENSES/KytyPlus-NOTICE.txt
ls -la "$out/lib"



# Publish the exact patched renderer and its source dependencies alongside the APK.
mkdir -p "$out/source"
tar --exclude='.git' -czf "$out/source/Kyty-Android-corresponding-source.tar.gz" -C "$work" kyty adrenotools

