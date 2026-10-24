#!/usr/bin/env python3
from pathlib import Path
import re,subprocess,tempfile
repo=Path(__file__).resolve().parents[1]
source=(repo/'native/novafex/clock_probe.cpp').read_text()
embedded=bytes(int(x,16) for x in re.search(r'code\[\]=\{([^}]+)',source)[1].split(','))
with tempfile.TemporaryDirectory() as td:
 p=Path(td)
 subprocess.run(['gcc','-c',str(repo/'native/novafex/clock_probe_x86.S'),'-o',str(p/'probe.o')],check=True)
 subprocess.run(['objcopy','-O','binary','--only-section=.text',str(p/'probe.o'),str(p/'probe.bin')],check=True)
 assert (p/'probe.bin').read_bytes()==embedded
print('PASS exact RDTSC/RDTSCP/CPUID probe bytes and preserved SysV RBX')
