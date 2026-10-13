#!/bin/bash
set -Eeuo pipefail
step() { echo "== STEP $(date -u +%H:%M:%S) $*"; }
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
unset WINEPREFIX WINEARCH WINELOADER WINESERVER WINEDLLPATH WINEDLLOVERRIDES LD_LIBRARY_PATH
# The compositor's ARM64 preload remains on the FEX host. FEX must not forward
# it into the x86-64 guest; supply guest variables through FEX_ENV explicitly.
host_preload=${LD_PRELOAD:-}
source "$base/fex-linux.sh"
nova_fex_setup "$runtime" "$base/fex-config"
export -f nova_fex_run
export nova_fex nova_loader nova_guest_libs
export FEX_TSOENABLED=1 FEX_VECTORTSOENABLED=1 FEX_MEMCPYSETTSOENABLED=1
export FEX_X87REDUCEDPRECISION=0
export SDL_VIDEODRIVER=x11
export XDG_CONFIG_HOME=/root/.config XDG_DATA_HOME=/root/.local/share
mkdir -p /root/.config/kyty /root/.local/share/kyty /root/.cache/kyty
echo "NOVA_HOST: uname=$(uname -a) page_size=$(getconf PAGESIZE)"
echo "NOVA_FEX: rootfs=$FEX_ROOTFS host_thunks=$FEX_THUNKHOSTLIBS guest_thunks=$FEX_THUNKGUESTLIBS"
echo "NOVA_DISPLAY: DISPLAY=${DISPLAY:-missing} VK_DRIVER_FILES=${VK_DRIVER_FILES:-default} host_preload=$host_preload"
preflight() {
    local stage=$1; shift
    step "$stage"
    if timeout --kill-after=5s 90s "$@"; then echo "NOVA_STAGE: $stage PASS";
    else local status=$?; echo "NOVA_ERROR: $stage failed (status $status; 124 means timeout)"; exit "$status"; fi
}
preflight 'A FEX runtime version' "$runtime/host/usr/bin/FEXGetConfig" --version
preflight 'B x86-64 Linux executable' bash -c 'nova_fex_run "$@"' nova "$guest/nova-probe"
preflight 'C Kyty dynamic dependencies' bash -c 'nova_fex_run "$@"' nova --list "$core"
preflight 'D Linux Kyty CLI' bash -c 'nova_fex_run "$@"' nova "$core" --help
step 'Guest memory mapping diagnostic'
bash -c 'nova_fex_run "$@"' nova "$guest/nova-probe" --memory
step 'Vulkan thunk diagnostics'
echo "NOVA_VULKAN: host ICD=${VK_DRIVER_FILES:-unset}; guest root=$FEX_ROOTFS"
for thunk in "$FEX_THUNKHOSTLIBS/libvulkan-host.so" "$FEX_THUNKGUESTLIBS/libvulkan-guest.so"; do
    if [[ -r "$thunk" ]]; then echo "NOVA_VULKAN: thunk present $thunk"; else echo "NOVA_ERROR: Vulkan thunk missing $thunk" >&2; exit 73; fi
done
if timeout --kill-after=5s 90s bash -c 'nova_fex_run "$@"' nova "$guest/nova-probe" --vulkan; then
    echo 'NOVA_STAGE: Vulkan instance and physical device preflight PASS'
else
    status=$?
    echo "NOVA_ERROR: Guest Vulkan preflight failed; inspect FEX Vulkan thunk overlay and ARM64 ICD (vkCreateInstance=-9 means incompatible driver)" >&2
    echo "NOVA_VULKAN: guest Vulkan failed before Kyty game loader; status=$status" >&2
    exit 73
fi
echo 'NOVA_STAGE: F guest execution and G frame presentation UNVERIFIED'
cd "$base/linux-kyty"
echo "NOVA_LAUNCH: Linux Kyty game=$game"
step 'E Linux Kyty attempting selected game'
bash -c 'nova_fex_run "$@"' nova "$core" --game "$game" --screen-width 1280 --screen-height 720 --vblank-frequency 60 --present-mode Fifo --fullscreen --hide-cursor --no-splash --vulkan-validation false --network-connected false

