#!/usr/bin/env python3
"""Port KytyPS5 37df7f3 FP16 signaling-NaN classification; preserve Nova runtime."""
from pathlib import Path
import sys
path = Path(sys.argv[1]) / 'src/graphics/shader/recompiler/frontend/translate/Float.cpp'
source = path.read_text()
old = 'const auto exponent = ir.BitwiseAnd(bits, IR::U32(IR::Value(0x7c00u)));'
new = 'const auto exponent = ir.BitwiseAnd(bits, IR::U32(IR::Value(0x7e00u)));'
if source.count(old) == 1 and source.count(new) == 0:
    path.write_text(source.replace(old, new, 1))
elif source.count(new) != 1 or old in source:
    raise SystemExit('FP16 signaling-NaN anchor changed; refusing edit')
print('NOVA_FP16: signaling-NaN quiet bit classification enabled')
