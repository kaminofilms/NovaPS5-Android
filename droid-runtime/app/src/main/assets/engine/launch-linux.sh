#!/bin/bash
# Nova PS5 0.4: native AArch64 Kyty (embedded FEXCore), or Linux x86-64 Kyty through standalone FEX.
# Every stage prints NOVA_STAGE: <id> <name> PASS|FAIL|DEGRADED|UNVERIFIED.
set -Eeuo pipefail
step() { echo "== STEP $(date -u +%H:%M:%S) $*"; }
stage() { echo "NOVA_STAGE: $1 $2"; }
trap 'status=$?; echo "NOVA_EXIT: Linux Kyty launch ended with status $status"; exit "$status"' EXIT
trap 'status=$?; echo "NOVA_ERROR: Linux launcher line $LINENO status $status" >&2; exit "$status"' ERR
base=/opt/novaps5
runtime=$base/linux-runtime
guest=$runtime/guest
fex=$runtime/host/usr/bin/FEX
core=$base/linux-kyty/kyty_emulator
game=${1:?Missing selected game directory}
[[ "$game" = /storage/* ]] || { echo 'NOVA_ERROR: Expected Linux /storage game path'; exit 64; }
[[ -r "$game/eboot.bin" ]] || { echo 'NOVA_ERROR: eboot.bin is not readable'; exit 66; }
[[ -x "$fex" && -x "$runtime/host/usr/bin/FEXServer" ]] || { echo 'NOVA_ERROR: Standalone FEX/FEXServer missing'; exit 67; }
[[ -x "$core" && -r "$guest/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" ]] || { echo 'NOVA_ERROR: Linux Kyty or x86-64 glibc loader missing'; exit 68; }
stage A 'Android runtime files PASS'
unset WINEPREFIX WINEARCH WINELOADER WINESERVER WINEDLLPATH WINEDLLOVERRIDES LD_LIBRARY_PATH
# Nova 0.4: native AArch64 Kyty. The emulator runs natively on the phone CPU and talks to the
# Android/Turnip Vulkan driver directly; an embedded FEXCore translates only the game's x86-64
# code. NOVA_ENGINE=fex (Download/droiddeck-env) selects the previous whole-emulator FEX path.
native=$runtime/native
if [[ -x "$native/kyty_emulator" && "${NOVA_ENGINE:-native}" != fex ]]; then
    stage B 'Native AArch64 Kyty present PASS'
    export SDL_VIDEODRIVER=x11 XDG_CONFIG_HOME=/root/.config XDG_DATA_HOME=/root/.local/share
    mkdir -p /root/.config/kyty /root/.local/share/kyty /root/.cache/kyty
    echo "NOVA_HOST: uname=$(uname -a) page_size=$(getconf PAGESIZE)"
    echo "NOVA_DISPLAY: DISPLAY=${DISPLAY:-missing} VK_DRIVER_FILES=${VK_DRIVER_FILES:-unset} VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-unset} preload=${LD_PRELOAD:-}"
    # Turnip on Adreno lacks fragment-shader barycentrics; continue with the documented
    # relaxations unless the user overrides it.
    export NOVA_RELAXED_VULKAN=${NOVA_RELAXED_VULKAN:-1}
    export NOVA_LIBC_HLE=0
    if [[ -r "$game/sce_module/libc.prx" ]] && sha256sum "$game/sce_module/libc.prx" | grep -q '^e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036 '; then
        NOVA_LIBC_HLE=1; echo 'NOVA_LAUNCH: open-SDK homebrew libc stub detected; Kyty host C library enabled'
    fi
    native_preload=${LD_PRELOAD:-}
    if [[ -n "${FAKE_EVDEV_MEMFD_PATHS:-}" && -r "$native/libfakeinput.so" ]]; then
        # Touch overlay / pads appear to SDL as an Xbox 360 gamepad (no mouse emulation).
        native_preload="$native/libfakeinput.so${native_preload:+:$native_preload}"
        export FAKE_EVDEV_IDENTITY=xbox360 SDL_JOYSTICK_HIDAPI=0
        echo "NOVA_INPUT: gamepad rings $FAKE_EVDEV_MEMFD_PATHS -> native fakeinput preload"
    else
        echo 'NOVA_INPUT: no DroidDeck gamepad rings'
    fi
    echo "NOVA_AUDIO_ENV: PULSE_SERVER=${PULSE_SERVER:-unset} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-unset} SDL_AUDIO_DRIVER=${SDL_AUDIO_DRIVER:-auto} libs: $(ls /usr/lib/aarch64-linux-gnu/libpulse.so.0 /usr/lib/aarch64-linux-gnu/libasound.so.2 /usr/lib/aarch64-linux-gnu/libpipewire-0.3.so.0 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
    stage F 'PS5 loader UNVERIFIED (see Kyty output below)'
    stage G 'First rendered frame UNVERIFIED'
    echo "NOVA_LAUNCH: native AArch64 Kyty game=$game relaxed_vulkan=$NOVA_RELAXED_VULKAN"
    cd "$native"
    # The session pins programs to the fastest cluster, which on Snapdragon 8 Elite-class chips is
    # only two cores. Kyty, the embedded FEX JIT and the game's 30+ threads need all of them.
    all_cores="0-$(( $(nproc --all) - 1 ))"
    taskset -cp "$all_cores" $$ >/dev/null 2>&1 && echo "NOVA_CPU: cores $all_cores (was $(cat /proc/self/status | sed -n 's/^Cpus_allowed_list:\s*//p'))" || true
    # Bundled glibc/libstdc++ first (the executable's interpreter is the bundled loader).
    LD_PRELOAD="$native_preload" LD_LIBRARY_PATH="$native:/usr/lib/aarch64-linux-gnu:/lib/aarch64-linux-gnu" \
        "$native/kyty_emulator" --game "$game" --screen-width 1280 --screen-height 720 --vblank-frequency 60 --present-mode Fifo --fullscreen --hide-cursor --no-splash --vulkan-validation false --network-connected false &
    kyty_pid=$!
    # Exit game / session stop: guest threads parked in emulated waits can keep Kyty alive after
    # SIGTERM, which blocks the next launch. Give it a moment, then force it down.
    trap 'kill -TERM "$kyty_pid" 2>/dev/null; sleep 1; kill -KILL "$kyty_pid" 2>/dev/null; exit 143' TERM INT HUP
    status=0
    wait "$kyty_pid" || status=$?
    exit "$status"
fi
# The compositor's ARM64 preload remains on the FEX host. FEX must not forward
# it into the x86-64 guest; supply guest variables through FEX_ENV explicitly.
host_preload=${LD_PRELOAD:-}
source "$base/fex-linux.sh"
nova_fex_setup "$runtime" "$base/fex-config"
export -f nova_fex_run
export nova_fex nova_loader nova_guest_libs
# FEX's own defaults (as used by Proton/Steam on ARM): TSO for scalar memory, half-barrier
# vector/memcpy ordering. Forcing full vector and memcpy TSO cost a large share of the frame time.
# Set NOVA_FEX_STRICT_TSO=1 in Download/droiddeck-env to restore the strict mode for a game.
export FEX_TSOENABLED=1 FEX_X87REDUCEDPRECISION=0 FEX_MULTIBLOCK=1
if [[ "${NOVA_FEX_STRICT_TSO:-0}" == 1 ]]; then export FEX_VECTORTSOENABLED=1 FEX_MEMCPYSETTSOENABLED=1; echo 'NOVA_FEX: strict vector/memcpy TSO'; fi
export SDL_VIDEODRIVER=x11
export XDG_CONFIG_HOME=/root/.config XDG_DATA_HOME=/root/.local/share
mkdir -p /root/.config/kyty /root/.local/share/kyty /root/.cache/kyty
echo "NOVA_HOST: uname=$(uname -a) page_size=$(getconf PAGESIZE)"
echo "NOVA_FEX: rootfs=$FEX_ROOTFS config=$FEX_APP_CONFIG_LOCATION host_thunks=$FEX_THUNKHOSTLIBS guest_thunks=$FEX_THUNKGUESTLIBS"
echo "NOVA_DISPLAY: DISPLAY=${DISPLAY:-missing} VK_DRIVER_FILES=${VK_DRIVER_FILES:-unset} VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-unset} host_preload=$host_preload"
for icd in ${VK_DRIVER_FILES:-} ${VK_ICD_FILENAMES:-}; do
    for file in ${icd//:/ }; do [[ -r $file ]] && echo "NOVA_ICD: $file $(tr -d '\n ' < "$file" | head -c 300)"; done
done
preflight() {
    local id=$1 name=$2; shift 2
    step "$id $name"
    if timeout --kill-after=5s 90s "$@"; then stage "$id" "$name PASS";
    else local status=$?; stage "$id" "$name FAIL"; echo "NOVA_ERROR: $id $name failed (status $status; 124 means timeout)"; exit "$status"; fi
}
preflight B 'x86-64 Linux executable via FEX' bash -c 'nova_fex_run "$@"' nova "$guest/nova-probe"
preflight C1 'Kyty dynamic dependencies' bash -c 'nova_fex_run "$@"' nova --list "$core"
preflight C2 'Kyty CLI' bash -c 'nova_fex_run "$@"' nova "$core" --help

step 'D Vulkan through FEX thunks'
for thunk in "$FEX_THUNKHOSTLIBS/libvulkan-host.so" "$FEX_THUNKGUESTLIBS/libvulkan-guest.so"; do
    [[ -r "$thunk" ]] || { stage D 'Vulkan FAIL'; echo "NOVA_ERROR: Vulkan thunk missing $thunk" >&2; exit 73; }
done
vulkan_status=0
# FEX debug output shows whether the thunk reached the host loader ("LoadLib: libvulkan").
vulkan_log=$(FEX_OUTPUTLOG=stderr FEX_SILENTLOG=0 VK_LOADER_DEBUG=error,warn timeout --kill-after=5s 90s bash -c 'nova_fex_run "$@"' nova "$guest/nova-probe" --vulkan 2>&1) || vulkan_status=$?
printf '%s\n' "$vulkan_log" | grep -v 'Linking address\|Adding host trampoline\|Adding guest trampoline\|Loaded [0-9]* syms' | head -120 || true
if printf '%s\n' "$vulkan_log" | grep -q 'LoadLib: libvulkan'; then echo 'NOVA_VULKAN: FEX Vulkan thunk ACTIVE (guest calls reach the ARM64 host loader)';
else echo 'NOVA_VULKAN: FEX Vulkan thunk NOT active (guest used the x86-64 loader)'; fi
relaxed=0
case $vulkan_status in
    0) stage D 'Vulkan instance, device and Kyty feature requirements PASS' ;;
    75)
        # Instance and device work, but the driver lacks something Kyty checks for.
        # imageViewMinLod/depthBounds/barycentrics can be relaxed (rendering is then
        # incomplete); anything else is a hard stop.
        missing=$(printf '%s\n' "$vulkan_log" | sed -n 's/^NOVA_KYTY_REQ: device [0-9]* \(FEATURE\|EXTENSION\) MISSING //p' | sort -u)
        hard=$(printf '%s\n' "$missing" | grep -Ev '^(imageViewMinLod|depthBounds|fragmentShaderBarycentric|VK_EXT_image_view_min_lod|VK_KHR_fragment_shader_barycentric)$' || true)
        if [[ -z $hard ]]; then
            relaxed=1
            stage D "Vulkan DEGRADED (driver lacks: $(echo $missing))"
            echo 'NOVA_WARNING: continuing with NOVA_RELAXED_VULKAN=1; shading that needs these features will be wrong or fail'
        else
            stage D "Vulkan FAIL (driver lacks: $(echo $missing))"
            echo 'NOVA_ERROR: The active Vulkan driver cannot run Kyty. A Turnip (Mesa) driver for this Adreno GPU is required.' >&2
            exit 75
        fi ;;
    *)
        stage D 'Vulkan FAIL'
        echo "NOVA_ERROR: Guest Vulkan preflight failed (status $vulkan_status). 73 = vkCreateInstance failed (thunk or host ICD), 74 = no physical device." >&2
        exit 73 ;;
