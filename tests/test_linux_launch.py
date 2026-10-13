#!/usr/bin/env python3
"""Exercise quoting, staged preflight, Vulkan outcomes and failure propagation with a fake FEX."""
import json, os, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
script = (ROOT / 'droid-runtime/app/src/main/assets/engine/launch-linux.sh').read_text()

FAKE_FEX = r'''#!/bin/bash
printf "%s\n" "$@" >> "$NOVA_TEST_ARGS"
if [[ -n "${NOVA_TEST_FAIL:-}" && "$*" = *"$NOVA_TEST_FAIL"* ]]; then exit 43; fi
if [[ "${@: -1}" = "--vulkan" ]]; then
    printf "%s\n" "${NOVA_TEST_VULKAN_OUT:-NOVA_VULKAN: instance and device enumeration PASS}"
    exit "${NOVA_TEST_VULKAN_STATUS:-0}"
fi
if [[ "$*" = *"--game"* ]]; then echo "RELAXED=${NOVA_RELAXED_VULKAN:-unset}"; fi
'''

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); base = root / 'engine'; game = root / 'storage' / 'Dead Cells [PPSA15552] $(touch PWNED)'
    game.mkdir(parents=True); (game / 'eboot.bin').write_bytes(b'test')
    fex = base / 'linux-runtime/host/usr/bin/FEX'; fex.parent.mkdir(parents=True)
    fex.write_text(FAKE_FEX); fex.chmod(0o755)
    config = fex.with_name('FEXGetConfig'); config.write_bytes(fex.read_bytes()); config.chmod(0o755)
    server = fex.with_name('FEXServer'); server.write_text('#!/bin/bash\nexit 0\n'); server.chmod(0o755)
    for name in ['linux-runtime/guest/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2', 'linux-kyty/kyty_emulator',
                 'linux-runtime/guest/usr/lib/x86_64-linux-gnu/libc.so.6', 'linux-runtime/guest/usr/lib/x86_64-linux-gnu/libm.so.6',
                 'linux-runtime/guest/usr/lib/x86_64-linux-gnu/libgcc_s.so.1', 'linux-runtime/guest/usr/lib/x86_64-linux-gnu/libstdc++.so.6',
                 'linux-runtime/guest/etc/ld.so.preload']:
        p = base / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'test'); p.chmod(0o755)
    for name in ['linux-runtime/host/usr/lib/aarch64-linux-gnu/fex-emu/HostThunks/libvulkan-host.so',
                 'linux-runtime/host/usr/share/fex-emu/GuestThunks/libvulkan-guest.so']:
        p = base / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'mock thunk')
    runtime = base / 'linux-runtime'
    (runtime / 'ThunksDB.json').write_text(json.dumps({'DB': {'Vulkan': {'Library': 'libvulkan-guest.so', 'Overlay': ['@PREFIX_LIB@/libvulkan.so.1']}}}))
    (base / 'fex-linux.sh').write_bytes((ROOT / 'droid-runtime/app/src/main/assets/engine/fex-linux.sh').read_bytes())
    staged = root / 'launch.sh'
    staged.write_text(script.replace('base=/opt/novaps5', 'base=' + str(base)).replace('= /storage/*', '= ' + str(root) + '/storage/*')
                      .replace('/root/.config', str(root) + '/config').replace('/root/.local/share', str(root) + '/data').replace('/root/.cache', str(root) + '/cache'))
    args = root / 'arguments'

    def launch(**extra):
        args.write_text('')
        env = dict(os.environ, NOVA_TEST_ARGS=str(args), **extra)
        return subprocess.run(['bash', str(staged), str(game)], env=env, capture_output=True, text=True)

    # 1. Everything passes: game argument is passed intact, injection is inert.
    result = launch()
    assert result.returncode == 0, result.stdout + result.stderr
    lines = args.read_text().splitlines(); at = lines.index('--game'); assert lines[at + 1] == str(game)
    assert not (base / 'linux-kyty/PWNED').exists()
    for text in ['A Android runtime files PASS', 'B x86-64 Linux executable via FEX PASS', 'C1 Kyty dynamic dependencies PASS',
                 'C2 Kyty CLI PASS', 'D Vulkan instance, device and Kyty feature requirements PASS', 'E Guest memory base mapping PASS',
                 'F PS5 loader UNVERIFIED', 'G First rendered frame UNVERIFIED']:
        assert 'NOVA_STAGE: ' + text in result.stdout, text
    assert 'RELAXED=0' in result.stdout, result.stdout
    # FEX must receive a config directory with a trailing slash (it appends file names).
    assert '/fex-config/ ' in result.stdout, result.stdout

    # 2. A preflight failure stops before the game.
    result = launch(NOVA_TEST_FAIL='--list')
    assert result.returncode == 43 and 'NOVA_ERROR: C1 Kyty dynamic dependencies failed (status 43' in result.stdout
    assert '--game' not in args.read_text()

    # 3. vkCreateInstance failure is a hard stop with status 73.
    result = launch(NOVA_TEST_VULKAN_STATUS='73', NOVA_TEST_VULKAN_OUT='NOVA_ERROR: vkCreateInstance=-9')
    assert result.returncode == 73 and 'NOVA_STAGE: D Vulkan FAIL' in result.stdout, result.stdout + result.stderr
    assert '--game' not in args.read_text()

    # 4. Only relaxable features missing: degraded but continues with relaxed Kyty.
    result = launch(NOVA_TEST_VULKAN_STATUS='75', NOVA_TEST_VULKAN_OUT='NOVA_KYTY_REQ: device 0 FEATURE MISSING fragmentShaderBarycentric\nNOVA_KYTY_REQ: device 0 EXTENSION MISSING VK_KHR_fragment_shader_barycentric')
    assert result.returncode == 0 and 'NOVA_STAGE: D Vulkan DEGRADED' in result.stdout and 'RELAXED=1' in result.stdout, result.stdout + result.stderr

    # 5. A required, non-relaxable feature missing: hard stop with 75.
    result = launch(NOVA_TEST_VULKAN_STATUS='75', NOVA_TEST_VULKAN_OUT='NOVA_KYTY_REQ: device 0 FEATURE MISSING shaderBufferInt64Atomics')
    assert result.returncode == 75 and 'NOVA_STAGE: D Vulkan FAIL (driver lacks: shaderBufferInt64Atomics)' in result.stdout, result.stdout
    assert '--game' not in args.read_text()
print('Linux launcher: quoting, staged preflight, Vulkan PASS/DEGRADED/FAIL routing and error propagation passed (mock FEX; no game execution claim).')
