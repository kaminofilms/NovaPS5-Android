#!/usr/bin/env python3
"""Preprocess production snapshot blocks with the production architecture header."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
root=Path(sys.argv[1])
s=(root/'src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp').read_text()
assert '#include "common/novaFex.h"' in s
blocks=re.findall(r'#if defined\(KYTY_NOVA_FEX\)\n(?:(?!#endif).)*Save\(true\);(?:(?!#endif).)*#endif',s,re.S)
assert len(blocks)==2, 'graphics and compute live snapshot blocks required'
with tempfile.TemporaryDirectory() as d:
    stage=Path(d)
    (stage/'novafex.h').write_text('// FEX declarations are irrelevant to preprocessing.\n')
    for header in [False,True]:
        source=stage/'guard.cpp'
        source.write_text(('#include "common/novaFex.h"\n' if header else '')+'\n'.join(blocks))
        result=subprocess.run(['g++','-E','-P','-D__aarch64__','-I'+str(root/'src'),'-I'+str(stage),str(source)],capture_output=True,text=True,check=True)
        assert result.stdout.count('Save(true);')==(2 if header else 0)
print('NOVA_CACHE_ACTIVATION_TEST: both Android snapshots survive preprocessing only with the architecture header PASS')
