#!/usr/bin/env python3
"""Run production completion/readback tests with Dead Cells explicitly selected.
The historical CPU-before-GPU stores and wait bypasses are deliberately excluded.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);tests=Path(__file__).resolve().parent
for name in ['test_eop_label_reads.py','test_ever_label_publication.py','test_ever_cooperative_label_waits.py','test_gpu_completion.py']:
 s=(tests/name).read_text()
 if name in ['test_ever_label_publication.py','test_ever_cooperative_label_waits.py']:
  # The assertion profile follows the newly enabled readback policy. The actual
  # production methods are still extracted unchanged from the staged source.
  s=s.replace('NovaRender::EverProfile()', 'NovaRender::LabelReadbackProfile()')
  s=s.replace("['PPSA04703','PPSA31162','']", "['PPSA04703','PPSA31162','PPSA15552','PPSA36257','']")
 with tempfile.TemporaryDirectory() as t:
  p=Path(t)/name;p.write_text(s);subprocess.run([sys.executable,str(p),str(root)],check=True)
print('DEAD_CELLS_REGRESSION: production GPU completion, coherent fault/read routing, cooperative queue progress and per-title fallback PASS')
