#!/usr/bin/env python3
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1]
root=Path(sys.argv[1])
production=(root/'src/graphics/presentation/videoOut.cpp').read_text()
assert 'm_vblank_thread' in production and 'NovaTiming::Deadline' in production
with tempfile.TemporaryDirectory(prefix='nova-timing-') as td:
    exe=Path(td)/'timing'
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'src/common/timing'),str(repo/'tests/timing_pacing_test.cpp'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS production timing headers; separate vblank/present workers present in patched source')
