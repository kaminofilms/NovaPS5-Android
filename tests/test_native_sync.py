#!/usr/bin/env python3
"""0.9.53 native-speed sync: execute the production bodies.

1. Mode switches (fast/accurate labels, relaxed/precise readbacks, fault window).
2. RELEASE_MEM fast path: label visible when the packet is processed, no host
   drain/submit, IRQ only after real completion, timestamps sampled immediately.
   Accurate mode re-runs the existing completion/ordered/cooperative tests.
3. RegionManager::UpdateProtection: relaxed skips only read protection.
4. MemoryTracker::InvalidateCleanWindow: releases CPU-clean, GPU-clean pages of
   the aligned window; GPU-dirty pages keep protection; BDA sync is queued.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(sys.argv[1]); tests = Path(__file__).resolve().parent
src = root/'src'; renderer = src/'graphics/host_gpu/renderer'; host = src/'graphics/host_gpu'
SAN = ['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []

def build(tmp, name, code):
    p = Path(tmp)/(name+'.cpp'); p.write_text(code); out = Path(tmp)/name
    subprocess.run(['g++','-std=c++20','-O1','-g','-Wall','-Wextra','-Wno-unused-variable','-Wno-unused-parameter',*SAN,
                    '-I'+str(src),'-I'+str(renderer),str(p),'-o',str(out)],check=True)
    return out

def run(binary, **env):
    e = dict(os.environ)
    for k in ('NOVA_LABEL_MODE','NOVA_READBACK_MODE','NOVA_FAULT_WINDOW_KB','NOVA_GPU_LABELS'): e.pop(k, None)
    e.update({k:v for k,v in env.items() if v is not None})
    subprocess.run([str(binary)], env=e, check=True, timeout=30)

def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]

gr = (src/'graphics/guest_gpu/graphicsRun.cpp').read_text()
assert 'if (NovaSync::FastLabels()) {' in gr
assert 'NovaRender::GpuLabelProfile() || !NovaSync::PreciseReadbacks()' in gr
rc = (renderer/'renderContext.cpp').read_text()
fault = between(rc, 'bool RenderContext::HandleFault(', 'bool RenderContext::InvalidateMemory(')
assert fault.index('m_buffer_cache.InvalidateMemory(') < fault.index('InvalidateCleanWindow(') and 'IsMapped(begin, window)' in fault

with tempfile.TemporaryDirectory() as tmp:
    # ---- 1. modes ----
    probe = build(tmp, 'probe', r'''
#include "novaRenderCosts.h"
#include <cassert>
#include <cstdio>
#include <cstring>
int main(int, char** argv){
 const bool accurate=std::strcmp(argv[1],"accurate")==0, precise=std::strcmp(argv[2],"precise")==0;
 const long kb=std::atol(argv[3]);
 const char* t=std::getenv("NOVA_CACHE_TITLE_ID");const std::string_view title=t?t:"";
 assert(NovaSync::FastLabels()==!accurate);
 assert(NovaSync::PreciseReadbacks()==(accurate||precise));
 assert(NovaSync::FaultWindowBytes()==uint64_t(kb)*1024u);
 const bool listed=title=="PPSA04703"||title=="PPSA31162"||title=="PPSA15552";
 if(!accurate){assert(!NovaRender::GpuLabelProfile()&&!NovaRender::LabelReadbackProfile());}
 else{assert(NovaRender::GpuLabelProfile()==(NovaRender::GenericGpuLabels()||listed));}
 assert(NovaRender::EverProfile()==(title=="PPSA04703"));
 puts("NOVA_SYNC_MODES: PASS");
}''')
    for title in ['PPSA27841','PPSA04703','PPSA15552','PPSA31162','']:
        subprocess.run([str(probe),'fast','relaxed','64'],env={**{k:v for k,v in os.environ.items() if not k.startswith('NOVA_')},'NOVA_CACHE_TITLE_ID':title},check=True)
        subprocess.run([str(probe),'accurate','precise','64'],env={**{k:v for k,v in os.environ.items() if not k.startswith('NOVA_')},'NOVA_CACHE_TITLE_ID':title,'NOVA_LABEL_MODE':'accurate'},check=True)
        subprocess.run([str(probe),'fast','precise','0'],env={**{k:v for k,v in os.environ.items() if not k.startswith('NOVA_')},'NOVA_CACHE_TITLE_ID':title,'NOVA_READBACK_MODE':'precise','NOVA_FAULT_WINDOW_KB':'0'},check=True)
        subprocess.run([str(probe),'fast','relaxed','64'],env={**{k:v for k,v in os.environ.items() if not k.startswith('NOVA_')},'NOVA_CACHE_TITLE_ID':title,'NOVA_FAULT_WINDOW_KB':'100'},check=True)
        subprocess.run([str(probe),'fast','relaxed','256'],env={**{k:v for k,v in os.environ.items() if not k.startswith('NOVA_')},'NOVA_CACHE_TITLE_ID':title,'NOVA_FAULT_WINDOW_KB':'256'},check=True)

    # ---- 2. RELEASE_MEM fast path (harness shared with test_gpu_completion.py) ----
    t = (tests/'test_gpu_completion.py').read_text()
    ns = {}
    exec(t[t.index("pre=r'''"):t.index("post=r'''")], ns)
    pre = ns['pre']
    old = 'void Copy(void* p,const void* v,size_t n){assert(gpu_finished);++writes;std::memcpy(p,v,n);}'
    assert pre.count(old) == 1
    pre = pre.replace(old, 'void Copy(void* p,const void* v,size_t n){++writes;std::memcpy(p,v,n);}')
    body = between(gr, 'template <typename T>\nvoid CommandProcessor::WriteAtEndOfPipe(', '\nvoid CommandProcessor::WriteAtEndOfPipe32(')
    post = r'''
int main(){
 const bool fast=NovaSync::FastLabels();
 auto no_gpu_label=[](uint64_t,const void*,uint64_t){assert(false&&"fast labels never record GPU copies");return false;};
 for(unsigned width:{4u,8u}) for(unsigned irq:{0u,2u}) for(unsigned cache:{0u,0x38u}) {
  gpu_finished=false;CommandProcessor cp;alignas(8) uint64_t label=0;
  const uint64_t expected=width==4?0x89abcdefull:0x0123456789abcdefull;
  cp.m_renderer.label=&label;cp.m_renderer.expected=expected;
  if(fast)cp.m_renderer.cache.write=no_gpu_label;
  if(width==4)cp.WriteAtEndOfPipe<uint32_t>(0,0,0x2f,cache,6,2,&label,uint32_t(expected),irq,0x55);
  else cp.WriteAtEndOfPipe<uint64_t>(0,0,cache?0x2b:0x2d,cache,0,2,&label,expected,irq,0x55);
  if(fast){
   // Visible at packet time; no drain, no submit; IRQ waits for real completion.
   assert(label==expected&&!gpu_finished&&cp.scheduler.submitted==0&&cp.scheduler.completed==0&&cp.m_renderer.irqs==0);
   assert(GuestMemory::writes>0);
   cp.scheduler.Flush();assert(cp.m_renderer.irqs==0);
   cp.scheduler.Complete();assert(cp.m_renderer.irqs==(irq==2));
   if(irq)assert(cp.m_renderer.context==0x55);
  }else{
   cp.scheduler.Flush();cp.scheduler.Complete();
   assert(label==expected&&cp.m_renderer.irqs==(irq==2));
  }
 }
 if(fast){
  gpu_finished=false;CommandProcessor cp;uint64_t stamp=0;
  cp.WriteAtEndOfPipe<uint64_t>(0,0,0x28,0,0,4,&stamp,0,0,0);
  assert(stamp>10&&!gpu_finished&&cp.scheduler.submitted==0);
  CommandProcessor bad;uint64_t l=0;bool rejected=false;
  try{bad.WriteAtEndOfPipe<uint64_t>(0,0,0x3f,0,0,2,&l,1,0,0);}catch(...){rejected=true;}
  assert(rejected&&l==0&&bad.scheduler.pending.empty());
  bool null_rejected=false;CommandProcessor n;
  try{n.WriteAtEndOfPipe<uint64_t>(0,0,0x2b,0,0,2,nullptr,1,0,0);}catch(...){null_rejected=true;}
  assert(null_rejected&&n.scheduler.pending.empty());
 }
 puts(fast?"NOVA_SYNC_EOP: fast labels visible at packet time, no drain/submit, IRQ after real completion, immediate timestamps, unsupported/null rejection PASS"
          :"NOVA_SYNC_EOP: accurate mode unchanged PASS");
}
'''
    eop = build(tmp, 'eop', pre + body + post)
    base = {k:v for k,v in os.environ.items() if not k.startswith('NOVA_')}
    for title in ['PPSA27841','PPSA04703','PPSA15552','PPSA31162','']:
        subprocess.run([str(eop)],env={**base,'NOVA_CACHE_TITLE_ID':title},check=True)
        subprocess.run([str(eop)],env={**base,'NOVA_CACHE_TITLE_ID':title,'NOVA_LABEL_MODE':'accurate'},check=True)

    # ---- 3. relaxed read protection ----
    rm = (host/'regionManager.h').read_text()
    upd = between(rm, 'template <bool track, bool is_read>\n\tvoid UpdateProtection() {', '\n\ttemplate <DirtySource source>\n\tRegionBits& GetBits() {')
    assert 'if (!NovaSync::PreciseReadbacks()) return;' in upd
    prot = build(tmp, 'prot', r'''
#include "graphics/host_gpu/novaSync.h"
#include <bitset>
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <vector>
struct RegionBits{std::bitset<64> b;RegionBits operator~()const{RegionBits r;r.b=~b;return r;}RegionBits operator^(const RegionBits& o)const{RegionBits r;r.b=b^o.b;return r;}bool None()const{return b.none();}};
struct Call{bool track,is_read;std::bitset<64> mask;};
struct PageManager{std::vector<Call> calls;template<bool track,bool is_read>void UpdatePageWatchersForRegion(uint64_t,const RegionBits& m){calls.push_back({track,is_read,m.b});}};
struct R{
 PageManager& m_page_manager;uint64_t m_cpu_addr=0;RegionBits m_cpu_dirty,m_gpu_dirty,m_writable,m_readable;
 explicit R(PageManager& p):m_page_manager(p){m_cpu_dirty.b.set();m_writable.b.set();m_readable.b.set();}
''' + upd + r'''
};
int main(){
 const bool precise=NovaSync::PreciseReadbacks();
 PageManager pm;R r(pm);
 // Upload clears CPU dirty pages 0-3: write protection is added in both modes.
 r.m_cpu_dirty.b.reset(0);r.m_cpu_dirty.b.reset(1);r.m_cpu_dirty.b.reset(2);r.m_cpu_dirty.b.reset(3);
 r.UpdateProtection<true,false>();assert(pm.calls.size()==1&&!pm.calls[0].is_read&&pm.calls[0].mask.count()==4);
 // GPU writes pages 1-2: read protection only in precise mode.
 r.m_gpu_dirty.b.set(1);r.m_gpu_dirty.b.set(2);r.UpdateProtection<true,true>();
 if(precise)assert(pm.calls.size()==2&&pm.calls[1].is_read&&pm.calls[1].mask.count()==2&&r.m_readable.b.count()==62);
 else assert(pm.calls.size()==1&&r.m_readable.b.all());
 // Download clears GPU dirty: symmetric untrack, still no read calls in relaxed mode.
 r.m_gpu_dirty.b.reset();r.UpdateProtection<false,true>();
 if(precise)assert(pm.calls.size()==3&&pm.calls[2].is_read&&r.m_readable.b.all());else assert(pm.calls.size()==1);
 // CPU write releases page 0: write protection removed in both modes.
 r.m_cpu_dirty.b.set(0);r.UpdateProtection<false,false>();assert(!pm.calls.back().is_read&&pm.calls.back().mask.count()==1);
 puts(precise?"NOVA_SYNC_READBACK: precise read protection unchanged PASS":"NOVA_SYNC_READBACK: relaxed skips read protection only; write protection intact PASS");
}''')
    run(prot); run(prot, NOVA_READBACK_MODE='precise'); run(prot, NOVA_LABEL_MODE='accurate')

    # ---- 4. write-fault window ----
    mt = (host/'memoryTracker.h').read_text()
    win = between(mt, '\tvoid InvalidateCleanWindow(uint64_t vaddr, uint64_t window) noexcept {', '\n#if KYTY_BUILD == KYTY_BUILD_DEBUG')
    window = build(tmp, 'window', r'''
#include <bitset>
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <mutex>
#include <vector>
constexpr uint64_t TRACKER_PAGE_SIZE=4096, TRACKER_REGION_SIZE=4ull*1024*1024;
enum class DirtySource{Cpu,Gpu};
struct RegionManager{
 uint64_t base;std::bitset<1024> cpu,gpu;std::mutex lock;std::vector<std::pair<uint64_t,uint64_t>> changes;
 explicit RegionManager(uint64_t b):base(b){}
 uint64_t GetCpuAddr()const{return base;}
 template<DirtySource s>bool IsModified(uint64_t off,uint64_t n){for(uint64_t p=off/4096;p<(off+n+4095)/4096;++p)if((s==DirtySource::Gpu?gpu:cpu).test(p))return true;return false;}
 template<DirtySource s,bool en>void ChangeState(uint64_t addr,uint64_t n){
  static_assert(s==DirtySource::Cpu&&en);changes.push_back({addr,n});
  for(uint64_t p=(addr-base)/4096;p<(addr-base+n)/4096;++p){assert(!gpu.test(p));cpu.set(p);}}
};
struct Tracker{
 std::vector<RegionManager*> regions;std::vector<std::pair<uint64_t,uint64_t>> bda;
 void CheckNotInUploadCallback()const noexcept{}
 void QueueBdaSync(uint64_t a,uint64_t n){bda.push_back({a,n});}
 template<bool create,class F>bool Iterate(uint64_t vaddr,uint64_t size,F&& f){
  uint64_t rem=size,idx=vaddr/TRACKER_REGION_SIZE,off=vaddr%TRACKER_REGION_SIZE;
  while(rem){const auto bytes=std::min(TRACKER_REGION_SIZE-off,rem);if(idx<regions.size()&&regions[idx])f(regions[idx],off,bytes);rem-=bytes;off=0;++idx;}return false;}
''' + win + r'''
};
int main(){
 RegionManager r0(0),r1(TRACKER_REGION_SIZE);Tracker t;t.regions={&r0,&r1};
 // Window 0x10000-0x1ffff (pages 16-31). Pages 20,21 GPU-dirty; page 25 already CPU-dirty.
 r0.gpu.set(20);r0.gpu.set(21);r0.cpu.set(25);
 t.InvalidateCleanWindow(0x17123,65536);
 for(int p=16;p<32;++p)assert(r0.cpu.test(p)==(p!=20&&p!=21));
 assert(r0.gpu.test(20)&&r0.gpu.test(21));
 assert((r0.changes==std::vector<std::pair<uint64_t,uint64_t>>{{0x10000,0x4000},{0x16000,0xa000}}));
 assert(t.bda.size()==1&&t.bda[0].first==0x10000&&t.bda[0].second==65536);
 for(int p=0;p<16;++p){assert(!r0.cpu.test(p));}
 for(int p=32;p<64;++p){assert(!r0.cpu.test(p));}
 // Invalid window sizes do nothing.
 const auto before=r0.changes.size();t.InvalidateCleanWindow(0x40000,3000);t.InvalidateCleanWindow(0x40000,24576);t.InvalidateCleanWindow(0x40000,0);
 assert(r0.changes.size()==before&&t.bda.size()==1);
 // A window in a region with no tracker does nothing but is harmless.
 Tracker empty;empty.InvalidateCleanWindow(0x123456,65536);assert(empty.bda.size()==1);
 // The last window of region 0 stays inside it.
 t.InvalidateCleanWindow(TRACKER_REGION_SIZE-1,65536);assert(r1.changes.empty()&&r0.cpu.test(1023)&&r0.cpu.test(1008));
 puts("NOVA_SYNC_WINDOW: aligned window, GPU-dirty pages untouched, contiguous runs, BDA sync, invalid sizes ignored PASS");
}''')
    run(window)

# ---- accurate mode keeps the existing production behaviour ----
inc = dict(os.environ, CPLUS_INCLUDE_PATH=str(src))
for name, extra in [('test_gpu_completion.py', {'NOVA_LABEL_MODE':'accurate'}),
                    ('test_ordered_label_waits.py', {'NOVA_LABEL_MODE':'accurate'})]:
    subprocess.run([sys.executable, str(tests/name), str(root)], env={**inc, **extra}, check=True)
print('NOVA_SYNC_REGRESSION: PASS')
