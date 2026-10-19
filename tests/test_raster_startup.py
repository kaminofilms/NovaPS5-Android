#!/usr/bin/env python3
"""Execute the full production Image::Transit with inactive/startup scheduler state."""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);s=(root/'src/graphics/host_gpu/renderer/image/image.cpp').read_text()
a=s.index('void Image::Transit(');b=s.index('\nvoid Image::Upload(',a);body=s[a:b]
pre=r'''
#include "common/novaRasterScale.h"
#include <cassert>
#include <cstdint>
#include <optional>
#include <vector>
namespace vk {
using AccessFlags2=uint64_t;using PipelineStageFlags2=uint64_t;using ImageLayout=int;
struct AccessFlagBits2 {static constexpr uint64_t eTransferRead=1,eTransferWrite=2;};
struct PipelineStageFlagBits2 {static constexpr uint64_t eTransfer=1,eAllGraphics=2,eComputeShader=4;};
struct DependencyInfo {uint32_t imageMemoryBarrierCount;const int* pImageMemoryBarriers;};
struct CommandBuffer {static inline unsigned barriers=0;void pipelineBarrier2(const DependencyInfo&i){assert(i.imageMemoryBarrierCount==1);++barriers;}};
}
using ImageSubresourceRange=int;
struct Image {
 struct Scheduler {
  bool active=false,flush=false;unsigned current=0,ends=0;bool Active(){return active;}
  Scheduler& Current(){assert(active);++current;return *this;}
  bool RasterScaleNeedsFlush(Image*,int,uint64_t){return flush;}
  void EndRendering(){++ends;flush=false;}
 }m_scheduler;
 bool check_preflush=false;bool empty=false;
 std::vector<int> GetBarriers(int,uint64_t,uint64_t,std::optional<int>){if(check_preflush)assert(!m_scheduler.flush);return empty?std::vector<int>{}:std::vector<int>{1};}
 void Transit(int,uint64_t,std::optional<int>,vk::CommandBuffer);
};
'''
post=r'''
int main(){
 Image i;vk::CommandBuffer command;
 // The startup/inactive case previously aborted at Current() even when scaling
 // was disabled. Explicit external command buffers must remain usable.
 i.Transit(1,1,{},command);assert(i.m_scheduler.current==0&&command.barriers==1);
 i.m_scheduler.active=true;i.m_scheduler.flush=true;i.check_preflush=NovaRaster::Enabled();
 i.Transit(1,2,{},command);
 assert(i.m_scheduler.current==unsigned(NovaRaster::Enabled()));
 assert(command.barriers==2);
 Image empty;empty.empty=true;empty.Transit(1,1,{},command);assert(empty.m_scheduler.current==0&&command.barriers==2);
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(pre+body+post)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-O1',*flags,'-I'+str(root/'src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 for title in ['PPSA04703','PPSA15552','']:
  for h in ['0','1080','720','540','360']:
   subprocess.run([str(p/'test')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title,NOVA_INTERNAL_RESOLUTION=h),check=True)
print('RASTER_STARTUP: production Image::Transit, inactive/active scheduler, native/all scales, empty transitions and preflush ordering PASS')
