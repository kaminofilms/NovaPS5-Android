#!/usr/bin/env python3
"""Execute the production GPL linking block on lavapipe with Vulkan validation."""
from pathlib import Path
import sys,tempfile,subprocess,os
s=(Path(sys.argv[1])/'src/graphics/host_gpu/renderer/pipeline/shaders.cpp').read_text()
begin=s.index('\tbool nova_linked = false;')
end=s.index('\n\tif (graphics_debug_dump_enabled())',begin)
block=s[begin:end]
prefix=r'''
#define VULKAN_HPP_NO_EXCEPTIONS
#define VULKAN_HPP_NO_STRUCT_CONSTRUCTORS
#include <vulkan/vulkan.hpp>
#include <array>
#include <vector>
#include <string>
#include <unordered_map>
#include <fstream>
#include <cassert>
#include <cstdio>
static int errors=0;
VKAPI_ATTR VkBool32 VKAPI_CALL report(VkDebugUtilsMessageSeverityFlagBitsEXT severity,VkDebugUtilsMessageTypeFlagsEXT,const VkDebugUtilsMessengerCallbackDataEXT* d,void*) {
 if(severity&VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT){++errors;std::fprintf(stderr,"VALIDATION: %s\n",d->pMessage);}return VK_FALSE;
}
struct PipelineCache {
 struct Pipeline {vk::Pipeline pipeline;vk::PipelineLayout pipeline_layout;bool uses_push_descriptors=false;};
 using LibraryMaps=std::array<std::unordered_map<std::string,vk::Pipeline>,4>;
};
struct Graphics {vk::Device device;bool graphics_pipeline_library_enabled=true;};
struct Program {uint64_t id=0;vk::ShaderModule module;};
struct Rendering {uint32_t color_count=1;std::array<vk::Format,8> color_formats{vk::Format::eR8G8B8A8Unorm};vk::Format depth_format=vk::Format::eUndefined,stencil_format=vk::Format::eUndefined;};
struct Static {bool negative_one_to_one=false,depth_clip_enable=true,cull_front=false,cull_back=false,face=false,provoking_vtx_last=false,sample_shading_enable=false;vk::PolygonMode polygon_mode=vk::PolygonMode::eFill;uint32_t samples=1;};
void build(Graphics& graphics,PipelineCache::Pipeline& pipeline,PipelineCache::LibraryMaps& libraries,vk::ShaderModule vs,vk::ShaderModule ps,uint64_t psid,bool blend) {
 bool rect_list=false,tessellation=false,mesh=false,ps_active=true;
 vk::PipelineCache driver_cache{};vk::Result result{};
 std::vector<vk::DynamicState> dynamic_states{vk::DynamicState::eViewportWithCount,vk::DynamicState::eScissorWithCount};
 vk::PipelineDynamicStateCreateInfo dynamic_state{};dynamic_state.dynamicStateCount=dynamic_states.size();dynamic_state.pDynamicStates=dynamic_states.data();
 std::vector<vk::DescriptorSetLayoutBinding> descriptor_bindings;
 vk::ShaderStageFlags graphics_stages=vk::ShaderStageFlagBits::eVertex|vk::ShaderStageFlagBits::eFragment;
 struct {std::array<Program,3> vertex;} programs{{Program{1,vs},Program{},Program{}}};
 Program pixel_program{psid,ps};Rendering rendering;Static static_params;
 vk::PipelineInputAssemblyStateCreateInfo input_assembly{};input_assembly.topology=vk::PrimitiveTopology::eTriangleList;
 struct {uint32_t binding_count=0,attribute_count=0;} vertex_input;
 std::array<vk::VertexInputBindingDescription,32> input_desc{};std::array<vk::VertexInputAttributeDescription,32> input_attr{};
 vk::PipelineVertexInputStateCreateInfo vertex_input_info{};
 vk::PipelineViewportStateCreateInfo viewport_state{};
 vk::PipelineRasterizationStateCreateInfo rasterizer{};rasterizer.lineWidth=1;rasterizer.polygonMode=vk::PolygonMode::eFill;
 vk::PipelineMultisampleStateCreateInfo multisampling{};multisampling.rasterizationSamples=vk::SampleCountFlagBits::e1;
 vk::PipelineDepthStencilStateCreateInfo depth_stencil_info{};
 std::array<vk::PipelineColorBlendAttachmentState,8> color_blend_attachment{};
 color_blend_attachment[0].colorWriteMask=vk::ColorComponentFlags(15);
 color_blend_attachment[0].blendEnable=blend; color_blend_attachment[0].srcColorBlendFactor=vk::BlendFactor::eOne;
 color_blend_attachment[0].srcAlphaBlendFactor=vk::BlendFactor::eOne;
 vk::PipelineColorBlendStateCreateInfo color_blending{};color_blending.attachmentCount=1;color_blending.pAttachments=color_blend_attachment.data();
 vk::PipelineRenderingCreateInfo rendering_info{};rendering_info.colorAttachmentCount=1;rendering_info.pColorAttachmentFormats=rendering.color_formats.data();
 std::array<vk::PipelineShaderStageCreateInfo,2> shader_stages{};
 shader_stages[0].stage=vk::ShaderStageFlagBits::eVertex;shader_stages[0].module=vs;shader_stages[0].pName="main";
 shader_stages[1].stage=vk::ShaderStageFlagBits::eFragment;shader_stages[1].module=ps;shader_stages[1].pName="main";
 uint32_t shader_stage_count=2;
 vk::GraphicsPipelineCreateInfo pipeline_info{};
'''
suffix=r'''
 assert(nova_linked && pipeline.pipeline && result==vk::Result::eSuccess);
}
int main(int argc,char**argv){
 vk::ApplicationInfo app{};app.apiVersion=VK_API_VERSION_1_3;
 const char* layer="VK_LAYER_KHRONOS_validation";const char* ext=VK_EXT_DEBUG_UTILS_EXTENSION_NAME;
 vk::InstanceCreateInfo ci{};ci.pApplicationInfo=&app;ci.enabledLayerCount=1;ci.ppEnabledLayerNames=&layer;ci.enabledExtensionCount=1;ci.ppEnabledExtensionNames=&ext;
 vk::Instance instance;assert(vk::createInstance(&ci,nullptr,&instance)==vk::Result::eSuccess);
 VkDebugUtilsMessengerCreateInfoEXT debug{VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT};debug.messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;debug.messageType=7;debug.pfnUserCallback=report;
 VkDebugUtilsMessengerEXT messenger{};
 auto createDebug=(PFN_vkCreateDebugUtilsMessengerEXT)instance.getProcAddr("vkCreateDebugUtilsMessengerEXT");assert(createDebug((VkInstance)instance,&debug,nullptr,&messenger)==VK_SUCCESS);
 uint32_t n=0;assert(instance.enumeratePhysicalDevices(&n,nullptr)==vk::Result::eSuccess && n);std::vector<vk::PhysicalDevice> devices(n);assert(instance.enumeratePhysicalDevices(&n,devices.data())==vk::Result::eSuccess);auto physical=devices[0];
 vk::PhysicalDeviceGraphicsPipelineLibraryFeaturesEXT gpl{};vk::PhysicalDeviceVulkan13Features f13{};gpl.pNext=&f13;
 vk::PhysicalDeviceFeatures2 f2{};f2.pNext=&gpl;physical.getFeatures2(&f2);assert(gpl.graphicsPipelineLibrary && f13.dynamicRendering);
 vk::PhysicalDeviceGraphicsPipelineLibraryFeaturesEXT enabled{};enabled.graphicsPipelineLibrary=VK_TRUE;
 vk::PhysicalDeviceVulkan13Features enabled13{};enabled13.dynamicRendering=VK_TRUE;enabled.pNext=&enabled13;
 uint32_t families=0;physical.getQueueFamilyProperties(&families,nullptr);std::vector<vk::QueueFamilyProperties> q(families);physical.getQueueFamilyProperties(&families,q.data());uint32_t family=0;while(!(q[family].queueFlags&vk::QueueFlagBits::eGraphics))++family;
 float priority=1;vk::DeviceQueueCreateInfo queue{};queue.queueFamilyIndex=family;queue.queueCount=1;queue.pQueuePriorities=&priority;
 const char* exts[]={VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME,VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME};
 vk::DeviceCreateInfo dc{};dc.pNext=&enabled;dc.queueCreateInfoCount=1;dc.pQueueCreateInfos=&queue;dc.enabledExtensionCount=2;dc.ppEnabledExtensionNames=exts;
 Graphics graphics;assert(physical.createDevice(&dc,nullptr,&graphics.device)==vk::Result::eSuccess);
 auto module=[&](const char* path){std::ifstream f(path,std::ios::binary|std::ios::ate);assert(f);auto length=f.tellg();std::vector<uint32_t> words(size_t(length)/4);f.seekg(0);f.read((char*)words.data(),length);vk::ShaderModuleCreateInfo c{};c.codeSize=size_t(length);c.pCode=words.data();vk::ShaderModule m;assert(graphics.device.createShaderModule(&c,nullptr,&m)==vk::Result::eSuccess);return m;};
 auto vs=module(argv[1]),ps=module(argv[2]);
 vk::PipelineLayoutCreateInfo lc{};vk::PipelineLayout layout;assert(graphics.device.createPipelineLayout(&lc,nullptr,&layout)==vk::Result::eSuccess);
 PipelineCache::LibraryMaps libraries;
 PipelineCache::Pipeline a{},b{},c{};a.pipeline_layout=b.pipeline_layout=c.pipeline_layout=layout;
 build(graphics,a,libraries,vs,ps,2,false);for(auto& m:libraries)assert(m.size()==1);
 build(graphics,b,libraries,vs,ps,2,true);assert(libraries[0].size()==1 && libraries[1].size()==1 && libraries[2].size()==1 && libraries[3].size()==2);
 build(graphics,c,libraries,vs,ps,3,true);assert(libraries[0].size()==1 && libraries[1].size()==1 && libraries[2].size()==2 && libraries[3].size()==2);
 graphics.device.destroyPipeline(a.pipeline,nullptr);graphics.device.destroyPipeline(b.pipeline,nullptr);graphics.device.destroyPipeline(c.pipeline,nullptr);
 for(auto& m:libraries)for(auto&[key,p]:m)graphics.device.destroyPipeline(p,nullptr);
 graphics.device.destroyPipelineLayout(layout,nullptr);graphics.device.destroyShaderModule(vs,nullptr);graphics.device.destroyShaderModule(ps,nullptr);graphics.device.destroy(nullptr);
 ((PFN_vkDestroyDebugUtilsMessengerEXT)instance.getProcAddr("vkDestroyDebugUtilsMessengerEXT"))((VkInstance)instance,messenger,nullptr);instance.destroy(nullptr);
 assert(errors==0);std::puts("GPL_TEST: production linking, blend-state reuse, shader identity, Vulkan validation PASS");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(prefix+block+suffix)
 (p/'test.vert').write_text('#version 450\nvoid main(){gl_Position=vec4(float(gl_VertexIndex),0,0,1);}')
 (p/'test.frag').write_text('#version 450\nlayout(location=0) out vec4 color;void main(){color=vec4(1);}')
 for stage in ['vert','frag']:subprocess.run(['glslangValidator','-V',str(p/('test.'+stage)),'-o',str(p/(stage+'.spv'))],check=True)
 subprocess.run(['c++','-std=c++20','-O1',str(p/'test.cpp'),'-lvulkan','-o',str(p/'test')],check=True)
 env=os.environ.copy()
 icds=list(Path('/usr/share/vulkan/icd.d').glob('*lvp*.json'))
 if icds:env['VK_ICD_FILENAMES']=str(icds[0])
 subprocess.run([str(p/'test'),str(p/'vert.spv'),str(p/'frag.spv')],env=env,check=True)
