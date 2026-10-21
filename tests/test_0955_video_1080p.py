#!/usr/bin/env python3
"""0.9.55: execute the production VideoOutGetOutputStatus resolution choice,
the WAIT_REG_MEM read-path predicate and the telemetry gate."""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(sys.argv[1]); src = root/'src'
SAN = ['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []

def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]

vo = (src/'graphics/presentation/videoOut.cpp').read_text()
choice = between(vo, '	static const bool nova_video_4k = [] {', '	status->dynamicRange')
gr = (src/'graphics/guest_gpu/graphicsRun.cpp').read_text()
assert '	if (NovaRender::GpuLabelProfile() || (!NovaSync::PreciseReadbacks() && !NovaSync::ReadbackOff())) {' in gr
tel = (src/'graphics/host_gpu/renderer/novaReadbackTelemetry.h').read_text()
assert 'return !(explicit_enable && std::string_view(explicit_enable) == "0");' in tel

code = r'''
#include "graphics/host_gpu/novaSync.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
struct Status{uint32_t resolution=0;};struct Ctx{uint32_t width,height;};
uint32_t Pick(int32_t attribute3, Ctx* ctx){Status s;Status* status=&s;
''' + choice + r'''
 return status->resolution;}
int main(int,char** argv){
 const bool want4k=std::strcmp(argv[1],"4k")==0;
 Ctx big{3840,2160},small{1920,1080};
 if(want4k){assert(Pick(0,&big)==2&&Pick(0,&small)==2&&Pick(4,&small)==1&&Pick(4,&big)==2);}
 else{assert(Pick(0,&big)==1&&Pick(4,&small)==1&&Pick(0,&small)==1);}
 // WAIT_REG_MEM coherent read only for accurate labels or relaxed readbacks.
 const bool coherent=!NovaSync::PreciseReadbacks()&&!NovaSync::ReadbackOff();
 const char* m=std::getenv("NOVA_READBACK_MODE");
 assert(coherent==(m&&std::strcmp(m,"relaxed")==0));
 puts("NOVA_0955: PASS");
}'''
with tempfile.TemporaryDirectory() as t:
    p = Path(t)/'v.cpp'; p.write_text(code); out = Path(t)/'v'
    subprocess.run(['g++','-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*SAN,'-I'+str(src),str(p),'-o',str(out)],check=True)
    base = {k:v for k,v in os.environ.items() if not k.startswith('NOVA_')}
    for env, arg in [({}, '1080'), ({'NOVA_VIDEO_OUT_4K':'0'}, '1080'), ({'NOVA_VIDEO_OUT_4K':'1'}, '4k'),
                     ({'NOVA_READBACK_MODE':'relaxed'}, '1080'), ({'NOVA_READBACK_MODE':'precise'}, '1080'),
                     ({'NOVA_READBACK_MODE':'off'}, '1080')]:
        subprocess.run([str(out), arg], env={**base, **env}, check=True, timeout=20)
print('NOVA_0955_REGRESSION: PASS')
