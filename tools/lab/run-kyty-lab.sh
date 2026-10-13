#!/bin/bash
# Nova PS5 lab runner: boots a homebrew title with Kyty under Xvfb and records
# logs plus periodic screenshots. Used only by .github/workflows/nova-lab.yml.
#   run-kyty-lab.sh <mode: native|fex> <kyty> <game-dir> <out-dir> <seconds>
set -uo pipefail
mode=$1 kyty=$2 game=$3 out=$4 seconds=$5
mkdir -p "$out/shots"
export DISPLAY=:99 NOVA_LIBC_HLE=1
Xvfb :99 -screen 0 1280x720x24 -nolisten tcp >"$out/xvfb.txt" 2>&1 &
xvfb=$!
sleep 2
args=(--game "$game" --screen-width 1280 --screen-height 720 --vblank-frequency 60
      --present-mode Fifo --no-splash --vulkan-validation false --network-connected false
      --printf-direction File --printf-output-file "$out/kyty-full.log")
start=$(date +%s)
if [[ $mode == native ]]; then
    timeout --kill-after=10s "${seconds}s" "$kyty" "${args[@]}" >"$out/kyty.txt" 2>&1 &
else
    timeout --kill-after=10s "${seconds}s" bash -c 'nova_fex_run "$@"' nova "$kyty" "${args[@]}" >"$out/kyty.txt" 2>&1 &
fi
pid=$!
i=0
while kill -0 "$pid" 2>/dev/null; do
    sleep 15; i=$((i+1))
    import -display :99 -window root "$out/shots/t$(printf %03d $((i*15))).png" 2>/dev/null || true
done
wait "$pid"; status=$?
echo "NOVA_LAB: mode=$mode exit=$status elapsed=$(( $(date +%s) - start ))s (124 = still running at timeout)" | tee -a "$out/kyty.txt"
# Keep only screenshots that differ from a blank frame, plus the last one.
for shot in "$out"/shots/*.png; do
    [[ -e $shot ]] || continue
    mean=$(convert "$shot" -colorspace Gray -format '%[fx:mean]' info: 2>/dev/null || echo 0)
    echo "$(basename "$shot") mean=$mean" >> "$out/shots/index.txt"
done
grep -n "abort\|Fatal\|Error\|Unresolved\|stack\[" "$out/kyty-full.log" 2>/dev/null | head -200 > "$out/kyty-highlights.txt" || true
tail -400 "$out/kyty-full.log" > "$out/kyty-tail.txt" 2>/dev/null || true
gzip -f "$out/kyty-full.log" 2>/dev/null || true
kill "$xvfb" 2>/dev/null || true
exit 0
