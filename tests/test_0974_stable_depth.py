#!/usr/bin/env python3
"""Exercise the depth-layout policy and actual inserted renderer decision block."""
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1];root=Path(sys.argv[1])
s=(root/'src/graphics/host_gpu/renderer/renderDraw.cpp').read_text()
start=s.index('\t\tauto layout = depth_attachment_layout(depth);')
end=s.index('\t\tif (sampled_aspects & ~DepthReadableAspects(layout)) {',start)
body=s[start:end]
assert 'image.backing.subresource_states.empty()' in body
assert 'image.binding.is_bound' in body
fixture='''#include <vulkan/vulkan.hpp>
#include "StableDepth.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cassert>
struct View {uint32_t base_level=0,base_layer=0,level_count=1,layer_count=1;vk::Format format=vk::Format::eD32SfloatS8Uint;};
struct Depth {struct {View view_info;} desc;vk::ImageLayout requested=vk::ImageLayout::eDepthStencilReadOnlyOptimal;};
struct Image {struct {struct {uint32_t levels=1,layers=1;} resources;} info;
 struct {struct {vk::ImageLayout layout=vk::ImageLayout::eDepthStencilAttachmentOptimal;} state;std::vector<int> subresource_states;} backing;
 struct {bool is_bound=false;} binding;};
namespace ImageViewOps {vk::ImageAspectFlags DepthAspectMask(vk::Format){return vk::ImageAspectFlagBits::eDepth|vk::ImageAspectFlagBits::eStencil;}}
vk::ImageLayout depth_attachment_layout(const Depth& d){return d.requested;}
vk::ImageLayout Select(Depth& depth,Image& image,vk::ImageAspectFlags sampled_aspects){
'''+body+'''return layout;}
int main(){Depth d;Image i;
 if(!std::getenv("NOVA_STABLE_DEPTH")||std::getenv("NOVA_STABLE_DEPTH")[0]!='1'){assert(Select(d,i,{})==d.requested);return 0;}
 assert(Select(d,i,{})==vk::ImageLayout::eDepthStencilAttachmentOptimal);
 assert(Select(d,i,vk::ImageAspectFlagBits::eDepth)==d.requested);
 i.binding.is_bound=true;assert(Select(d,i,{})==d.requested);i.binding.is_bound=false;
 i.backing.subresource_states.push_back(1);assert(Select(d,i,{})==d.requested);i.backing.subresource_states.clear();
 i.info.resources.layers=2;assert(Select(d,i,{})==d.requested);
}
'''
with tempfile.TemporaryDirectory() as td:
 t=Path(td);compiler=os.environ.get('CXX','c++')
 for name,source in [('policy',(repo/'tests/stable_depth_test.cpp').read_text()),('integration',fixture)]:
  cpp=t/(name+'.cpp');cpp.write_text(source);exe=t/name
  subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'3rdparty/Vulkan-Headers/include'),'-I',str(repo/'native/render'),str(cpp),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',NOVA_STABLE_DEPTH='1'))
 if name=='integration':subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',NOVA_STABLE_DEPTH='0'))
print('PASS actual inserted depth decision: sampled, bound, whole-range and subresource guards')

if os.environ.get('NOVA_TEST_VULKAN')=='1':
 with tempfile.TemporaryDirectory() as td:
  exe=Path(td)/'depth-vulkan'
  subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(root/'3rdparty/Vulkan-Headers/include'),'-I',str(repo/'native/render'),str(repo/'tests/stable_depth_vulkan.cpp'),'-l:libvulkan.so.1','-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
