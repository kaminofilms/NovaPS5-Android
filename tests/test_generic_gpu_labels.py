#!/usr/bin/env python3
"""0.9.52: re-run the production completion/readback/wait tests with the
GPU-label path enabled for every title, and with the NOVA_GPU_LABELS=0 opt-out.

Each wrapped test extracts the real staged Kyty bodies; only its title list and
(for the readback tests) the profile that selects the expected branch change.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(sys.argv[1]); tests = Path(__file__).resolve().parent
header = (root/'src/graphics/host_gpu/renderer/novaRenderCosts.h').read_text()
assert 'inline bool GenericGpuLabels()' in header
assert '|| GenericGpuLabels(); }' in header and 'return GenericGpuLabels() ||' in header
assert 'NOVA_GPU_LABELS: GPU-recorded completion labels' in (root/'src/graphics/host_gpu/renderer/cache/bufferCache.cpp').read_text()

# Profile semantics: default on for any title, opt-out keeps the original per-title set.
probe = r'''
#include "novaRenderCosts.h"
#include <cassert>
#include <cstdio>
#include <string_view>
int main(int argc,char** argv){
 const std::string_view title=argc>1?argv[1]:"";
 const bool optout=argc>2&&std::string_view(argv[2])=="0";
 const bool listed=title=="PPSA04703"||title=="PPSA31162"||title=="PPSA15552";
 const bool readback=title=="PPSA04703"||title=="PPSA15552";
 assert(NovaRender::GpuLabelProfile()==(!optout||listed));
 assert(NovaRender::LabelReadbackProfile()==(!optout||readback));
 assert(NovaRender::EverProfile()==(title=="PPSA04703"));
 assert(NovaRender::DeadCellsProfile()==(title=="PPSA15552"));
 puts("NOVA_GPU_LABELS_PROFILE: PASS");
}
'''
titles = ['PPSA27841', 'PPSA04703', 'PPSA31162', 'PPSA15552', 'PPSA36257', '']
with tempfile.TemporaryDirectory() as t:
    p = Path(t); (p/'probe.cpp').write_text(probe)
    subprocess.run(['c++','-std=c++20','-O1','-Wall','-Wextra','-Werror','-I'+str(root/'src/graphics/host_gpu/renderer'),
                    str(p/'probe.cpp'),'-o',str(p/'probe')],check=True)
    for title in titles:
        for value in (None, '1', '0'):
            env = dict(os.environ, NOVA_CACHE_TITLE_ID=title); env.pop('NOVA_GPU_LABELS', None)
            if value is not None: env['NOVA_GPU_LABELS'] = value
            subprocess.run([str(p/'probe'), title, value or ''], env=env, check=True)

wrapped = ['test_eop_label_reads.py','test_ever_label_publication.py','test_ever_cooperative_label_waits.py',
           'test_gpu_completion.py','test_ever_pm4_fetch.py']
if os.getenv('NOVA_TEST_WITH_VULKAN') == '1':
    wrapped.append('test_ever_gpu_labels.py')
lists = ["['PPSA04703','PPSA31162','']", "('PPSA04703','PPSA31162','PPSA15552','PPSA36257','')",
         "('PPSA04703','PPSA31162','PPSA15552','')"]
for name in wrapped:
    s = (tests/name).read_text()
    if name in ['test_ever_label_publication.py','test_ever_cooperative_label_waits.py']:
        s = s.replace('NovaRender::EverProfile()', 'NovaRender::LabelReadbackProfile()')
    hit = False
    for old in lists:
        if old in s:
            s = s.replace(old, old[0] + "'PPSA27841','PPSA36257'," + old[1:]); hit = True
    assert hit, f'NOVA_GPU_LABELS: title list anchor missing in {name}'
    for value in (None, '0'):
        env = dict(os.environ); env.pop('NOVA_GPU_LABELS', None)
        if value is not None: env['NOVA_GPU_LABELS'] = value
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/name; p.write_text(s)
            subprocess.run([sys.executable, str(p), str(root)], env=env, check=True)
print('NOVA_GPU_LABELS_REGRESSION: all-title GPU completion labels, coherent reads, cooperative waits, PM4 fetch and opt-out fallback PASS')
