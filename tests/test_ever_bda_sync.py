#!/usr/bin/env python3
"""Focused upstream dirtiness/concurrent-drain tests against production tracker.
The OS protection callback comes from upstream's harness; no GPU FPS claim.
"""
from pathlib import Path
import os, subprocess, sys, tempfile
root=Path(sys.argv[1]); repo=Path(__file__).resolve().parents[1]
s=(repo/'tests/upstream_MemoryTrackerTests.cpp').read_text()
sync=(root/'src/graphics/host_gpu/renderer/cache/bufferCache.cpp').read_text()
a=sync.index('void BufferCache::SynchronizeBda(')
b=sync.index('void BufferCache::SynchronizeBuffersInRange(',a)
selection=sync[a:b]
selection=selection.replace('void BufferCache::SynchronizeBda(', 'void SyncProbe::SynchronizeBda(')
probe='''namespace Libs::Graphics {
class SyncProbe { public:
 explicit SyncProbe(MemoryTracker& t):m_memory_tracker(t){}
 void SynchronizeBda(const RangeSet& mapped);
 void SynchronizeBuffersInRange(uint64_t start,uint64_t size){calls.emplace_back(start,size);}
 MemoryTracker& m_memory_tracker;
 std::vector<std::pair<uint64_t,uint64_t>> calls;
};
'''+selection+'''}
void TestSelection(){
 constexpr uint64_t base=0x200000000ull,page=Libs::Graphics::TRACKER_PAGE_SIZE;
 TrackerHarness h; Libs::Graphics::RangeSet mapped;Libs::Graphics::SyncProbe probe(h.tracker);
 mapped.Add(base,page);mapped.Add(base+2*page,page);
 h.tracker.QueueBdaSync(base,3*page);probe.SynchronizeBda(mapped);
 Check(probe.calls==std::vector<std::pair<uint64_t,uint64_t>>{{base,page},{base+2*page,page}},"mapped holes or changed-range intersection wrong");
 probe.calls.clear();probe.SynchronizeBda(mapped);Check(probe.calls.empty(),"clean drain rescanned mappings");
 mapped.Add(base+page,page);h.tracker.QueueBdaSync(base+page,1);probe.SynchronizeBda(mapped);
 Check(probe.calls==std::vector<std::pair<uint64_t,uint64_t>>{{base+page,page}},"new mapping not queued exactly once");
}
'''
s=s[:s.index('int main(int argc, char **argv) {')]+probe+'''int main(){
 if(std::string(std::getenv("NOVA_CACHE_TITLE_ID"))!="PPSA04703" || (std::getenv("NOVA_EVER_BDA_SYNC")&&std::string(std::getenv("NOVA_EVER_BDA_SYNC"))=="0")) {
   TrackerHarness h;h.tracker.QueueBdaSync(0x200000000ull,4096);Check(h.tracker.TakeBdaSync().Empty(),"optimization escaped title/override gate");return 0;
 }
 TestSelection();
  TestBdaSyncDirtiness();
  TestBdaSyncConcurrentDrain();
  std::puts("Ever BDA: production ownership transitions and concurrent drains passed");
}
'''
# ASAN reserves the PS5-like 8-GiB virtual range for shadow memory. The
# focused tracker tests need valid tracked pages, not that particular base.
if os.getenv('SANITIZE')=='1':
 s=s.replace('first_base = 0x0000000200000000ull', 'first_base = 0x0000000010000000ull')
 s=s.replace('stride = 0x0000000100000000ull', 'stride = 0x0000000001000000ull')
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'common').mkdir()
 (p/'common/assert.h').write_text('''#pragma once
#include "common/common.h"
#include <cstdio>
#include <cstdlib>
#define EXIT_IF(x) do {if(x){std::fprintf(stderr,"EXIT_IF %s\\n",#x);std::abort();}}while(0)
#define EXIT(...) do {std::fprintf(stderr,__VA_ARGS__);std::abort();}while(0)
#define EXIT_NOT_IMPLEMENTED(x) EXIT_IF(x)
''')
 (p/'cmake_config.h').write_text('#define KYTY_PLATFORM 5\n#define KYTY_BUILD 2\n#define KYTY_COMPILER 1\n#define KYTY_LINKER 1\n#define KYTY_ENDIAN 2\n')
 (p/'test.cpp').write_text(s)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-O1','-g','-ffunction-sections','-fdata-sections',*flags,'-I',str(p),'-I',str(root/'src'),str(p/'test.cpp'),str(root/'src/graphics/host_gpu/memoryTracker.cpp'),str(root/'src/graphics/host_gpu/pageManager.cpp'),'-Wl,--gc-sections','-pthread','-o',str(p/'test')],check=True)
 for title,override in [('PPSA04703','1'),('PPSA15552','1'),('PPSA04703','0')]:
  subprocess.run([str(p/'test')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title,NOVA_EVER_BDA_SYNC=override),check=True)
