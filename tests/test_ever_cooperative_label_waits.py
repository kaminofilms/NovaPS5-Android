#!/usr/bin/env python3
"""Execute production polling, label reads, kernel routing and WAIT_REG_MEM.

Controlled timelines verify queue progress and ordering, not device FPS.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
renderer = root / 'src/graphics/host_gpu/renderer'
def between(s, a, b):
    return s[s.index(a):s.index(b, s.index(a))]
s = (renderer/'cache/bufferCache.cpp').read_text()
pending = between(s, 'bool BufferCache::IsEopLabelPending(', 'bool BufferCache::TryPublishEopLabels(')
read = between(s, 'bool BufferCache::TryReadEopLabel(', '\nvoid BufferCache::Register(')
scheduler = (renderer/'commandScheduler.cpp').read_text()
poll = between(scheduler, 'bool CommandScheduler::PollCompletion(', 'void CommandScheduler::PopPendingOperations(')
gr = (root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
wait = between(gr, 'template <typename T>\nvoid CommandProcessor::WaitRegMem(', '\ntemplate void CommandProcessor::WaitRegMem<uint32_t>')
predicate = between(gr, 'bool TestWaitRegMemValue(uint64_t value, uint64_t ref, uint64_t mask, uint32_t func) {', '\ntemplate <typename T>\nvoid CommandProcessor::WaitRegMem(')
kernel = (root/'src/kernel/memory.cpp').read_text()
routing = between(kernel, 'bool TryReadBufferBacking(', '\nuint64_t ClampRangeSize(')
# Submission retries the same packet; completion still uses the original predicate.
assert 'if (execution.m_suspended) {\n\t\t\treturn;\n\t\t}\n\t\tcursor.offset_dw += packet_dw;' in gr
assert 'm_work_available.WaitFor(&gpu->m_queue_mutex, 100)' in gr
assert 'if (!queue.empty()) {\n\t\t\t\t\t\t\tqueue.front().blocked = false;' in gr
assert 'Wait(' not in poll and 'WaitPriorityOperations(' not in poll
assert 'WriteBacking' not in pending and '.Subtract(' not in pending
pre = r'''
#include "novaRenderCosts.h"
#include "novaEopLabels.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cinttypes>
#include <functional>
#include <mutex>
#include <queue>
#include <stdexcept>
#define EXIT(...) throw std::runtime_error("invalid")
#define EXIT_IF(x) do { if(x) EXIT(); } while(0)
struct GuestRange {uint64_t a,n;bool Valid()const{return a&&n&&n<=UINT64_MAX-a;}};
namespace GuestMemory {template<class T>const T* Ptr(const T* p,uint64_t){return p;}}
namespace Libs::Graphics {
struct GuestGpu {static inline bool gpu=true;static bool IsGpuThread(){return gpu;}};
struct CommandScheduler {
 uint64_t current=7,completed=0;unsigned flushes=0,waits=0,publications=0;
 bool m_priority_active=false;uint64_t m_priority_active_tick=0;
 struct Op {uint64_t tick;};std::queue<Op> m_priority_operations;std::mutex m_operation_mutex;
 std::function<void()> on_flush,on_wait;
 uint64_t CurrentTick(){return current;}
 void Flush(){++flushes;++current;if(on_flush)on_flush();}
 bool IsFree(uint64_t tick){return completed>=tick;}
 bool PollCompletion(uint64_t);
 void Wait(uint64_t tick){++waits;assert(tick<=completed);if(on_wait)on_wait();}
 void WaitPriorityOperations(uint64_t tick){++publications;assert(!m_priority_active||m_priority_active_tick>tick);assert(m_priority_operations.empty()||m_priority_operations.front().tick>tick);}
};
struct BufferCache {
 using ReadbackCaller=NovaRender::ReadbackCaller;
 using ReadbackContext=NovaRender::ReadbackContext;
 NovaRender::EopLabels m_eop_labels;
 struct Dirty {bool value=true;bool Contains(uint64_t,uint64_t){return value;}}m_gpu_modified_ranges;
 struct Textures {bool overlap=false;bool FindImageFromRange(uint64_t,uint64_t){return overlap;}}m_texture_cache;
 CommandScheduler m_scheduler;unsigned downloads=0;
 bool IsEopLabelPending(uint64_t,uint64_t);
 bool TryReadEopLabel(uint64_t,void*,uint64_t);
 bool HasGpuDirtyBytes(uint64_t,uint64_t){return m_gpu_modified_ranges.value;}
 void ReadMemory(uint64_t a,uint64_t n,bool write,ReadbackContext context){assert(!write&&context.caller==NovaRender::ReadbackCaller::Other);++downloads;m_gpu_modified_ranges.value=false;m_eop_labels.Invalidate(a,n);}
};
'''
bridge = r'''
}
namespace Libs::LibKernel::Memory {
struct Resources {Graphics::BufferCache* cache;auto& GetBufferCache(){return *cache;}};
Resources resources;Resources* g_gpu_resources=&resources;
Resources& GetGpuResources(){return resources;}
bool IsGpuAddressRange(uint64_t,uint64_t){return true;}
unsigned backing_reads=0;uint64_t backing=5;
bool TryReadBacking(uint64_t,void* data,uint64_t n){++backing_reads;assert(n<=8);std::memcpy(data,&backing,n);return true;}
'''
bridge2 = r'''
}
namespace Libs::Graphics {
struct Renderer {BufferCache& cache;auto& GetBufferCache(){return cache;}};
struct CommandProcessor {
 Renderer m_renderer;unsigned suspended=0;
 explicit CommandProcessor(BufferCache& cache):m_renderer{cache}{}
 void SuspendPm4(){++suspended;}
 template<class T>void WaitRegMem(uint32_t,const T*,T,T,uint32_t,uint32_t);
};
'''
post = r'''
}
int main(){
 using namespace Libs::Graphics;
 namespace M=Libs::LibKernel::Memory;
 // A current tick must be submitted exactly once; polling never advances it again.
 CommandScheduler scheduler;
 assert(!scheduler.PollCompletion(7)&&scheduler.flushes==1&&scheduler.current==8);
 assert(!scheduler.PollCompletion(7)&&scheduler.flushes==1);
 scheduler.completed=7;
 scheduler.m_priority_active=true;scheduler.m_priority_active_tick=7;
 assert(!scheduler.PollCompletion(7));scheduler.m_priority_active=false;
 scheduler.m_priority_operations.push({7});assert(!scheduler.PollCompletion(7));
 scheduler.m_priority_operations.pop();scheduler.m_priority_operations.push({8});
 assert(scheduler.PollCompletion(7));scheduler.m_priority_active=true;scheduler.m_priority_active_tick=8;
 assert(scheduler.PollCompletion(7)&&scheduler.waits==0&&scheduler.publications==0);
 bool rejected=false;try{scheduler.PollCompletion(9);}catch(...){rejected=true;}assert(rejected);
 for(unsigned n:{4u,8u}) for(unsigned func=0;func<7;++func){
  BufferCache cache;CommandProcessor cp(cache);M::resources.cache=&cache;
  uint64_t label=5;const uint64_t a=reinterpret_cast<uint64_t>(&label);
  cache.m_eop_labels.Record(a,&label,n,7);
  auto run=[&]{if(n==4)cp.WaitRegMem<uint32_t>(func,reinterpret_cast<uint32_t*>(&label),5,~0u,0,0);else cp.WaitRegMem<uint64_t>(func,&label,5,~0ull,0,0);};
  const auto reads=M::backing_reads;
  if(NovaRender::EverProfile()){
   run();assert(cp.suspended==1&&cache.m_scheduler.flushes==1&&cache.m_scheduler.waits==0);
   assert(M::backing_reads==reads&&cache.downloads==0&&label==5);
   // A different queue can complete work while the dependent queue is suspended.
   BufferCache independent;independent.m_gpu_modified_ranges.value=false;
   CommandProcessor other(independent);M::resources.cache=&independent;
   other.WaitRegMem<uint64_t>(3,&label,5,~0ull,0,0);assert(other.suspended==0);
   M::resources.cache=&cache;cache.m_scheduler.completed=7;
   cache.m_scheduler.m_priority_active=true;cache.m_scheduler.m_priority_active_tick=7;
   run();assert(cp.suspended==2&&cache.m_scheduler.waits==0);
   cache.m_scheduler.m_priority_active=false;
  }else cache.m_scheduler.completed=7;
  const auto suspended=cp.suspended;run();
  assert(cp.suspended==suspended+!TestWaitRegMemValue(5,5,~0ull,func));
  assert(label==5&&cache.m_gpu_modified_ranges.value&&cache.m_eop_labels.Size()==1);
 }
 // Unknown data, textures, invalid ranges and unrelated titles do not claim readiness.
 BufferCache cache;uint64_t v=5;uint64_t a=reinterpret_cast<uint64_t>(&v);
 assert(!cache.IsEopLabelPending(a,4)&&cache.m_scheduler.flushes==0);
 cache.m_eop_labels.Record(a,&v,8,7);
 assert(!cache.IsEopLabelPending(a,3)&&!cache.IsEopLabelPending(UINT64_MAX-2,4));
 cache.m_texture_cache.overlap=true;assert(!cache.IsEopLabelPending(a,8));cache.m_texture_cache.overlap=false;
 cache.m_gpu_modified_ranges.value=false;assert(!cache.IsEopLabelPending(a,8));cache.m_gpu_modified_ranges.value=true;
 if(NovaRender::EverProfile()){
  assert(cache.IsEopLabelPending(a,8));
  // Overwrite while suspended: wait for the NEW producer, never return the old constant.
  v=9;cache.m_eop_labels.Record(a,&v,8,8);
  cache.m_scheduler.completed=7;assert(cache.IsEopLabelPending(a,8)&&cache.m_scheduler.flushes==2);
  cache.m_scheduler.completed=8;assert(!cache.IsEopLabelPending(a,8));
  uint64_t result=0;assert(cache.TryReadEopLabel(a,&result,8)&&result==9);
  cache.m_eop_labels.Invalidate(a,8);assert(!cache.IsEopLabelPending(a,8));
  M::resources.cache=&cache;M::backing=11;CommandProcessor cp(cache);
  cp.WaitRegMem<uint64_t>(3,&v,11,~0ull,0,0);assert(cp.suspended==0&&cache.downloads==1);
 }else assert(!cache.IsEopLabelPending(a,8)&&cache.m_scheduler.flushes==0);
 puts("NOVA_COOPERATIVE_LABEL_TEST: submit once, no host wait, independent queue progress, publication ordering, exact predicates, overwrite/invalidation/fallback PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)
    (p/'test.cpp').write_text(pre+poll+pending+read+bridge+routing+bridge2+predicate+wait+post)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
    subprocess.run(['c++','-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror',*flags,'-I'+str(renderer),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    for title in ['PPSA04703','PPSA31162','']:
        subprocess.run([str(p/'test')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True,timeout=20)
