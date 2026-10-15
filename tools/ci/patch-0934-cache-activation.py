#!/usr/bin/env python3
"""Include the header defining KYTY_NOVA_FEX before Android cache guards."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp'
s=p.read_text()
anchor='#include <cstring>'
if s.count(anchor)!=1 or '#include "common/novaFex.h"' in s:
    raise SystemExit('NOVA_CACHE_ACTIVATION: source/include anchor changed')
p.write_text(s.replace(anchor,anchor+'\n#include "common/novaFex.h"',1))
print('NOVA_CACHE_ACTIVATION: Android title fallback and live snapshots enabled explicitly')
