#!/bin/bash
# Usage: proot-probe.sh <runtime> <fex-config> <fex-linux.sh>
set -uo pipefail
source "$3"
nova_fex_setup "$1" "$2"
echo "--- config dir"; ls -la "$2"; head -c 600 "$2/ThunksDB.json"; echo
echo "--- probe --memory"; nova_fex_run "$1/guest/nova-probe" --memory; echo "status $?"
echo "--- probe --vulkan"; nova_fex_run "$1/guest/nova-probe" --vulkan; echo "status $?"
echo "--- FEX debug log"
FEX_OUTPUTLOG=stderr FEX_SILENTLOG=0 nova_fex_run "$1/guest/nova-probe" --vulkan 2>&1 | head -80
echo "--- strace of FEX file lookups (openat/openat2/statx)"
if command -v strace >/dev/null; then
  strace -f -e trace=openat,openat2,newfstatat,statx,faccessat,faccessat2,readlinkat -o /tmp/st.txt "$nova_fex" "$nova_loader" --inhibit-cache --library-path "$nova_guest_libs" "$1/guest/nova-probe" --vulkan >/dev/null 2>&1
  grep -E "ld.so.preload|libvulkan|ThunksDB|Config.json|openat2|ENOSYS" /tmp/st.txt | head -80
else echo "no strace in this root"; fi
