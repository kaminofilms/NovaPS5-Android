#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys, tempfile
repo = Path(__file__).resolve().parents[1]
core = Path(sys.argv[1])
s = (core / 'src/graphics/host_gpu/renderer/cache/bufferCache.cpp').read_text()
body = s[s.index('bool BufferCache::SynchronizeBuffer('):s.index('vk::Buffer BufferCache::UploadCopies(')]
# Compile the actual inserted barrier assignments with the pinned Vulkan types.
a = body.index('\t\tconst auto upload_range')
b = body.index('\n\t\tnative.pipelineBarrier', a)
assignments = body[a:b]
source = r'''
#include "native/render/UploadRange.h"
#include <vulkan/vulkan.hpp>
#include <cassert>
#include <vector>
#include <random>
struct Buffer { uint64_t Size() const { return 1024*1024; } };
int main() {
 Buffer buffer;
 std::vector<vk::BufferCopy> copies{{0,4096,4096}};
 vk::BufferMemoryBarrier before{};
''' + assignments + r'''
 assert(before.offset == 4096 && before.size == 4096);
 copies = {{0,900,100},{0,100,200}};
 auto r = NovaRender::UploadDestinationRange(copies, 1024);
 assert(r.offset == 100 && r.size == 900);
 for (auto bad: std::vector<vk::BufferCopy>{{0,UINT64_MAX-2,8},{0,1024,1},{0,0,0}}) {
   copies = {bad}; r=NovaRender::UploadDestinationRange(copies,1024);
   assert(r.offset==0 && r.size==1024);
 }
 copies.clear(); r=NovaRender::UploadDestinationRange(copies,1024);
 assert(r.offset==0 && r.size==1024);
 std::mt19937 rng(74);
 for(int trial=0;trial<10000;++trial) {
   copies.clear();
   for(int j=0;j<16;++j) {
     uint64_t off=rng()%1024, len=1+rng()%(1024-off);
     copies.emplace_back(0,off,len);
   }
   r=NovaRender::UploadDestinationRange(copies,1024);
   assert(r.offset < 1024 && r.size <= 1024-r.offset);
   for(auto c:copies) assert(r.offset<=c.dstOffset && r.offset+r.size>=c.dstOffset+c.size);
 }
}
'''
assert 'auto after          = before;' in body
assert 'command.EndRendering();' in body
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'test.cpp'; p.write_text(source)
    binary=Path(d)/'test'
    subprocess.run(['c++','-std=c++20','-fsanitize=undefined','-I'+str(repo),'-I'+str(core/'3rdparty/Vulkan-Headers/include'),str(p),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('Upload ranges: actual assignments + 10,000 randomized coverage cases passed; stages/accesses preserved')
