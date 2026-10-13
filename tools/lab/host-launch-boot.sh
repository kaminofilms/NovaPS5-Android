#!/bin/bash
# CI: boot a homebrew title through Nova's host (outside proot) launch path exactly as the app
# runs it: launch.sh's host-launch.sh writes the script, a stand-in for the app's watcher runs it
# with mksh (Android's /system/bin/sh), and the script loads Kyty with the glibc loader directly.
#   host-launch-boot.sh <repo> <native-dir> <game-dir> <out-dir> <seconds>
set -uo pipefail
repo=$1 native=$2 game=$3 out=$4 seconds=$5
mkdir -p "$out"
hostdir=$out/nova-host
printf 'NOVA_HOST_ROOT=/\nNOVA_HOST_DIR=%s\n' "$hostdir" > "$out/host-env"
export DISPLAY=:98 NOVA_LIBC_HLE=1 BL_LOG=$out/session.log NOVA_HOST_ENV_FILE=$out/host-env NOVA_HOST_RETRY=0
Xvfb :98 -screen 0 1280x720x24 -nolisten tcp >"$out/xvfb.txt" 2>&1 &
xvfb=$!
sleep 2
bash "$repo/tools/lab/fake-host-watcher.sh" "$hostdir" "$(command -v mksh)" &
watcher=$!
timeout --signal=TERM "${seconds}s" bash -c 'source "$1"; shift; nova_host_launch "$@"' x \
    "$repo/droid-runtime/app/src/main/assets/engine/host-launch.sh" "$native" "" \
    --game "$game" --screen-width 1280 --screen-height 720 --vblank-frequency 60 --present-mode Fifo \
    --no-splash --vulkan-validation false --network-connected false > "$out/launcher.txt" 2>&1
echo "NOVA_LAB: host launch exit=$? (124/143 = still running at timeout)" | tee -a "$out/launcher.txt"
sleep 2
kill "$watcher" "$xvfb" 2>/dev/null
cp "$hostdir/run.sh" "$out/run.sh" 2>/dev/null
cat "$out/launcher.txt"
tail -60 "$out/session.log"
grep -q 'NOVA_HOST: Kyty pid' "$out/launcher.txt" || { echo 'host launch did not start Kyty'; exit 1; }
grep -q '\[ccleste\] sample celeste: starts' "$out/session.log" || { echo 'ccleste did not start through the host launch'; exit 1; }
echo 'NOVA_LAB: ccleste started through the host launch path'
