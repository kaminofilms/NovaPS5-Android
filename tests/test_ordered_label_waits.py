#!/usr/bin/env python3
"""Execute the production WAIT_REG_MEM, TryPeekEopLabel, IsEopLabelPending and
PollCompletion bodies: a known queued label that satisfies the predicate lets
the PM4 queue continue without a submit, host wait or suspension; everything
else keeps the cooperative suspend / coherent read path. Harness types are
shared with test_ever_cooperative_label_waits.py.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(sys.argv[1]); tests = Path(__file__).resolve().parent
renderer = root/'src/graphics/host_gpu/renderer'
src = (tests/'test_ever_cooperative_label_waits.py').read_text()
ns = {}
exec(src[src.index("pre = r'''"):src.index("post = r'''")], ns)
pre, bridge, bridge2 = ns['pre'], ns['bridge'], ns['bridge2']
anchor = ' bool IsEopLabelPending(uint64_t,uint64_t);'
assert pre.count(anchor) == 1
pre = pre.replace(anchor, anchor + '\n bool TryPeekEopLabel(uint64_t,void*,uint64_t);')

def between(s, a, b):
    return s[s.index(a):s.index(b, s.index(a))]
bc = (renderer/'cache/bufferCache.cpp').read_text()
peek = between(bc, 'bool BufferCache::TryPeekEopLabel(', 'bool BufferCache::IsEopLabelPending(')
pending = between(bc, 'bool BufferCache::IsEopLabelPending(', 'bool BufferCache::TryPublishEopLabels(')
read = between(bc, 'bool BufferCache::TryReadEopLabel(', '\nvoid BufferCache::Register(')
assert 'Wait(' not in peek and 'Flush(' not in peek and 'Subtract(' not in peek and 'Invalidate(' not in peek
poll = between((renderer/'commandScheduler.cpp').read_text(), 'bool CommandScheduler::PollCompletion(', 'void CommandScheduler::PopPendingOperations(')
gr = (root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
wait = between(gr, 'template <typename T>\nvoid CommandProcessor::WaitRegMem(', '\ntemplate void CommandProcessor::WaitRegMem<uint32_t>')
predicate = between(gr, 'bool TestWaitRegMemValue(uint64_t value, uint64_t ref, uint64_t mask, uint32_t func) {', '\ntemplate <typename T>\nvoid CommandProcessor::WaitRegMem(')
assert wait.index('TryPeekEopLabel') < wait.index('IsEopLabelPending')
routing = between((root/'src/kernel/memory.cpp').read_text(), 'bool TryReadBufferBacking(', '\nuint64_t ClampRangeSize(')

post = r'''
}
int main(){
 using namespace Libs::Graphics; namespace M=Libs::LibKernel::Memory;
 const bool fast=NovaRender::LabelReadbackProfile()&&NovaRender::OrderedLabelWaits();
 for(unsigned n:{4u,8u}) for(unsigned func=0;func<7;++func) for(uint64_t ref:{5ull,6ull}){
  BufferCache cache;CommandProcessor cp(cache);M::resources.cache=&cache;
  uint64_t label=0;const uint64_t a=reinterpret_cast<uint64_t>(&label);
  uint64_t v=5;cache.m_eop_labels.Record(a,&v,n,7);
  auto run=[&]{if(n==4)cp.WaitRegMem<uint32_t>(func,reinterpret_cast<uint32_t*>(&label),uint32_t(ref),~0u,0,0);else cp.WaitRegMem<uint64_t>(func,&label,ref,~0ull,0,0);};
  const auto reads=M::backing_reads;run();
  const bool sat=TestWaitRegMemValue(5,ref,~0ull,func);
  if(!NovaRender::LabelReadbackProfile()){assert(cp.suspended==unsigned(!TestWaitRegMemValue(0,ref,~0ull,func)));continue;}
  if(fast&&sat){
   // Continue in GPU order: no submit, no host wait, no CPU publication, label untouched.
   assert(cp.suspended==0&&cache.m_scheduler.flushes==0&&cache.m_scheduler.waits==0&&cache.m_scheduler.publications==0);
   assert(M::backing_reads==reads&&cache.downloads==0&&label==0&&cache.m_eop_labels.Size()==1);
  }else{
   // Unsatisfied known value or opt-out: unchanged cooperative suspend on the real producer.
   assert(cp.suspended==1&&cache.m_scheduler.flushes==1&&cache.m_scheduler.waits==0&&label==0);
  }
 }
 // Not eligible for the shortcut: texture-backed, no longer GPU-dirty, invalidated, unknown.
 for(int c=0;c<4;++c){
  BufferCache cache;CommandProcessor cp(cache);M::resources.cache=&cache;
  uint64_t label=0;const uint64_t a=reinterpret_cast<uint64_t>(&label);uint64_t v=5;
  if(c!=3)cache.m_eop_labels.Record(a,&v,8,7);
  if(c==0)cache.m_texture_cache.overlap=true;
  if(c==1)cache.m_gpu_modified_ranges.value=false;
  if(c==2)cache.m_eop_labels.Invalidate(a,8);
  uint64_t out=0;assert(!cache.TryPeekEopLabel(a,&out,8)&&out==0);
  M::backing=5;const auto reads=M::backing_reads;
  cp.WaitRegMem<uint64_t>(3,&label,5,~0ull,0,0);
  (void)reads;assert(cp.suspended==unsigned(!NovaRender::GpuLabelProfile()));
  assert(cache.m_scheduler.flushes==0);
 }
 // Invalid sizes and ranges never peek.
 {BufferCache cache;uint64_t v=5,out=0;const uint64_t a=reinterpret_cast<uint64_t>(&v);cache.m_eop_labels.Record(a,&v,8,7);
  assert(!cache.TryPeekEopLabel(a,&out,3)&&!cache.TryPeekEopLabel(UINT64_MAX-2,&out,4)&&!cache.TryPeekEopLabel(a,nullptr,8));
  if(NovaRender::LabelReadbackProfile()){assert(cache.TryPeekEopLabel(a+4,&out,4)&&out==0);}}
 puts("NOVA_ORDERED_WAIT_TEST: satisfied known labels continue without submit/wait/publication; unsatisfied, texture, clean, invalidated, unknown and opt-out keep suspend/coherent reads PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p/'test.cpp').write_text(pre+poll+peek+pending+read+bridge+routing+bridge2+predicate+wait+post)
    flags = ['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
    subprocess.run(['c++','-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror',*flags,'-I'+str(renderer),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    for title in ['PPSA04703','PPSA27841','PPSA15552','']:
        for labels in (None,'0'):
            for ordered in (None,'0'):
                env = dict(os.environ, NOVA_CACHE_TITLE_ID=title)
                for k,v in (('NOVA_GPU_LABELS',labels),('NOVA_GPU_ORDERED_WAITS',ordered)):
                    env.pop(k,None)
                    if v is not None: env[k]=v
                subprocess.run([str(p/'test')],env=env,check=True,timeout=20)
print('NOVA_ORDERED_WAIT_REGRESSION: PASS')
