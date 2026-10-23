#!/usr/bin/env python3
"""Compile the actual patched fiber functions and execute the production guest stubs."""
from pathlib import Path
import os,re,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1]
root=Path(sys.argv[1]);source=(root/'src/libs/libKernel.cpp').read_text()
fiber=source.split('namespace Fiber {',1)[1].split('} // namespace Fiber',1)[0]
with tempfile.TemporaryDirectory(prefix='nova-fiber-test-') as t:
 p=Path(t)
 (p/'fiber-under-test.inc').write_text(fiber)
 subprocess.run(['gcc','-c',str(repo/'native/guestfiber/switch.S'),'-o',str(p/'switch.o')],check=True)
 subprocess.run(['objcopy','-O','binary','--only-section=.text',str(p/'switch.o'),str(p/'switch.bin')],check=True)
 h=(repo/'native/guestfiber/switchBytes.h').read_text()
 expected=bytes(int(x,16) for x in re.findall(r'0x([0-9a-f]{2})',h))
 assert (p/'switch.bin').read_bytes()==expected,'Guest assembly bytes drifted'
 nm=subprocess.check_output(['nm','-n',str(p/'switch.o')],text=True)
 assert re.search(r'000000000000000e T nova_fiber_host',nm)
 assert re.search(r'0000000000000042 T nova_fiber_complete',nm)
 for opt in ['-O0','-O2','-O3']:
  exe=p/('fibers'+opt[1:]);flags=['-fsanitize=undefined','-fno-sanitize=function'] if os.getenv('CXX','g++').endswith('clang++') else ['-fsanitize=undefined']
  subprocess.run([os.getenv('CXX','g++'),'-std=c++20',opt,'-pthread',*flags,'-I',str(p),'-I',str(root/'src'),str(repo/'tests/guest_fiber_test.cpp'),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,timeout=30)
print('PASS: exact production fiber code and assembly at O0/O2/O3 (UBSan)')
