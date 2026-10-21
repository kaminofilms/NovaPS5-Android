#!/usr/bin/env python3
"""0.9.54: execute the production bodies of the new paths.

1. Idle submit ordering in GuestGpu::ThreadRun (structure: flush outside the
   queue lock, once per idle period, reset on progress).
2. NovaPeriodicSubmit: flushes every N draws; 0 disables; bounds.
3. Readback off: CPU write drops GPU ownership without a download.
4. Audio latency parsing (default 80 ms, bounds) and the low-latency hint.
5. Internal resolution scale for any 16:9 pass.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(sys.argv[1]); src = root/'src'
SAN = ['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []

def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]

def build(tmp, name, code):
    p = Path(tmp)/(name+'.cpp'); p.write_text(code); out = Path(tmp)/name
    subprocess.run(['g++','-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*SAN,
                    '-I'+str(src),str(p),'-o',str(out)],check=True)
    return out

def run(binary, *args, **env):
    e = {k:v for k,v in os.environ.items() if not k.startswith('NOVA_')}
    e.update(env)
    subprocess.run([str(binary), *args], env=e, check=True, timeout=30)

gr = (src/'graphics/guest_gpu/graphicsRun.cpp').read_text()
# ---- 1. idle submit structure ----
loop = between(gr, 'void GuestGpu::ThreadRun(void* data) {', '\nbool GuestGpu::Process(')
top = loop.index('if (nova_flush_idle) {'); lock = loop.index('Common::LockGuard lock(gpu->m_queue_mutex);')
assert top < lock, 'idle flush must run before the queue lock is taken'
assert 'gpu->m_gfx_cp->BufferInit();\n\t\t\tgpu->m_gfx_cp->BufferFlush();' in loop[top:lock]
idle = between(loop, 'if (selected_queue < 0) {', 'auto& queue = gpu->m_queues[')
assert idle.index('if (!nova_idle_flushed) {') < idle.index('WaitFor(&gpu->m_queue_mutex, 100)')
assert 'nova_flush_idle   = true;' in idle and 'continue;' in idle
assert 'command();\n\t\t\tnova_idle_flushed = false;' in loop
assert 'const bool complete = gpu->Process(submission);\n\t\tif (complete) nova_idle_flushed = false;' in loop

# ---- 2. periodic submit ----
periodic = between(gr, 'template <typename Scheduler>\nstatic void NovaPeriodicSubmit(', '\nvoid CommandProcessor::DrawIndex(')
for anchor in ['DrawIndex(m_submit_id, CurrentBuffer(), args);\n\tNovaPeriodicSubmit(GetScheduler());',
               'DrawAuto(m_submit_id, CurrentBuffer(), args);\n\tNovaPeriodicSubmit(GetScheduler());',
               'IsAsyncComputeQueue());\n\tNovaPeriodicSubmit(GetScheduler());']:
    assert anchor in gr, anchor

with tempfile.TemporaryDirectory() as tmp:
    per = build(tmp, 'periodic', r'''
#include "graphics/host_gpu/novaSync.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
struct Scheduler{unsigned flushes=0;void Flush(){++flushes;}};
''' + periodic + r'''
int main(int,char** argv){
 const unsigned expect=std::strtoul(argv[1],nullptr,10);
 assert(NovaSync::SubmitEveryDraws()==expect);
 Scheduler s;for(unsigned i=0;i<5000;++i)NovaPeriodicSubmit(s);
 assert(s.flushes==(expect?5000/expect:0));
 puts("NOVA_0954_PERIODIC: PASS");
}''')
    run(per, '1024'); run(per, '0', NOVA_SUBMIT_DRAWS='0'); run(per, '64', NOVA_SUBMIT_DRAWS='3')
    run(per, '512', NOVA_SUBMIT_DRAWS='512'); run(per, '65536', NOVA_SUBMIT_DRAWS='999999')

    # ---- 3. readback off ----
    bc = (src/'graphics/host_gpu/renderer/cache/bufferCache.cpp').read_text()
    rm = between(bc, 'void BufferCache::ReadMemory(uint64_t vaddr, uint64_t size, bool is_write, ReadbackContext context) {', '\nBufferId BufferCache::FindBuffer(')
    off = between(rm, '		if (is_write && NovaSync::ReadbackOff()) {', '		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];')
    assert rm.index('NovaSync::ReadbackOff()') < rm.index('DownloadBufferMemory<false>') and 'return;' in off
    rb = build(tmp, 'readback', r'''
#include "graphics/host_gpu/novaSync.h"
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
struct Labels{std::vector<std::pair<uint64_t,uint64_t>> inv;void Invalidate(uint64_t a,uint64_t n){inv.push_back({a,n});}};
struct Ranges{std::vector<std::pair<uint64_t,uint64_t>> sub;void Subtract(uint64_t a,uint64_t n){sub.push_back({a,n});}};
struct Tracker{bool gpu=true,cpu=false;unsigned downloads_seen=0;
 template<bool clear,class F>void ForEachDownloadRange(uint64_t a,uint64_t n,F&& f){assert(!clear);if(gpu)f(a,n);}
 void UnmarkRegionAsGpuModified(uint64_t,uint64_t){gpu=false;}
 void MarkRegionAsCpuModified(uint64_t,uint64_t){assert(!gpu);cpu=true;}};
struct Cache{Labels m_eop_labels;Ranges m_gpu_modified_ranges;Tracker m_memory_tracker;unsigned downloads=0;
 void Run(uint64_t vaddr,uint64_t size,bool is_write){
''' + off + r'''
  ++downloads;}};
int main(int,char** argv){
 const bool expect_off=std::strcmp(argv[1],"off")==0;
 assert(NovaSync::ReadbackOff()==expect_off);
 Cache c;c.Run(0x10000,4096,true);const bool skipped=c.downloads==0;
 if(expect_off){assert(skipped&&!c.m_memory_tracker.gpu&&c.m_memory_tracker.cpu);
  assert(c.m_gpu_modified_ranges.sub.size()==1&&c.m_eop_labels.inv.size()==1);}
 else assert(c.downloads==1&&c.m_memory_tracker.gpu);
 Cache r;r.Run(0x10000,4096,false);assert(r.downloads==1&&r.m_memory_tracker.gpu);
 puts("NOVA_0954_READBACK: PASS");
}''')
    run(rb, 'off'); run(rb, 'off', NOVA_READBACK_MODE='off')
    run(rb, 'on', NOVA_READBACK_MODE='relaxed'); run(rb, 'on', NOVA_READBACK_MODE='precise')
    run(rb, 'on', NOVA_LABEL_MODE='accurate')

    # ---- 4. audio ----
    au = (src/'libs/audio.cpp').read_text()
    lat = between(au, 'static uint64_t NovaAudioLatencyUs() {', 'static const uint64_t AUDIO_OUT_TARGET_LATENCY_US')
    assert au.count('SDL_SetHint(SDL_HINT_ANDROID_LOW_LATENCY_AUDIO,') == 2
    for init in [i for i in range(len(au)) if au.startswith('if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {', i)]:
        assert 'SDL_HINT_ANDROID_LOW_LATENCY_AUDIO' in au[init-300:init]
    aud = build(tmp, 'audio', '#include <cassert>\n#include <cstdint>\n#include <cstdio>\n#include <cstdlib>\n' + lat + r'''
int main(int,char** argv){assert(NovaAudioLatencyUs()==std::strtoull(argv[1],nullptr,10));puts("NOVA_0954_AUDIO: PASS");}''')
    run(aud, '80000'); run(aud, '120000', NOVA_AUDIO_LATENCY_MS='120'); run(aud, '20000', NOVA_AUDIO_LATENCY_MS='5'); run(aud, '250000', NOVA_AUDIO_LATENCY_MS='900')

    # ---- 5. resolution ----
    res = build(tmp, 'raster', r'''
#include "common/novaRasterScale.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
int main(int,char** argv){
 const unsigned pct=std::strtoul(argv[1],nullptr,10);
 assert(NovaRaster::ScalePct()==pct&&NovaRaster::Enabled()==(pct<100));
 auto e=NovaRaster::Extent(1920,1080);
 if(pct==50)assert(e.first==960&&e.second==540);
 if(pct==25){assert(e.first==480&&e.second==270);auto k=NovaRaster::Extent(3840,2160);assert(k.first==960&&k.second==540);}
 if(pct==75){auto k=NovaRaster::Extent(1280,720);assert(k.first==960&&k.second==540);}
 if(pct==100)assert(!e.first);
 assert(!NovaRaster::Extent(1920,1200).first&&!NovaRaster::Extent(640,360).first&&!NovaRaster::Extent(0,0).first);
 puts("NOVA_0954_RASTER: PASS");
}''')
    run(res, '100'); run(res, '50', NOVA_RASTER_SCALE_PCT='50'); run(res, '25', NOVA_RASTER_SCALE_PCT='25')
    run(res, '75', NOVA_RASTER_SCALE_PCT='75'); run(res, '100', NOVA_RASTER_SCALE_PCT='10'); run(res, '100', NOVA_RASTER_SCALE_PCT='150')
print('NOVA_0954_REGRESSION: PASS')
