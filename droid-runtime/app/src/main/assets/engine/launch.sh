#!/bin/bash
set -euo pipefail
step() { echo "== STEP $(date -u +%H:%M:%S) $*"; }
on_exit() {
    local status=$?
    trap - EXIT
    echo "NOVA_EXIT: Kyty launch ended with status $status"
    # Only this launcher's private Wine prefix; stale Wine services must not
    # leave gamescope's reaper alive forever over a black surface.
    if [ -n "${wine:-}" ] && [ -n "${WINEPREFIX:-}" ]; then
        timeout --kill-after=2s 5s "${wine%/wine}/wineserver" -k 2>/dev/null || true
    fi
    exit "$status"
}
trap on_exit EXIT
trap 'status=$?; echo "NOVA_ERROR: launcher failed at line $LINENO (status $status)" >&2; exit "$status"' ERR
game=${1:?Missing game directory}
base=/opt/novaps5
proton=$base/proton/GE-Proton11-7-aarch64/files
wine=$proton/bin/wine
[ -r "$game/eboot.bin" ] || { echo 'NOVA_ERROR: eboot.bin is not readable'; exit 66; }
[ -x "$wine" ] || { echo 'NOVA_ERROR: ARM64 Wine/FEX runtime is not installed'; exit 67; }
[ -r "$proton/lib/wine/aarch64-unix/libarm64ecfex.so" ] || { echo 'NOVA_ERROR: FEX component is missing'; exit 68; }
export WINEPREFIX=/root/.local/share/novaps5/prefix
export WINEARCH=win64
export WINELOADER=$wine
export WINESERVER=$proton/bin/wineserver
export WINEDLLPATH=$proton/lib/wine
export LD_LIBRARY_PATH=$proton/lib/aarch64-linux-gnu:$proton/lib:$proton/lib64:${LD_LIBRARY_PATH:-}
export FEX_TSOENABLED=1
export FEX_VECTORTSOENABLED=1
export FEX_MEMCPYSETTSOENABLED=1
export FEX_MULTIBLOCK=1
export FEX_X87REDUCEDPRECISION=0
export WINEDEBUG=-all,err+all
# Avoid using the Android preload from an x86 game; the runtime supplies ARM64 shims.
export FEX_HALFBARRIERTSOENABLED=1
export SDL_VIDEODRIVER=x11
export WINEDLLOVERRIDES='winemenubuilder.exe=d'
mkdir -p "$WINEPREFIX" /root/.local/share/novaps5/logs
# This is full CPU translation. Kyty remains responsible for the PS5 loader/services/RDNA GPU.
echo 'NOVA_CORE: full Kyty df5b9b9; ARM64 Wine/Proton with FEX; TSO enabled'
echo 'NOVA_TARGET: output 1280x720; vblank 60; gameplay FPS is not guaranteed'
echo "NOVA_DISPLAY: DISPLAY=${DISPLAY:-missing} VK_DRIVER_FILES=${VK_DRIVER_FILES:-default}"
step 'Starting Kyty through ARM64 Wine/FEX (first prefix setup can take a few minutes)'
if timeout --kill-after=10s 180s "$wine" "$base/kyty/kyty_emulator.exe" --help; then
    echo 'NOVA_PREFLIGHT: Kyty CLI started through Wine/FEX'
else
    status=$?
    echo "NOVA_ERROR: Kyty Wine/FEX preflight failed (status $status; 124 means timeout)"
    exit 69
fi
windows_game="Z:${game//\//\\}"
cd "$base/kyty"
echo "NOVA_LAUNCH: $game"
step 'Kyty loading the selected game (a compositor frame is not proof of game boot)'
if "$wine" "$base/kyty/kyty_emulator.exe" --game "$windows_game" --screen-width 1280 --screen-height 720 --vblank-frequency 60 --present-mode Fifo --fullscreen --hide-cursor --no-splash --vulkan-validation false --network-connected false; then
    exit 0
else
    status=$?
    echo "NOVA_ERROR: Kyty game process exited with status $status"
    exit "$status"
fi
