# Nova PS5: run native Kyty outside proot. Sourced by launch.sh (bash, inside proot).
#
# Under proot every signal stops the traced program until proot resumes it, and Kyty takes a
# page-fault signal for each CPU write to memory the GPU caches watch: in game most of its time went
# to the kernel and threads could stay stopped (frozen game, no error). The app runs a script this
# file writes, with Android's shell, outside proot; Kyty is loaded by the runtime's own glibc
# loader with the same libraries, so it is the same program, only not traced.
#
# nova_host_launch <native dir> <preload list> <kyty args...>
#   Returns 90 (nothing started) when the host launch is unavailable; the caller then runs Kyty
#   under proot as before. Otherwise it waits for Kyty and returns its exit status.

nova_host_q() { local v=${1//\'/\'\\\'\'}; printf "'%s'" "$v"; }

# Host (Android-side) path of a path inside the rootfs. Paths bound at their own location
# (app files, storage, /proc, /dev ...) are the same on both sides.
nova_host_path() {
    case $1 in
        /data/*|/storage/*|/sdcard/*|/proc/*|/dev/*|/sys/*|/system/*|/apex/*|/vendor/*|/odm/*|/product/*) printf '%s' "$1" ;;
        /*) printf '%s%s' "$NOVA_HOST_ROOT" "$1" ;;
        *) printf '%s' "$1" ;;
    esac
}

# A Vulkan manifest whose library_path is an absolute rootfs path, rewritten for the host.
nova_host_manifest() {
    local src=$1 out=$2
    sed -E 's#("library_path"[[:space:]]*:[[:space:]]*")/#\1'"$NOVA_HOST_ROOT"'/#' "$src" > "$out"
}

nova_host_launch() {
    local native=$1 preload=$2; shift 2
    [[ "${NOVA_HOST_LAUNCH:-1}" != 0 ]] || { echo 'NOVA_HOST: disabled (NOVA_HOST_LAUNCH=0); running under proot'; return 90; }
    local envfile=${NOVA_HOST_ENV_FILE:-/opt/novaps5/host-env}
    [[ -r $envfile ]] || { echo 'NOVA_HOST: no host environment; running under proot'; return 90; }
    local NOVA_HOST_ROOT NOVA_HOST_DIR
    NOVA_HOST_ROOT=$(sed -n 's/^NOVA_HOST_ROOT=//p' "$envfile")
    NOVA_HOST_DIR=$(sed -n 's/^NOVA_HOST_DIR=//p' "$envfile")
    local dir=$NOVA_HOST_DIR
    [[ -n $NOVA_HOST_ROOT && -n $dir ]] && mkdir -p "$dir" && [[ -w $dir ]] || { echo "NOVA_HOST: host directory unavailable ($dir); running under proot"; return 90; }
    local ld
    ld=${NOVA_HOST_LD:-$(readlink -f /lib/ld-linux-aarch64.so.1 2>/dev/null || true)}
    [[ -n $ld && -x $ld ]] || { echo 'NOVA_HOST: no AArch64 glibc loader; running under proot'; return 90; }

    # Library directories: wherever the loader inside proot resolves Kyty and the libraries SDL,
    # Vulkan and PulseAudio load at run time (some, like libpulsecommon, sit in subdirectories).
    local -A seen=()
    local libdirs="" lib d candidates=("$native/kyty_emulator" "$native/libfakeinput.so")
    for lib in X11 Xext Xcursor Xi Xfixes Xrandr Xss Xrender xkbcommon xcb vulkan pulse pulse-simple asound dbus-1 udev \
               wayland-client wayland-cursor wayland-egl decor-0 usb-1.0 samplerate; do
        for d in /usr/lib/lib$lib.so.[0-9]*; do [[ -e $d ]] && candidates+=("$d") && break; done
    done
    rm -rf "$dir/layers" "$dir/icd"; mkdir -p "$dir/layers" "$dir/icd"
    local manifest layerlib
    for manifest in /usr/share/vulkan/implicit_layer.d/*.json; do
        [[ -r $manifest ]] || continue
        nova_host_manifest "$manifest" "$dir/layers/${manifest##*/}"
        layerlib=$(sed -n 's/.*"library_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -n 1)
        [[ $layerlib == /* ]] || layerlib=/usr/lib/$layerlib
        [[ -e $layerlib ]] && candidates+=("$layerlib")
    done
    local icds="" entry
    local -a icd_list=()
    IFS=: read -r -a icd_list <<< "${VK_DRIVER_FILES:-${VK_ICD_FILENAMES:-}}"
    for entry in "${icd_list[@]}"; do
        [[ -n $entry ]] || continue
        if [[ $(nova_host_path "$entry") == "$entry" ]]; then icds+=${icds:+:}$entry
        else nova_host_manifest "$entry" "$dir/icd/${entry##*/}"; icds+=${icds:+:}$dir/icd/${entry##*/}; fi
    done
    for lib in "${candidates[@]}"; do
        d=${lib%/*}; [[ -n ${seen[$d]:-} ]] || { seen[$d]=1; libdirs+=${libdirs:+:}$(nova_host_path "$d"); }
        while read -r d; do
            [[ -n $d && -z ${seen[$d]:-} ]] || continue
            seen[$d]=1; libdirs+=${libdirs:+:}$(nova_host_path "$d")
        done < <(ldd "$lib" 2>/dev/null | sed -n 's#.*=> \(/[^ ]*\)/[^/ ]* (0x.*#\1#p')
    done
    for d in /usr/lib /usr/lib/pulseaudio; do
        [[ -d $d && -z ${seen[$d]:-} ]] && { seen[$d]=1; libdirs+=${libdirs:+:}$(nova_host_path "$d"); }
    done

    local host_native host_preload="" item
    local -a preload_list=()
    host_native=$(nova_host_path "$native")
    IFS=: read -r -a preload_list <<< "$preload"
    for item in "${preload_list[@]}"; do [[ -n $item ]] && host_preload+=${host_preload:+:}$(nova_host_path "$item"); done
    local log=${BL_LOG:-$dir/kyty.log}

    rm -f "$dir/pid" "$dir/exit" "$dir/request" "$dir/request.tmp"
    {
        echo '#!/system/bin/sh'
        echo "# Written by Nova's launch.sh $(date -u +%FT%TZ); run by the app outside proot."
        echo "exec >>$(nova_host_q "$log") 2>&1"
        echo "cd $(nova_host_q "$host_native") || exit 70"
        local kv name value
        while IFS= read -r -d '' kv; do
            name=${kv%%=*}; value=${kv#*=}
            [[ $name =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
            case $name in
                PWD|OLDPWD|SHLVL|_|PATH|LD_PRELOAD|LD_LIBRARY_PATH|LD_AUDIT|PROOT_*|BASH*|IFS|PS[0-9]|TERMUX_*) continue ;;
                VK_DRIVER_FILES|VK_ICD_FILENAMES) value=$icds; [[ -n $value ]] || continue ;;
                VK_IMPLICIT_LAYER_PATH|VK_ADD_IMPLICIT_LAYER_PATH|GCONV_PATH|LOCPATH|XLOCALEDIR|GLIBC_TUNABLES|NOVA_LAUNCHER_PID) continue ;;
                *) if [[ $value == /* && $value != *:* && -e $value ]]; then value=$(nova_host_path "$value"); fi ;;
            esac
            echo "export $name=$(nova_host_q "$value")"
        done < <(env -0)
        [[ -n ${TMPDIR:-} ]] || echo "export TMPDIR=$(nova_host_q "$NOVA_HOST_ROOT/tmp")"
        echo "export VK_IMPLICIT_LAYER_PATH=$(nova_host_q "$dir/layers")"
        echo "export GCONV_PATH=$(nova_host_q "$NOVA_HOST_ROOT/usr/lib/gconv")"
        echo "export LOCPATH=$(nova_host_q "$NOVA_HOST_ROOT/usr/lib/locale")"
        echo "export XLOCALEDIR=$(nova_host_q "$NOVA_HOST_ROOT/usr/share/X11/locale")"
        # Android's seccomp policy may refuse rseq; glibc then needs no fallback at all.
        echo "export GLIBC_TUNABLES=glibc.pthread.rseq=0"
        # Kyty exits when this launcher (the session) is gone.
        echo "export NOVA_LAUNCHER_PID=$$"
        [[ -z $host_preload ]] || echo "export LD_PRELOAD=$(nova_host_q "$host_preload")"
        echo "echo \$\$ > $(nova_host_q "$dir/pid.tmp") && mv -f $(nova_host_q "$dir/pid.tmp") $(nova_host_q "$dir/pid")"
        printf 'exec %s --library-path %s %s' "$(nova_host_q "$(nova_host_path "$ld")")" "$(nova_host_q "$libdirs")" \
            "$(nova_host_q "$host_native/kyty_emulator")"
        for item in "$@"; do printf ' %s' "$(nova_host_q "$item")"; done
        echo
    } > "$dir/request.tmp"
    mv -f "$dir/request.tmp" "$dir/request"
    echo "NOVA_HOST: Kyty requested outside proot (loader $(nova_host_path "$ld"))"
    echo "NOVA_HOST: libraries $libdirs"

    # The app picks the request up within a moment; without its watcher, fall back to proot.
    local waited=0
    while [[ ! -e $dir/pid && ! -e $dir/exit ]]; do
        if (( waited >= ${NOVA_HOST_TIMEOUT_TICKS:-60} )); then
            rm -f "$dir/request"
            echo 'NOVA_HOST: the app did not start Kyty (no host launcher); running under proot'
            return 90
        fi
        sleep 0.1; waited=$((waited + 1))
    done
    local pid="" started=$SECONDS
    [[ -e $dir/pid ]] && pid=$(cat "$dir/pid")
    if [[ -n $pid ]]; then
        echo "NOVA_HOST: Kyty pid $pid running outside proot"
        trap "kill -TERM $pid 2>/dev/null; sleep 1; kill -KILL $pid 2>/dev/null; exit 143" TERM INT HUP
        while kill -0 "$pid" 2>/dev/null && [[ ! -e $dir/exit ]]; do sleep 0.5; done
    fi
    waited=0
    while [[ ! -e $dir/exit ]] && (( waited < 40 )); do sleep 0.1; waited=$((waited + 1)); done
    local status=1
    [[ -e $dir/exit ]] && status=$(cat "$dir/exit")
    [[ $status =~ ^[0-9]+$ ]] || status=1
    echo "NOVA_HOST: Kyty exited with status $status after $((SECONDS - started)) s"
    # Failed straight away outside proot (no display connection, a library the host side cannot
    # load ...): run it the proven way instead of leaving the user with an error.
    if [[ $status != 0 && $status != 143 && $((SECONDS - started)) -lt ${NOVA_HOST_EARLY_SECONDS:-12} && "${NOVA_HOST_RETRY:-1}" == 1 ]]; then
        echo 'NOVA_HOST: early failure outside proot; retrying under proot'
        return 90
    fi
    return "$status"
}
