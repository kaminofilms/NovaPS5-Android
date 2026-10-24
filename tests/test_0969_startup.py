#!/usr/bin/env python3
"""Native metadata and production vblank-loop regression checks; no APK build."""
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1])
source = (root/'src/graphics/presentation/videoOut.cpp').read_text()
start = source.index('        const bool nova_frame_late =')
end = source.index('\n\n\t\tconst auto refresh', start)
production = source[start:end]
with tempfile.TemporaryDirectory(prefix='nova-startup-check-') as td:
    temp = Path(td)
    stat_exe = temp/'stat-test'
    subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                    '-I',str(repo/'native/startup'),str(repo/'tests/startup_stat_test.cpp'),
                    '-o',str(stat_exe)],check=True)
    subprocess.run([str(stat_exe)],check=True)
    (temp/'pacing.cpp').write_text('''
#include <algorithm>
#include <cassert>
#include <cstdint>
int bursts(bool patched) {
    int64_t total_wait=0;
    int immediate=0;
    for(int i=0;i<20;++i) {
        // First presentation blocks 100 ms, subsequent frames cost 1 ms.
        const int64_t sleep_begin=0;
        const int64_t frame_begin=std::max<int64_t>(0,total_wait);
        if(i>0 && frame_begin==0) ++immediate;
        if(patched) {
''' + production + '''
            (void)nova_frame_late;
        } else total_wait-=frame_begin-sleep_begin;
        total_wait+=16667-(i==0?100000:1000);
    }
    return immediate;
}
int main() { assert(bursts(false)>=5); assert(bursts(true)==1); }
''')
    exe=temp/'pacing-test'
    subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                    str(temp/'pacing.cpp'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('PASS: native file/directory/symlink/error metadata; no catch-up vblank burst after 100 ms stall')
