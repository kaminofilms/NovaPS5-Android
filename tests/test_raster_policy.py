#!/usr/bin/env python3
"""Execute production per-title selector and draw eligibility with resource fixtures."""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);src=(root/'src/graphics/host_gpu/renderer/renderDraw.cpp').read_text()
a=src.index('    const auto requested=NovaRaster::Extent(');b=src.index('\n\t// Resource preparation above',a);body=src[a:b]
code=r'''
#include "common/novaRasterScale.h"
#include <array>
#include <cassert>
#include <vector>
struct Image {bool eligible=true,allocate=true;unsigned allocations=0;
 bool CanRasterScale(int,unsigned,unsigned){return eligible;}
 bool PrepareRasterScale(unsigned,unsigned){++allocations;return allocate;}};
struct Attachment{int image_view=0;Image*raster_owner=nullptr;bool has_stencil=false;};
struct RenderState{unsigned width=1920,height=1080,num_layers=1,raster_width=0,raster_height=0;std::array<Attachment,8>color_attachments;Attachment depth_stencil_attachment;};
struct Resource{bool written=false;};struct Program{bool has_address_writes=false;struct{std::vector<Resource>images;}info;};
struct Runtime{Program*program;bool buffers_written=false;};struct Stage{Runtime*runtime;};
bool HasShaderBufferWrites(const Runtime&r){return r.buffers_written;}
void Select(RenderState&rendering,std::vector<Stage*>&stages,bool feedback_aspects){
'''+body+r'''
}
int main(){
 Image color,depth;Program program;Runtime runtime{&program};Stage stage{&runtime};std::vector<Stage*>stages{&stage};
 auto make=[&]{RenderState r;r.color_attachments[0]={1,&color,false};r.depth_stencil_attachment={2,&depth,false};return r;};
 auto baseline=make();Select(baseline,stages,false);auto expected=NovaRaster::Extent(1920,1080);
 assert(baseline.raster_width==expected.first&&baseline.raster_height==expected.second);
 if(!expected.first){assert(color.allocations==0&&depth.allocations==0);return 0;}
 for(unsigned reason=0;reason<10;++reason){auto r=make();bool feedback=false;
  if(reason==0)r.num_layers=2;if(reason==1)r.depth_stencil_attachment.has_stencil=true;
  if(reason==2)feedback=true;if(reason==3)runtime.buffers_written=true;
  if(reason==4)program.has_address_writes=true;if(reason==5)program.info.images.push_back({true});
  if(reason==6)color.eligible=false;if(reason==7)depth.eligible=false;
  if(reason==8)r.color_attachments[0].raster_owner=nullptr;if(reason==9)depth.allocate=false;
  Select(r,stages,feedback);assert(r.raster_width==0&&r.raster_height==0);
  runtime.buffers_written=false;program.has_address_writes=false;program.info.images.clear();color.eligible=depth.eligible=depth.allocate=true;
 }
 auto small=make();small.width=960;small.height=540;Select(small,stages,false);assert(!small.raster_width);
 puts("Nova raster policy: atomic pass fallback for side effects/feedback/MSAA proxy rejection/stencil/layers/allocation; per-title native isolation PASS");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-O1',*flags,'-I'+str(root/'src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 for title in ['PPSA04703','PPSA15552','']:
  for height in ['0','1080','720','540','360','bad']:
   subprocess.run([str(p/'test')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title,NOVA_INTERNAL_RESOLUTION=height),check=True)

# Execute the production viewport/scissor transform, including inverted viewport height.
s=src;start=s.index('        if(rendering.raster_width){');end=start;depth=0
for i in range(s.index('{',start),len(s)):
 if s[i]=='{':depth+=1
 elif s[i]=='}':
  depth-=1
  if depth==0:end=i+1;break
math=s[start:end]
code="""
#include <cmath>
#include <cstdint>
#include <cassert>
namespace vk {struct Offset2D{int32_t x,y;};struct Extent2D{uint32_t width,height;};}
struct State{uint32_t width=1920,height=1080,raster_width=0,raster_height=0;};
struct Viewport{float x=12,y=18,width=1920,height=-1080;};
struct Scissor{vk::Offset2D offset{12,18};vk::Extent2D extent{24,30};};
void Transform(const State&rendering,Viewport&viewport,Scissor&scissor){
"""+math+"""}
int main(){
 for(unsigned h:{360u,540u,720u,1080u}){State s;s.raster_width=h==1080?0:h*16/9;s.raster_height=h;Viewport v;Scissor c;Transform(s,v,c);
  float scale=float(h)/1080;assert(std::abs(v.x-12*scale)<.001f);assert(std::abs(v.height+1080*scale)<.001f);
  assert(c.offset.x==int32_t(12*scale)&&c.offset.y==int32_t(18*scale));
  assert(c.extent.width==uint32_t(24*scale)&&c.extent.height==uint32_t(30*scale));
 }
}
"""
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-include','initializer_list',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Production raster viewport/scissor transform and native identity PASS')

# Run the production flush predicate: restore proxies before native transitions,
# while preserving batching for repeated attachment writes.
s=(root/'src/graphics/host_gpu/renderer/render.h').read_text()
a=s.index(' bool RasterScaleNeedsFlush(');b=s.index('\n }',a)+3
predicate=s[a:b]
code='''
#include <array>
#include <cassert>
namespace vk {using ImageLayout=int;using AccessFlags2=int;}
struct Image{};
struct Attachment {Image* raster_owner=nullptr;int image_layout=1,image_access=2;};
struct State {unsigned raster_width=640;std::array<Attachment,4> color_attachments{};Attachment depth_stencil_attachment;};
struct Commands {bool m_rendering=true;State m_render_state;
'''+predicate+'''
};
int main(){Image color,depth,other;Commands c;c.m_render_state.color_attachments[0].raster_owner=&color;c.m_render_state.depth_stencil_attachment.raster_owner=&depth;
 for(auto* i:{&color,&depth}){assert(!c.RasterScaleNeedsFlush(i,1,2));assert(c.RasterScaleNeedsFlush(i,3,2));assert(c.RasterScaleNeedsFlush(i,1,4));}
 assert(!c.RasterScaleNeedsFlush(&other,3,4));c.m_rendering=false;assert(!c.RasterScaleNeedsFlush(&color,3,4));c.m_rendering=true;c.m_render_state.raster_width=0;assert(!c.RasterScaleNeedsFlush(&color,3,4));
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O1',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Production raster flush predicate: batching, native transitions and inactive/native identity PASS')
