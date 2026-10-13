#!/bin/bash
# Stand-in for the app's HostKyty watcher (tests only): takes <dir>/request, runs it with the
# given shell as run.sh (as Android's /system/bin/sh would), and writes <dir>/exit.
#   fake-host-watcher.sh <dir> <shell> [once]
dir=$1 shell=$2
while :; do
    if [[ -e $dir/request ]]; then
        mv -f "$dir/request" "$dir/run.sh"
        (cd "$dir" && env -i PATH=/usr/bin:/bin "$shell" "$dir/run.sh" >>"$dir/host.log" 2>&1)
        status=$?
        echo "$status" > "$dir/exit.tmp" && mv -f "$dir/exit.tmp" "$dir/exit"
        [[ ${3:-} == once ]] && exit 0
    fi
    sleep 0.1
done