esac

step 'E Guest memory'
memory_status=0
bash -c 'nova_fex_run "$@"' nova "$guest/nova-probe" --memory || memory_status=$?
if [[ $memory_status -eq 0 ]]; then stage E 'Guest memory base mapping PASS (Kyty clamps its user window to the host VA ceiling)';
else stage E 'Guest memory FAIL'; exit 76; fi

stage F 'PS5 loader UNVERIFIED (see Kyty output below)'
stage G 'First rendered frame UNVERIFIED'
cd "$base/linux-kyty"
echo "NOVA_LAUNCH: Linux Kyty game=$game relaxed_vulkan=$relaxed"
step 'F Linux Kyty attempting selected game'
export NOVA_RELAXED_VULKAN=$relaxed
# Controllers: DroidDeck's touch overlay and hardware pads are fake evdev nodes. Preload the x86-64
# build of its reader into Kyty so SDL sees them as gamepads (Xbox 360 identity -> SDL mapping).
if [[ -n "${FAKE_EVDEV_MEMFD_PATHS:-}" && -r "$guest/usr/lib/nova/libfakeinput.so" ]]; then
    export FEX_ENV="LD_PRELOAD=$guest/usr/lib/nova/libfakeinput.so" FAKE_EVDEV_IDENTITY=xbox360
    echo "NOVA_INPUT: gamepad rings $FAKE_EVDEV_MEMFD_PATHS -> Kyty (x86-64 fakeinput preload)"
else
    echo "NOVA_INPUT: no DroidDeck gamepad rings in this session (FAKE_EVDEV_MEMFD_PATHS unset)"
fi
# Homebrew built with the open PS5 SDK ships a generated stub libc.prx (PS5_Vulkan runtime,
# SHA-256 below) and imports the firmware C library directly; Kyty then needs its host libc.
# Retail games ship Sony's libc.prx and must keep using it.
export NOVA_LIBC_HLE=0
if [[ -r "$game/sce_module/libc.prx" ]] && sha256sum "$game/sce_module/libc.prx" | grep -q '^e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036 '; then
    NOVA_LIBC_HLE=1
    echo 'NOVA_LAUNCH: open-SDK homebrew libc stub detected; Kyty host C library enabled'
fi
bash -c 'nova_fex_run "$@"' nova "$core" --game "$game" --screen-width 1280 --screen-height 720 --vblank-frequency 60 --present-mode Fifo --fullscreen --hide-cursor --no-splash --vulkan-validation false --network-connected false
