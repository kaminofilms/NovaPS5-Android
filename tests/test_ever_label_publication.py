#!/usr/bin/env python3
"""Execute production constant-label publication with real metadata and range sets."""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);renderer=root/'src/graphics/host_gpu/renderer'
s=(renderer/'cache/bufferCache.cpp').read_text()
method=s[s.index('bool BufferCache::TryPublishEopLabels('):s.index('bool BufferCache::TryReadEopLabel(')]
assert 'if (TryPublishEopLabels(vaddr, size, context)) return true;' in s
pre=r'''
#include "novaRenderCosts.h"
#include "novaEopLabels.h"
#include <cassert>
#include <algorithm>
#include <functional>
#include <vector>
#include <cstring>
#include <stdexcept>
#define EXIT(...) throw std::runtime_error("invalid range")
'''
pre+= (root/'src/graphics/host_gpu/rangeSet.h').read_text().replace('#include "common/assert.h"','')
pre+=r'''
struct GuestRange {uint64_t a,n;bool Valid()const{return a&&n&&n<=UINT64_MAX-a;}};
std::vector<std::pair<uint64_t,uint32_t>> writes;
namespace Libs::LibKernel::Memory {void WriteBacking(uint64_t a,const void* p,uint64_t n) {assert(n==4);uint32_t v;std::memcpy(&v,p,4);writes.emplace_back(a,v);}}
namespace Libs::Graphics {
struct BufferCache {
 using ReadbackContext=NovaRender::ReadbackContext;
 NovaRender::EopLabels m_eop_labels;RangeSet m_gpu_modified_ranges;
 struct Tracker {
  std::vector<std::pair<uint64_t,uint64_t>> pages{{0x1000,4096}};
  template<bool clear,class F>void ForEachDownloadRange(uint64_t,uint64_t,F f){static_assert(!clear);for(auto[a,n]:pages)f(a,n);}
 }m_memory_tracker;
 struct Textures {bool overlap=false;bool FindImageFromRange(uint64_t,uint64_t){return overlap;}}m_texture_cache;
 struct Scheduler {
  unsigned waits=0,pubs=0;uint64_t tick=0;std::function<void()> change;
  void Wait(uint64_t t){++waits;tick=t;assert(writes.empty());if(change)change();}
  void WaitPriorityOperations(uint64_t t){++pubs;assert(t==tick&&writes.empty());}
 }m_scheduler;
 bool TryPublishEopLabels(uint64_t,uint64_t,ReadbackContext);
 void label(uint64_t a,uint64_t v,uint64_t n,uint64_t t){m_eop_labels.Record(a,&v,n,t);m_gpu_modified_ranges.Add(a,n);}
};
'''
post=r'''
}
int main(){
 using Libs::Graphics::BufferCache;
 using NovaRender::ReadbackCaller;
 const NovaRender::ReadbackContext fault{ReadbackCaller::HandleFaultRead,0x1000,4,true};
 const auto run=[&](BufferCache& c){return c.TryPublishEopLabels(0x1000,4,fault);};
 BufferCache c;c.label(0x1000,0x12345678,4,5);c.label(0x1008,0xabcdef0198765432ull,8,7);
 if(!NovaRender::EverProfile()){assert(!run(c)&&writes.empty()&&c.m_scheduler.waits==0);puts("NOVA_LABEL_PUBLISH_TEST: unrelated-title fallback PASS");return 0;}
 assert(run(c));assert(c.m_scheduler.waits==1&&c.m_scheduler.pubs==1&&c.m_scheduler.tick==7);
 assert(writes.size()==3&&writes[0].second==0x12345678&&writes[1].second==0x98765432&&writes[2].second==0xabcdef01);
 assert(c.m_gpu_modified_ranges.Empty()&&c.m_eop_labels.Size()==0);
 writes.clear();
 // Unknown or mixed dirty data must preserve the complete normal-readback path.
 BufferCache unknown;unknown.label(0x1000,9,4,2);unknown.m_gpu_modified_ranges.Add(0x1010,4);
 assert(!run(unknown)&&writes.empty()&&unknown.m_scheduler.waits==0&&unknown.m_gpu_modified_ranges.Contains(0x1000,4));
 BufferCache texture;texture.label(0x1000,9,4,2);texture.m_texture_cache.overlap=true;assert(!run(texture));
 // Changes during waits must not publish stale labels or discard GPU ownership.
 for(int mode=0;mode<4;++mode){
  BufferCache x;x.label(0x1000,9,4,2);
  x.m_scheduler.change=[&]{
   if(mode==0)x.m_eop_labels.Invalidate(0x1000,1);
   if(mode==1)x.label(0x1000,10,4,3);
   if(mode==2)x.m_gpu_modified_ranges.Add(0x1020,4);
   if(mode==3)x.m_texture_cache.overlap=true;
  };
  assert(!run(x)&&writes.empty()&&x.m_gpu_modified_ranges.Contains(0x1000,4));
 }
 BufferCache nofault;nofault.label(0x1000,9,4,2);
 assert(!nofault.TryPublishEopLabels(0x1000,4,{ReadbackCaller::Other,0,0,false}));
 assert(!nofault.TryPublishEopLabels(UINT64_MAX-2,4,fault));
 BufferCache unaligned;unaligned.m_gpu_modified_ranges.Add(0x1001,3);assert(!run(unaligned));
 BufferCache limit;for(unsigned i=0;i<257;++i)limit.label(0x1000+i*4,i,4,2);assert(!run(limit)&&writes.empty());
 // Two tracked pages reconcile their labels together; only actual dirty bytes change.
 BufferCache pages;pages.m_memory_tracker.pages.push_back({0x2000,4096});
 pages.label(0x1000,1,4,2);pages.label(0x2000,2,4,3);assert(run(pages));assert(writes.size()==2&&pages.m_gpu_modified_ranges.Empty());
 puts("NOVA_LABEL_PUBLISH_TEST: exact bytes, latest real tick, publications, unknown/texture fallback, mutation rejection, multiple pages and bounds PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(pre+method+post)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['c++','-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror',*flags,'-I'+str(renderer),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 for title in ['PPSA04703','PPSA31162','']:
  subprocess.run([str(p/'test')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True,timeout=20)
