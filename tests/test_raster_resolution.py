#!/usr/bin/env python3
"""Production scaler/image commands and render-pass methods on real Vulkan.
Allocation/transition harness substitutes VMA and the native image tracker.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);images=(root/'src/graphics/host_gpu/renderer/image/image.cpp').read_text()
a=images.index('bool Image::CanRasterScale(');b=images.index('Image::~Image()',a);methods=images[a:b]
ctx=(root/'src/graphics/host_gpu/renderer/context.cpp').read_text();a=ctx.index('void CommandBuffer::BeginRendering(');b=ctx.index('\n} // namespace',a);render=ctx[a:b]
rt=(root/'src/graphics/host_gpu/renderer/renderTarget.h').read_text();a=rt.index('class Image;');b=rt.index('[[nodiscard]] inline constexpr',a);structs=rt[a:b]
pre=r'''
#include <vulkan/vulkan.hpp>
#include <array>
#include <vector>
#include <algorithm>
#include <optional>
#include <cassert>
#include <bit>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#define EXIT_IF(x) do{if(x){std::fprintf(stderr,"ASSERT %s:%d: %s\n",__FILE__,__LINE__,#x);std::abort();}}while(0)
#define RENDER_COLOR_ATTACHMENTS_MAX 8
struct VulkanImage {vk::Image image{};vk::Extent3D extent{};vk::Format format{};uint32_t samples=1,layers=1;vk::DeviceMemory memory{};};
struct GraphicContext {vk::Device device{};vk::PhysicalDevice physical{};
 vk::FormatProperties GetFormatProperties(vk::Format f)const{return physical.getFormatProperties(f);}
 bool CreateImage(const vk::ImageCreateInfo& c,VulkanImage& out){
  out.image=device.createImage(c);out.extent=c.extent;out.format=c.format;out.layers=c.arrayLayers;
  auto req=device.getImageMemoryRequirements(out.image);auto props=physical.getMemoryProperties();unsigned type=0;
  while(!(req.memoryTypeBits&(1u<<type)))++type;
  out.memory=device.allocateMemory({req.size,type});device.bindImageMemory(out.image,out.memory,0);return true;
 }
 void DeleteImage(VulkanImage& i){device.destroyImage(i.image);device.freeMemory(i.memory);}
};
'''+structs+r'''
class CommandBuffer;
struct Image {
 struct Info {bool depth=false,stencil=false;bool IsDepth()const{return depth;}bool HasStencil()const{return stencil;}}info;
 VulkanImage backing;GraphicContext& m_graphics;
 struct ViewInfo {uint32_t base_level=0,base_layer=0,layer_count=1,level_count=1;vk::Format format;vk::ImageAspectFlags aspect;};
 struct Cached {vk::ImageView view;ViewInfo info;};std::vector<Cached> views;
 struct Binding {bool is_bound=false;vk::AccessFlags2 attachment_access;}binding;
 struct RasterProxy {VulkanImage backing;vk::ImageView view{};vk::ImageLayout layout=vk::ImageLayout::eUndefined;};
 std::unique_ptr<RasterProxy> raster_proxy;vk::ImageLayout native_layout=vk::ImageLayout::eUndefined;
 explicit Image(GraphicContext& c):m_graphics(c){}
 bool CanRasterScale(vk::ImageView,uint32_t,uint32_t)const;
 bool PrepareRasterScale(uint32_t,uint32_t);
 vk::ImageView BeginRasterScale(vk::ImageView,uint32_t,uint32_t,vk::ImageLayout,vk::CommandBuffer);
 void EndRasterScale(vk::ImageView,vk::ImageLayout,vk::CommandBuffer);
 void Transit(vk::ImageLayout,vk::AccessFlags2,std::optional<int>,vk::CommandBuffer);
};
class CommandBuffer {public:
 vk::CommandBuffer command{};mutable bool m_rendering=false;mutable RenderState m_render_state;
 vk::CommandBuffer Handle()const{return command;}
 void BeginRendering(const RenderState&)const;void EndRendering()const;
};
'''+methods+r'''
void Image::Transit(vk::ImageLayout layout,vk::AccessFlags2,std::optional<int>,vk::CommandBuffer c){
 RasterProxy native{backing,{},native_layout};RasterTransition(c,native,layout,RasterAspect(*this));native_layout=layout;
}
'''+render+r'''
unsigned errors=0;
VKAPI_ATTR VkBool32 VKAPI_CALL debug(VkDebugUtilsMessageSeverityFlagBitsEXT severity,VkDebugUtilsMessageTypeFlagsEXT,const VkDebugUtilsMessengerCallbackDataEXT* d,void*){
 if(severity&VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT){++errors;std::fprintf(stderr,"VULKAN_VALIDATION: %s\n",d->pMessage);}return VK_FALSE;
}
std::vector<uint32_t> spv(const char* path){std::ifstream f(path,std::ios::binary|std::ios::ate);auto size=f.tellg();assert(size>0);std::vector<uint32_t>s(size/4);f.seekg(0);f.read(reinterpret_cast<char*>(s.data()),size);return s;}
int main(int argc,char**argv){assert(argc==3);
 const char* layer="VK_LAYER_KHRONOS_validation";const char* exts[]={"VK_EXT_debug_utils","VK_EXT_validation_features"};
 vk::ApplicationInfo app("NovaRasterTest",1,"Nova",1,VK_API_VERSION_1_3);
 vk::ValidationFeatureEnableEXT feature=vk::ValidationFeatureEnableEXT::eSynchronizationValidation;
 vk::ValidationFeaturesEXT vf;vf.enabledValidationFeatureCount=1;vf.pEnabledValidationFeatures=&feature;
 vk::InstanceCreateInfo ci;ci.pApplicationInfo=&app;ci.enabledLayerCount=1;ci.ppEnabledLayerNames=&layer;ci.enabledExtensionCount=2;ci.ppEnabledExtensionNames=exts;ci.pNext=&vf;
 auto instance=vk::createInstance(ci);VkDebugUtilsMessengerCreateInfoEXT di{VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT};di.messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;di.messageType=7;di.pfnUserCallback=debug;
 VkDebugUtilsMessengerEXT messenger;auto create=reinterpret_cast<PFN_vkCreateDebugUtilsMessengerEXT>(instance.getProcAddr("vkCreateDebugUtilsMessengerEXT"));assert(create(instance,&di,nullptr,&messenger)==VK_SUCCESS);
 auto physical=instance.enumeratePhysicalDevices().at(0);auto families=physical.getQueueFamilyProperties();unsigned family=0;while(!(families[family].queueFlags&vk::QueueFlagBits::eGraphics))++family;
 float priority=1;vk::DeviceQueueCreateInfo qi({},family,1,&priority);vk::PhysicalDeviceVulkan13Features f13;f13.dynamicRendering=true;f13.synchronization2=true;vk::DeviceCreateInfo dc({},1,&qi);dc.pNext=&f13;
 auto device=physical.createDevice(dc);GraphicContext graphics{device,physical};auto queue=device.getQueue(family,0);
 auto pool=device.createCommandPool({vk::CommandPoolCreateFlagBits::eResetCommandBuffer,family});auto command=device.allocateCommandBuffers({pool,vk::CommandBufferLevel::ePrimary,1}).at(0);
 auto vs=spv(argv[1]),fs=spv(argv[2]);auto vsm=device.createShaderModule({{},vs.size()*4,vs.data()}),fsm=device.createShaderModule({{},fs.size()*4,fs.data()});
 vk::PushConstantRange push(vk::ShaderStageFlagBits::eVertex|vk::ShaderStageFlagBits::eFragment,0,128);auto layout=device.createPipelineLayout({{},0,nullptr,1,&push});
 std::array<vk::PipelineShaderStageCreateInfo,2> shaders={vk::PipelineShaderStageCreateInfo({},vk::ShaderStageFlagBits::eVertex,vsm,"main"),vk::PipelineShaderStageCreateInfo({},vk::ShaderStageFlagBits::eFragment,fsm,"main")};
 vk::PipelineVertexInputStateCreateInfo vertex;vk::PipelineInputAssemblyStateCreateInfo assembly({},vk::PrimitiveTopology::eTriangleList);
 vk::PipelineViewportStateCreateInfo vp({},1,nullptr,1,nullptr);vk::PipelineRasterizationStateCreateInfo raster({},false,false,vk::PolygonMode::eFill,vk::CullModeFlagBits::eNone,vk::FrontFace::eCounterClockwise,false,0,0,0,1);
 vk::PipelineMultisampleStateCreateInfo ms({},vk::SampleCountFlagBits::e1);vk::PipelineDepthStencilStateCreateInfo depth({},true,true,vk::CompareOp::eLess);
 std::array<vk::PipelineColorBlendAttachmentState,4> blend{};for(auto& a:blend)a.colorWriteMask=vk::ColorComponentFlagBits::eR;
 vk::PipelineColorBlendStateCreateInfo blending({},false,vk::LogicOp::eCopy,blend.size(),blend.data());vk::DynamicState dynamics[]={vk::DynamicState::eViewport,vk::DynamicState::eScissor};vk::PipelineDynamicStateCreateInfo dyn({},2,dynamics);
 std::array<vk::Format,4> formats;formats.fill(vk::Format::eR32Sfloat);vk::PipelineRenderingCreateInfo rendering({},formats.size(),formats.data(),vk::Format::eD32Sfloat);
 vk::GraphicsPipelineCreateInfo pi({},shaders.size(),shaders.data(),&vertex,&assembly,nullptr,&vp,&raster,&ms,&depth,&blending,&dyn,layout);pi.pNext=&rendering;
 auto pipeline=device.createGraphicsPipeline(nullptr,pi).value;
 constexpr unsigned W=1920,H=1080;constexpr uint64_t bytes=uint64_t(W)*H*4;
 auto read=device.createBuffer({{},5*bytes,vk::BufferUsageFlagBits::eTransferDst});auto req=device.getBufferMemoryRequirements(read);auto props=physical.getMemoryProperties();unsigned mt=0;
 while(!(req.memoryTypeBits&(1u<<mt))||!(props.memoryTypes[mt].propertyFlags&vk::MemoryPropertyFlagBits::eHostVisible)||!(props.memoryTypes[mt].propertyFlags&vk::MemoryPropertyFlagBits::eHostCoherent))++mt;
 auto memory=device.allocateMemory({req.size,mt});device.bindBufferMemory(read,memory,0);auto* data=static_cast<float*>(device.mapMemory(memory,0,VK_WHOLE_SIZE));
 for(unsigned target:{1080u,720u,540u,360u}){
  unsigned rw=target*16/9,rh=target;std::array<std::unique_ptr<Image>,5> images;
  RenderState state{};state.width=W;state.height=H;state.num_color_attachments=4;state.raster_width=target<1080?rw:0;state.raster_height=target<1080?rh:0;
  command.begin({vk::CommandBufferUsageFlagBits::eOneTimeSubmit});
  for(unsigned i=0;i<5;++i){
   images[i]=std::make_unique<Image>(graphics);auto& image=*images[i];image.info.depth=i==4;
   vk::ImageCreateInfo ic({},vk::ImageType::e2D,i==4?vk::Format::eD32Sfloat:vk::Format::eR32Sfloat,{W,H,1},1,1,vk::SampleCountFlagBits::e1,vk::ImageTiling::eOptimal,
     vk::ImageUsageFlagBits::eTransferSrc|vk::ImageUsageFlagBits::eTransferDst|(i==4?vk::ImageUsageFlagBits::eDepthStencilAttachment:vk::ImageUsageFlagBits::eColorAttachment));
   graphics.CreateImage(ic,image.backing);auto aspect=RasterAspect(image);vk::ImageSubresourceRange range(aspect,0,1,0,1);
   auto view=device.createImageView({{},image.backing.image,vk::ImageViewType::e2D,ic.format,{},range});image.views.push_back({view,{0,0,1,1,ic.format,aspect}});
   auto& a=i==4?state.depth_stencil_attachment:state.color_attachments[i];a.raster_owner=&image;a.image_view=view;a.has_depth=i==4;
   a.image_layout=i==4?vk::ImageLayout::eDepthStencilAttachmentOptimal:vk::ImageLayout::eColorAttachmentOptimal;
   image.binding.attachment_access=i==4?vk::AccessFlagBits2::eDepthStencilAttachmentRead|vk::AccessFlagBits2::eDepthStencilAttachmentWrite:vk::AccessFlagBits2::eColorAttachmentRead|vk::AccessFlagBits2::eColorAttachmentWrite;
   image.Transit(vk::ImageLayout::eTransferDstOptimal,vk::AccessFlagBits2::eTransferWrite,{},command);
   if(i==4)command.clearDepthStencilImage(image.backing.image,vk::ImageLayout::eTransferDstOptimal,{0.75f,0},range);
   else command.clearColorImage(image.backing.image,vk::ImageLayout::eTransferDstOptimal,vk::ClearColorValue(std::array<float,4>{0.125f,0,0,0}),range);
   image.Transit(a.image_layout,image.binding.attachment_access,{},command);
   assert(image.CanRasterScale(view,W,H));image.binding.is_bound=true;assert(!image.CanRasterScale(view,W,H));image.binding.is_bound=false;
   image.backing.samples=4;assert(!image.CanRasterScale(view,W,H));image.backing.samples=1;
   image.info.stencil=true;assert(!image.CanRasterScale(view,W,H));image.info.stencil=false;
  }
  CommandBuffer cb;cb.command=command;
  // Two passes exercise proxy reuse and LOAD preservation. Depth from first pass
  // prevents the second draw from replacing the first pass's colour data.
  for(unsigned pass=0;pass<2;++pass){
   state.color_attachments[0].is_clear=pass==0;
   state.color_attachments[0].clear_value[0]=std::bit_cast<uint32_t>(0.625f);
   state.depth_stencil_attachment.depth_clear=pass==0;
   state.depth_stencil_attachment.clear_value[0]=std::bit_cast<uint32_t>(0.6f);
   if(state.raster_width)for(auto& image:images)assert(image->PrepareRasterScale(rw,rh));
   cb.BeginRendering(state);command.bindPipeline(vk::PipelineBindPoint::eGraphics,pipeline);
   vk::Viewport viewport(0,0,float(rw),float(rh),0,1);vk::Rect2D scissor({int32_t(rw/4),int32_t(rh/4)},{rw/2,rh/2});command.setViewport(0,viewport);command.setScissor(0,scissor);
   const float inverse[]={float(W)/rw,float(H)/rh};command.pushConstants(layout,push.stageFlags,0,8,inverse);command.draw(3,1,0,0);cb.EndRendering();
  }
  for(unsigned i=0;i<5;++i){auto& image=*images[i];image.Transit(vk::ImageLayout::eTransferSrcOptimal,vk::AccessFlagBits2::eTransferRead,{},command);
   vk::BufferImageCopy copy(i*bytes,0,0,{RasterAspect(image),0,0,1},{0,0,0},{W,H,1});command.copyImageToBuffer(image.backing.image,vk::ImageLayout::eTransferSrcOptimal,read,copy);}
  vk::MemoryBarrier2 mb(vk::PipelineStageFlagBits2::eTransfer,vk::AccessFlagBits2::eTransferWrite,vk::PipelineStageFlagBits2::eHost,vk::AccessFlagBits2::eHostRead);vk::DependencyInfo dep({},1,&mb);command.pipelineBarrier2(dep);
  command.end();vk::SubmitInfo submit({}, {},command);queue.submit(submit);queue.waitIdle();
  unsigned x=W/2,y=H/2,index=y*W+x;const float expected_x=(float((uint64_t(x)*rw)/W)+.5f)*float(W)/rw;
  assert(std::abs(data[index]-expected_x)<0.01f);assert(std::abs(data[W*H+index]-(float((uint64_t(y)*rh)/H)+.5f)*float(H)/rh)<.01f);
  assert(data[2*W*H+index]==0.5f&&data[3*W*H+index]==1.f&&data[4*W*H+index]==0.25f);
  for(unsigned i=0;i<4;++i)assert(data[i*W*H]==(i==0?0.625f:0.125f));assert(data[4*W*H]==0.6f);
  command.reset({});for(auto& image:images){if(image->raster_proxy){device.destroyImageView(image->raster_proxy->view);graphics.DeleteImage(image->raster_proxy->backing);}device.destroyImageView(image->views[0].view);graphics.DeleteImage(image->backing);}
 }
 device.unmapMemory(memory);device.destroyBuffer(read);device.freeMemory(memory);device.destroyPipeline(pipeline);device.destroyPipelineLayout(layout);device.destroyShaderModule(vsm);device.destroyShaderModule(fsm);device.destroyCommandPool(pool);device.destroy();
 auto destroy=reinterpret_cast<PFN_vkDestroyDebugUtilsMessengerEXT>(instance.getProcAddr("vkDestroyDebugUtilsMessengerEXT"));destroy(instance,messenger,nullptr);instance.destroy();assert(errors==0);
 puts("NOVA_RASTER_VULKAN: production pass/proxy/emitter commands; native/720/540/360p, four MRTs+depth, reuse/LOAD, native readback/FragCoord, fallback checks, sync validation PASS");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(pre)
 (p/'test.vert').write_text('#version 450\nvoid main(){vec2 v=vec2((gl_VertexIndex<<1)&2,gl_VertexIndex&2);gl_Position=vec4(v*2-1,0.25,1);}\n')
 (p/'test.frag').write_text('#version 450\nlayout(push_constant) uniform Scale{vec2 inverse;}s;layout(location=0)out float a;layout(location=1)out float b;layout(location=2)out float c;layout(location=3)out float d;void main(){a=gl_FragCoord.x*s.inverse.x;b=gl_FragCoord.y*s.inverse.y;c=0.5;d=1.0;}\n')
 subprocess.run(['glslangValidator','-V',str(p/'test.vert'),'-o',str(p/'vert.spv')],check=True,stdout=subprocess.DEVNULL)
 flow=(root/'src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp').read_text()
 a=flow.index('\tif (kind == IR::StageInputKind::FragCoord || kind == IR::StageInputKind::TessCoord) {')
 b=flow.index('\n\tif (centroid || sample',a)
 emitter=('#include \"common/novaRasterScale.h\"\n'+Path(__file__).with_name('raster_coord_emitter.inc').read_text()).replace('/* PRODUCTION_COORD_BRANCH */',flow[a:b])
 (p/'emitter.cpp').write_text(emitter);(p/'common').mkdir()
 (p/'common/assert.h').write_text('#pragma once\n#include <cstdlib>\n#define EXIT_IF(x) do{if(x)std::abort();}while(0)\n')
 (p/'cmake_config.h').write_text('#define KYTY_PLATFORM 5\n#define KYTY_BUILD 2\n#define KYTY_COMPILER 1\n#define KYTY_LINKER 1\n#define KYTY_ENDIAN 2\n')
 subprocess.run(['g++','-std=c++20','-O1','-I'+str(p),'-I'+str(root/'src'),'-I'+str(root/'3rdparty/SPIRV-Headers/include'),str(p/'emitter.cpp'),str(root/'src/graphics/shader/recompiler/backend/spirv/SpirvBuilder.cpp'),'-o',str(p/'emitter')],check=True)
 subprocess.run([str(p/'emitter'),str(p/'frag.spv')],env=dict(os.environ,NOVA_CACHE_TITLE_ID='PPSA04703',NOVA_INTERNAL_RESOLUTION='540'),check=True)
 subprocess.run(['spirv-val','--target-env','vulkan1.3',str(p/'frag.spv')],check=True)
 subprocess.run(['g++','-std=c++20','-O1','-Wno-unused-variable','-I'+str(root/'src'),str(p/'test.cpp'),'-lvulkan','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'vert.spv'),str(p/'frag.spv')],check=True)
