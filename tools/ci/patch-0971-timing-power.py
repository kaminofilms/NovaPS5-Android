#!/usr/bin/env python3
"""Apply after 0968 + 0969; keep UI and installer separate from core overlays."""
from pathlib import Path
import json,shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);pending={}
for item in json.loads((repo/'native/timing/core-edits.json').read_text()):
    name=item['path'];p=root/name[1:] if name.startswith('@') else root/'src'/name
    s=pending.get(p,p.read_text());old=item['old'];new=item['new']
    if s.count(old)!=1:raise SystemExit('NOVA_TIMING: anchor changed: '+name+': '+old[:80])
    pending[p]=s.replace(old,new,1)
for p,s in pending.items():p.write_text(s)
shutil.copytree(repo/'native/startup',root/'src/common/startup',dirs_exist_ok=True)
shutil.copytree(repo/'native/timing',root/'src/common/timing',dirs_exist_ok=True)
shutil.copy(repo/'native/novalsfg/novaFramegen.h',root/'src/graphics/presentation/window/novaFramegen.h')
shutil.copy(repo/'native/novalsfg/novaFrameExtent.h',root/'src/graphics/presentation/window/novaFrameExtent.h')
print('NOVA_TIMING: independent vblank worker, bounded deadlines/diagnostics, safe runtime output workload')
