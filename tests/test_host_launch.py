#!/usr/bin/env python3
"""Host (outside proot) launch of native Kyty: the script launch.sh hands to the app.

Runs host-launch.sh with a fake Kyty and a fake glibc loader, a stand-in for the app's watcher
(tools/lab/fake-host-watcher.sh) and Android's shell replaced by mksh (or dash). Checks argument
quoting, path translation into the rootfs, Vulkan manifest rewriting, exit status, the TERM path
and the proot fallback. No game is executed here."""
import os, shutil, signal, subprocess, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_LAUNCH = ROOT / 'droid-runtime/app/src/main/assets/engine/host-launch.sh'
WATCHER = ROOT / 'tools/lab/fake-host-watcher.sh'
SHELL = os.environ.get('NOVA_TEST_SHELL') or shutil.which('mksh') or shutil.which('dash') or '/bin/sh'

FAKE_LD = '''#!/bin/bash
[[ $1 == --library-path ]] || { echo "fake ld: bad args $*"; exit 99; }
echo "$2" > "$NOVA_TEST_OUT/libpath"
shift 2
exec "$@"
'''
FAKE_KYTY = '''#!/bin/bash
printf '%s\\n' "$@" > "$NOVA_TEST_OUT/args"
env > "$NOVA_TEST_OUT/env"
pwd > "$NOVA_TEST_OUT/cwd"
echo "KYTY RUNNING"
[[ -n ${NOVA_TEST_SLEEP:-} ]] && exec sleep "$NOVA_TEST_SLEEP"
exit 7
'''

with tempfile.TemporaryDirectory(dir='/tmp') as directory:
    t = Path(directory)
    host_root = t / 'hostroot'; host_root.mkdir()
    (host_root / 'tmp').symlink_to('/tmp')   # host root + "/tmp/..." reaches the same files
    native = t / 'native'; native.mkdir()
    (native / 'kyty_emulator').write_text(FAKE_KYTY); (native / 'kyty_emulator').chmod(0o755)
    (native / 'libfakeinput.so').write_bytes(b'')
    ld = t / 'ld.so'; ld.write_text(FAKE_LD); ld.chmod(0o755)
    home = t / 'home'; home.mkdir()
    out = t / 'out'; out.mkdir()
    hostdir = t / 'nova-host'
    envfile = t / 'host-env'
    envfile.write_text(f'NOVA_HOST_ROOT={host_root}\nNOVA_HOST_DIR={hostdir}\n')
    icd = t / 'freedreno_icd.json'
    icd.write_text('{"ICD": {"library_path": "/usr/lib/libvulkan_freedreno.so", "api_version": "1.4"}}')
    log = t / 'session.log'
    game = t / 'storage' / "Dead Cells [PPSA15552] it's $(touch PWNED) `id`"
    game.mkdir(parents=True)

    def launcher(extra=None, background=False):
        env = dict(os.environ, NOVA_HOST_ENV_FILE=str(envfile), NOVA_HOST_LD=str(ld), NOVA_TEST_OUT=str(out),
                   HOME=str(home), BL_LOG=str(log), VK_DRIVER_FILES=str(icd), DISPLAY=':0',
                   FAKE_EVDEV_IDENTITY='xbox360', NOVA_TEST_TRICKY="a'b\"c $HOME `x`")
        env.pop('VK_ICD_FILENAMES', None)
        env.update(extra or {})
        cmd = ['bash', '-c', 'source "$1"; shift; nova_host_launch "$@"; echo "RETURN=$?"', 'x', str(HOST_LAUNCH),
               str(native), f'{native}/libfakeinput.so', '--game', str(game), '--screen-width', '1280']
        if background:
            return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    # 1. Normal run: the watcher runs the script, Kyty's status comes back.
    watcher = subprocess.Popen(['bash', str(WATCHER), str(hostdir), SHELL])
    try:
        result = launcher({'NOVA_HOST_RETRY': '0'})
        text = result.stdout + result.stderr
        assert 'RETURN=7' in text, text
        assert 'NOVA_HOST: Kyty pid' in text and 'NOVA_HOST: Kyty exited with status 7' in text, text
        args = (out / 'args').read_text().splitlines()
        assert args == ['--game', str(game), '--screen-width', '1280'], args
        assert not Path('PWNED').exists() and not (native / 'PWNED').exists()
        env = dict(line.split('=', 1) for line in (out / 'env').read_text().splitlines() if '=' in line)
        assert env['HOME'] == f'{host_root}{home}', env['HOME']
        assert env['DISPLAY'] == ':0' and env['FAKE_EVDEV_IDENTITY'] == 'xbox360'
        assert env['NOVA_TEST_TRICKY'] == "a'b\"c $HOME `x`", env['NOVA_TEST_TRICKY']
        assert env['LD_PRELOAD'] == f'{host_root}{native}/libfakeinput.so', env['LD_PRELOAD']
        assert env['GLIBC_TUNABLES'] == 'glibc.pthread.rseq=0'
        assert env['VK_IMPLICIT_LAYER_PATH'] == f'{hostdir}/layers'
        assert env['NOVA_LAUNCHER_PID'].isdigit()
        assert env['VK_DRIVER_FILES'] == f'{hostdir}/icd/{icd.name}', env['VK_DRIVER_FILES']
        rewritten = (hostdir / 'icd' / icd.name).read_text()
        assert f'"library_path": "{host_root}/usr/lib/libvulkan_freedreno.so"' in rewritten, rewritten
        assert 'PATH' not in env or not env['PATH'].startswith('/opt')
        assert (out / 'cwd').read_text().strip() in (f'{host_root}{native}', str(native))
        libpath = (out / 'libpath').read_text().strip().split(':')
        assert f'{host_root}{native}' in libpath, libpath
        assert 'KYTY RUNNING' in log.read_text()
        assert (hostdir / 'run.sh').read_text().startswith('#!/system/bin/sh')

        # 1b. The same early failure with retry on (default): handed back to proot.
        result = launcher()
        assert 'RETURN=90' in result.stdout and 'retrying under proot' in result.stdout, result.stdout

        # 2. Session stop: TERM to the launcher ends the host Kyty.
        for f in ('args',):
            (out / f).unlink()
        proc = launcher({'NOVA_TEST_SLEEP': '60'}, background=True)
        deadline = time.time() + 20
        while not (hostdir / 'pid').exists() and time.time() < deadline:
            time.sleep(0.1)
        pid = int((hostdir / 'pid').read_text())
        time.sleep(0.5)
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        time.sleep(1.5)
        alive = subprocess.run(['kill', '-0', str(pid)], capture_output=True).returncode == 0
        assert not alive, 'host Kyty survived the session stop'
    finally:
        watcher.kill()

    # 3. No watcher (the app did not pick the request up): fall back to proot.
    result = launcher({'NOVA_HOST_TIMEOUT_TICKS': '5'})
    text = result.stdout + result.stderr
    assert 'RETURN=90' in text and 'running under proot' in text, text
    assert not (hostdir / 'request').exists()

    # 4. Disabled by the user, or no host environment: fall back without writing a request.
    assert 'RETURN=90' in launcher({'NOVA_HOST_LAUNCH': '0'}).stdout
    assert 'RETURN=90' in launcher({'NOVA_HOST_ENV_FILE': str(t / 'missing')}).stdout

print(f'Host launch: quoting, rootfs path translation, Vulkan manifest rewrite, exit status, TERM and proot fallback passed ({SHELL}; fake Kyty, no game execution claim).')
