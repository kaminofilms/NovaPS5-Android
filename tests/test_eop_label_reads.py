#!/usr/bin/env python3
"""Execute production constant-label lookup and kernel read routing. Controlled host
timeline fixtures test the dependency, not device FPS. Vulkan upload bytes are
independently checked by test_ever_gpu_labels.py.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root=Path(sys.argv[1]);renderer=root/'src/graphics/host_gpu/renderer'
s=(renderer/'cache/bufferCache.cpp').read_text()
method=s[s.index('bool BufferCache::TryReadEopLabel('):s.index('\nvoid BufferCache::Register(')]
kernel=(root/'src/kernel/memory.cpp').read_text()
read=kernel[kernel.index('bool TryReadBufferBacking('):kernel.index('\nuint64_t ClampRangeSize(')]
texture=(renderer/'cache/textureCache.cpp').read_text()
assert s.count('m_gpu_modified_ranges.Add(')==1
assert 'm_eop_labels.Invalidate(vaddr, size);\n\t\tm_gpu_modified_ranges.Add(vaddr, size);' in s
assert 'm_eop_labels.Invalidate(address, bytes);\n\t\t    m_gpu_modified_ranges.Subtract(address, bytes);' in s
assert 'm_eop_labels.Invalidate(buffer.CpuAddress(), buffer.Size());' in s
assert 'm_eop_labels.Invalidate(image.info.data.address, copy_size);' in texture
assert s.index('WriteDataBuffer(*buffer, vaddr, data, size);') < s.index('m_eop_labels.Record(')
assert 'WriteBacking' not in method and 'UnmarkRegion' not in method and '.Subtract(' not in method
assert method.index('m_scheduler.Wait(known->tick)') < method.index('WaitPriorityOperations(known->tick)') < method.index('std::memcpy(data,')
gr=(root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
assert gr.count('NovaRender::GpuLabelProfile()')==6
assert 'if (!TestWaitRegMemValue(*value, ref, mask, func))' in gr
assert 'SuspendPm4();' in gr

pre=r'''
#include "novaRenderCosts.h"
#include "novaEopLabels.h"
#include <cassert>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <atomic>
#include <vector>
#include <cstring>
struct GuestRange {uint64_t a,n;bool Valid() const{return a && n && n<=UINT64_MAX-a;}};
namespace Graphics {
struct GuestGpu {static inline bool gpu=true;static bool IsGpuThread(){return gpu;}};
struct Scheduler {
 unsigned waits=0,publications=0,submits=0;uint64_t current=1;
 std::function<void()> on_wait,on_publish;
 void Wait(uint64_t tick){++waits;if(tick>=current){++submits;current=tick+1;}if(on_wait)on_wait();}
 void WaitPriorityOperations(uint64_t){++publications;if(on_publish)on_publish();}
};
struct BufferCache {
 using ReadbackCaller=NovaRender::ReadbackCaller;
 using ReadbackContext=NovaRender::ReadbackContext;
 NovaRender::EopLabels m_eop_labels;
 struct Dirty{bool dirty=true;bool Contains(uint64_t,uint64_t){return dirty;}}m_gpu_modified_ranges;
 struct Textures{bool overlap=false;bool FindImageFromRange(uint64_t,uint64_t){return overlap;}}m_texture_cache;
 Scheduler m_scheduler;unsigned downloads=0;
 bool TryReadEopLabel(uint64_t,void*,uint64_t);
 bool HasGpuDirtyBytes(uint64_t,uint64_t){return m_gpu_modified_ranges.dirty;}
 void ReadMemory(uint64_t a,uint64_t n,bool write,ReadbackContext context){
   assert(!write && context.caller==ReadbackCaller::Other);++downloads;
   m_eop_labels.Invalidate(a,n);m_gpu_modified_ranges.dirty=false;
 }
};
'''
bridge=r'''
}
struct Resources{Graphics::BufferCache cache;auto& GetBufferCache(){return cache;}} resources;
Resources* g_gpu_resources=&resources;
bool gpu_address=true;
bool IsGpuAddressRange(uint64_t,uint64_t){return gpu_address;}
Resources& GetGpuResources(){return resources;}
uint64_t backing=0xeeeeeeeeeeeeeeeeull;unsigned backing_reads=0;
bool TryReadBacking(uint64_t,void* data,uint64_t size){++backing_reads;if(size>8)return false;std::memcpy(data,&backing,size);return true;}
'''
post=r'''
int main(){
 using NovaRender::EopLabels;
 // Stored bytes own their input. Half-open overlap and upper boundary checks.
 EopLabels labels;uint64_t source=0x123456789abcdef0ull;
 labels.Record(0x1000,&source,8,1);source=0;
 auto e=labels.Find(0x1004,4);assert(e && e->bytes[0]==0xf0);
 labels.Invalidate(0x1008,4);assert(labels.Find(0x1000,8));
 labels.Invalidate(0x1007,1);assert(!labels.Find(0x1000,8));
 labels.Record(UINT64_MAX-8,&source,8,2);assert(labels.Find(UINT64_MAX-4,4));
 assert(!labels.Find(UINT64_MAX-2,4));
 labels.Invalidate(UINT64_MAX-2,4);assert(labels.Size()==0);
 for(unsigned i=0;i<EopLabels::Capacity+1;++i)labels.Record(0x1000+i*16,&source,8,i+1);
 assert(labels.Size()<=EopLabels::Capacity && !labels.Find(0x1000,8));
 auto& cache=resources.cache;
 source=0x123456789abcdef0ull;cache.m_eop_labels.Record(0x1000,&source,8,1);
 uint64_t out=0xccccccccccccccccull;
 if(!NovaRender::GpuLabelProfile()){
   assert(!cache.TryReadEopLabel(0x1000,&out,8));assert(out==0xccccccccccccccccull && cache.m_scheduler.waits==0);
   assert(TryReadBufferBacking(0x1000,&out,8) && out==backing && cache.downloads==1);
   puts("NOVA_EOP_READ_TEST: unrelated-title fallback PASS");return 0;
 }
 // Neither GPU completion nor host publication may expose the cached bytes early.
 cache.m_scheduler.on_wait=[&]{assert(out==0xccccccccccccccccull);};
 cache.m_scheduler.on_publish=[&]{assert(out==0xccccccccccccccccull);};
 assert(TryReadBufferBacking(0x1000,&out,8) && out==source);
 assert(cache.m_scheduler.waits==1 && cache.m_scheduler.publications==1 && cache.downloads==0 && backing_reads==0);
 assert(cache.m_gpu_modified_ranges.dirty); // Guest CPU protection/ownership retained.
 cache.m_scheduler.on_wait={};cache.m_scheduler.on_publish={};
 for(unsigned i=0;i<1000;++i)assert(TryReadBufferBacking(0x1000,&out,8) && out==source);
 assert(cache.m_scheduler.submits==1 && cache.downloads==0); // No copy submission per poll.
 uint32_t high=0;assert(TryReadBufferBacking(0x1004,&high,4) && high==uint32_t(source>>32));
 // Actual callback reentrancy / invalidation during the wait must fail closed.
 cache.m_scheduler.on_wait=[&]{cache.m_eop_labels.Invalidate(0x1000,4);};
 out=0xccccccccccccccccull;assert(!cache.TryReadEopLabel(0x1000,&out,8));assert(out==0xccccccccccccccccull);
 cache.m_scheduler.on_wait={};
 assert(TryReadBufferBacking(0x1000,&out,8) && out==backing && cache.downloads==1);
 // A CPU reconciled/overwritten range cannot use old labels, even if metadata remains.
 cache.m_eop_labels.Record(0x1000,&source,8,2);cache.m_gpu_modified_ranges.dirty=false;
 assert(!cache.TryReadEopLabel(0x1000,&out,8));
 cache.m_gpu_modified_ranges.dirty=true;cache.m_texture_cache.overlap=true;
 assert(!cache.TryReadEopLabel(0x1000,&out,8));cache.m_texture_cache.overlap=false;
 // Partially overlapping shader writes remove the entire immutable entry.
 cache.m_eop_labels.Invalidate(0x1003,1);assert(!cache.TryReadEopLabel(0x1000,&out,8));
 cache.m_eop_labels.Record(0x1000,&source,8,3);
 assert(!cache.TryReadEopLabel(0x1000,&out,16));assert(!cache.TryReadEopLabel(UINT64_MAX-2,&out,4));
 Graphics::GuestGpu::gpu=false;assert(!TryReadBufferBacking(0x1000,&out,8));Graphics::GuestGpu::gpu=true;
 // A blocked real-tick fixture: publication and output stay blocked together.
 std::mutex lock;std::condition_variable cv;bool entered=false,complete=false;
 cache.m_scheduler.on_wait=[&]{std::unique_lock l(lock);entered=true;cv.notify_all();cv.wait(l,[&]{return complete;});};
 out=0xccccccccccccccccull;std::atomic<bool> returned=false;
 std::thread reader([&]{assert(cache.TryReadEopLabel(0x1000,&out,8));returned=true;});
 {std::unique_lock l(lock);cv.wait(l,[&]{return entered;});assert(!returned && out==0xccccccccccccccccull);complete=true;}cv.notify_all();reader.join();
 assert(out==source && returned);
 puts("NOVA_EOP_READ_TEST: production lookup/kernel routing, real-tick/publication gates, immutable bytes, partial overlaps, CPU/GPU invalidation, texture/overflow fallback and repeated polls PASS");
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'labels.cpp';p.write_text(pre+method+bridge+read+post)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
    subprocess.run(['g++','-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror',*flags,
                    '-I'+str(renderer),str(p),'-o',str(Path(d)/'labels')],check=True)
    for title in ('PPSA04703','PPSA31162','PPSA15552','PPSA36257',''):
        subprocess.run([str(Path(d)/'labels')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True,timeout=20)
