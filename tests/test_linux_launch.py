#!/usr/bin/env python3
"""Exercise quoting, sequential preflight, and failure propagation with a fake FEX."""
import os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
script=(ROOT/'droid-runtime/app/src/main/assets/engine/launch-linux.sh').read_text()
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);base=root/'engine';game=root/'storage'/'Dead Cells [PPSA15552] $(touch PWNED)'
    game.mkdir(parents=True);(game/'eboot.bin').write_bytes(b'test')
    fex=base/'linux-runtime/host/usr/bin/FEX';fex.parent.mkdir(parents=True)
    fex.write_text('#!/bin/bash\nprintf "%s\\n" "$@" >> "$NOVA_TEST_ARGS"\nif [[ "${NOVA_TEST_FAIL:-}" = "$1" ]]; then exit 43; fi\n')
    fex.chmod(0o755);server=fex.with_name('FEXServer');server.write_text('#!/bin/bash\nexit 0\n');server.chmod(0o755)
    for name in ['linux-runtime/guest/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','linux-kyty/kyty_emulator']:
        p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'test');p.chmod(0o755)
    staged=root/'launch.sh';staged.write_text(script.replace('base=/opt/novaps5','base='+str(base)).replace('= /storage/*','= '+str(root)+'/storage/*').replace('/root/.config',str(root)+'/config').replace('/root/.local/share',str(root)+'/data').replace('/root/.cache',str(root)+'/cache'))
    args=root/'arguments';env=dict(os.environ,NOVA_TEST_ARGS=str(args))
    result=subprocess.run(['bash',str(staged),str(game)],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    lines=args.read_text().splitlines();at=lines.index('--game');assert lines[at+1]==str(game)
    assert not (base/'linux-kyty/PWNED').exists()
    assert all('NOVA_STAGE: '+stage+' PASS' in result.stdout for stage in ['A FEX starts','B x86-64 Linux executable','C Kyty dynamic dependencies','D Linux Kyty CLI'])
    args.write_text('');env['NOVA_TEST_FAIL']='/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
    result=subprocess.run(['bash',str(staged),str(game)],env=env,capture_output=True,text=True)
    assert result.returncode==43 and 'NOVA_ERROR: C Kyty dynamic dependencies failed (status 43' in result.stdout
    assert '--game' not in args.read_text()
print('Linux launcher quoting, preflight ordering and error propagation passed (mock FEX; no game execution claim).')
