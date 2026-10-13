#!/bin/bash
# Shared by the Android launcher and native/proot ARM64 CI.
nova_fex_setup() {
    local runtime=$1 config=$2
    nova_guest=$runtime/guest
    nova_loader=$nova_guest/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    nova_guest_libs=$nova_guest/usr/lib/x86_64-linux-gnu
    nova_fex=$runtime/host/usr/bin/FEX
    for file in "$nova_loader" "$nova_guest_libs/libc.so.6" "$nova_guest_libs/libm.so.6" "$nova_guest_libs/libgcc_s.so.1" "$nova_guest_libs/libstdc++.so.6"; do
        [[ -r "$file" ]] || { echo "NOVA_ERROR: Required x86-64 library missing: $file" >&2; return 68; }
    done
    mkdir -p "$config"
    # Explicit physical paths bypass the ARM64 root's loader cache/search paths.
    # Add matching thunk overlays so using those paths cannot bypass Vulkan forwarding.
    python3 - "$runtime" "$config" <<'PY'
import json,sys
from pathlib import Path
runtime,config=map(Path,sys.argv[1:])
guest=runtime/'guest'
db=json.loads((runtime/'ThunksDB.json').read_text())
for item in db['DB'].values():
    overlays=item.get('Overlay',[])
    if isinstance(overlays,str):overlays=[overlays]
    expanded=[]
    for overlay in overlays:
        if '@PREFIX_LIB@' in overlay:
            for prefix in ['usr/lib/x86_64-linux-gnu','lib/x86_64-linux-gnu']:
                expanded.append(overlay.replace('@PREFIX_LIB@',str(guest/prefix)))
    item['Overlay']=overlays+expanded
(config/'ThunksDB.json').write_text(json.dumps(db)+'\n')
(config/'Config.json').write_text(json.dumps({'Config':{'Env':'LD_LIBRARY_PATH='+str(guest/'usr/lib/x86_64-linux-gnu')}})+'\n')
PY
    export FEX_ROOTFS=$nova_guest FEX_APP_CONFIG_LOCATION=$config FEX_PORTABLE=1
    export FEX_THUNKHOSTLIBS=$runtime/host/usr/lib/aarch64-linux-gnu/fex-emu/HostThunks
    export FEX_THUNKGUESTLIBS=$runtime/host/usr/share/fex-emu/GuestThunks
    export FEX_THUNKCONFIG=$runtime/thunks.json
    export FEX_ENV='LD_PRELOAD='
    export PATH=$runtime/host/usr/bin:$PATH
    echo "NOVA_LOADER: $nova_loader --inhibit-cache --library-path $nova_guest_libs"
    echo "NOVA_LIBC: $(ls -l "$nova_guest_libs/libc.so.6")"
    [[ -r "$nova_guest/etc/ld.so.preload" ]] || { echo 'NOVA_ERROR: Guest preload isolation file missing' >&2; return 68; }
}
nova_fex_run() {
    "$nova_fex" "$nova_loader" --inhibit-cache --library-path "$nova_guest_libs" "$@"
}
