#!/usr/bin/env python3
"""Execute production GPU label recording on Vulkan; test actual PM4 wait bodies.
The Vulkan harness substitutes allocation/tracking, not the production barriers/copy.
Existing memory-tracker/readback regressions test the cache ownership machinery.
"""
import os, pathlib, subprocess, sys, tempfile
root=pathlib.Path(sys.argv[1])
source=(root/'src/graphics/host_gpu/renderer/cache/bufferCache.cpp').read_text()
def method(text,start,end): return text[text.index(start):text.index(end,text.index(start))]
write=method(source,'void BufferCache::WriteDataBuffer(', '\nbool BufferCache::WriteEopLabel(')
label=method(source,'bool BufferCache::WriteEopLabel(', '\nvoid BufferCache::Register(')
label=label.split('\nbool BufferCache::IsEopLabelPending(',1)[0]
if '\nbool BufferCache::TryReadEopLabel(' in label:
 label=label.split('\nbool BufferCache::TryReadEopLabel(',1)[0]
gr=(root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
wait=method(gr,'template <typename T>\nvoid CommandProcessor::WaitRegMem(', '\ntemplate void CommandProcessor::WaitRegMem<uint32_t>')
predicate=method(gr,'bool TestWaitRegMemValue(', '\ntemplate <typename T>\nvoid CommandProcessor::WaitRegMem(')
# The first declaration precedes the definition. Extract the definition only.
predicate=predicate[predicate.rindex('bool TestWaitRegMemValue('):]
pre=r'''
#include "novaRenderCosts.h"
#include <cassert>
#include <cstdint>
#include <cinttypes>
#include <cstdio>
#include <stdexcept>
#define EXIT(...) throw std::runtime_error("invalid wait")
#define EXIT_IF(c) do{if(c)EXIT();}while(0)
namespace GuestMemory {template<class T>const T* Ptr(const T* p,uint64_t){return p;}}
namespace LibKernel::Memory {unsigned reads=0;uint64_t coherent=0;bool valid=true;
bool TryReadBufferBacking(uint64_t,void* dst,uint64_t n){++reads;if(!valid)return false;std::memcpy(dst,&coherent,n);return true;}}
struct CommandProcessor {unsigned suspended=0;void SuspendPm4(){++suspended;}
template<class T>void WaitRegMem(uint32_t,const T*,T,T,uint32_t,uint32_t);};
'''
post=r'''
int main(){
 for(unsigned width:{4u,8u})for(unsigned func=0;func<7;++func){
  CommandProcessor cp;uint64_t backing=0;LibKernel::Memory::coherent=5;LibKernel::Memory::reads=0;
  uint64_t observed=NovaRender::EverProfile()?5:0;
  if(width==4)cp.WaitRegMem<uint32_t>(func,reinterpret_cast<uint32_t*>(&backing),5,~0u,0,0);
  else cp.WaitRegMem<uint64_t>(func,&backing,5,~0ull,0,0);
  assert(cp.suspended==!TestWaitRegMemValue(observed,5,~0ull,func));
  assert(LibKernel::Memory::reads==unsigned(NovaRender::EverProfile()));
 }
 if(NovaRender::EverProfile()) {CommandProcessor cp;uint64_t backing=0;bool rejected=false;LibKernel::Memory::valid=false;
  try{cp.WaitRegMem<uint64_t>(3,&backing,1,~0ull,0,0);}catch(...){rejected=true;}assert(rejected && cp.suspended==0);}
 puts("NOVA_GPU_LABEL_WAIT: coherent 32/64-bit reads, seven predicates, unsatisfied suspension, profile isolation PASS");
}
'''
# Actual methods, real Vulkan allocation/commands and sync validation.
vpre=r'''
#include "novaRenderCosts.h"
#include <vulkan/vulkan.hpp>
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#define EXIT_IF(c) do{if(c)throw std::runtime_error("invalid copy");}while(0)
struct GuestRange {uint64_t a,n;bool Valid()const{return a>=0x20000 && a<0x24000 && n<=0x24000-a;}};
struct Command {vk::CommandBuffer c;vk::CommandBuffer Handle(){return c;}};
struct Scheduler {Command command;void EndRendering(){}Command& Current(){return command;}};
struct Buffer {vk::Buffer b;uint64_t a=0,n=0;vk::Buffer Handle(){return b;}uint64_t Offset(uint64_t p){return p-a;}uint64_t Size(){return n;}};
struct Staging:Buffer {char* bytes=nullptr;uint64_t cursor=0;uint64_t Copy(const void* p,uint64_t n,uint64_t align){cursor=(cursor+align-1)&~(align-1);assert(cursor+n<=Size());auto at=cursor;std::memcpy(bytes+at,p,n);cursor+=n;return at;}};
struct Textures {bool overlap=false;bool FindImageFromRange(uint64_t,uint64_t){return overlap;}};
struct BufferCache {Scheduler m_scheduler;Staging m_staging_buffer;Buffer destination;Textures m_texture_cache;unsigned obtains=0;bool dirty=false;
 std::pair<Buffer*,uint64_t> ObtainBuffer(uint64_t a,uint64_t,bool written){assert(written);dirty=true;++obtains;return {&destination,a-destination.a};}
 void WriteDataBuffer(Buffer&,uint64_t,const void*,uint64_t);bool WriteEopLabel(uint64_t,const void*,uint64_t);
};
unsigned errors=0;
VKAPI_ATTR VkBool32 VKAPI_CALL debug(VkDebugUtilsMessageSeverityFlagBitsEXT severity,VkDebugUtilsMessageTypeFlagsEXT,const VkDebugUtilsMessengerCallbackDataEXT* data,void*){if(severity&VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT){++errors;std::fprintf(stderr,"VULKAN_VALIDATION: %s\n",data->pMessage);}return VK_FALSE;}
'''
vpost=r'''
int main(){
 const char* layer="VK_LAYER_KHRONOS_validation";const char* extensions[]={"VK_EXT_debug_utils", "VK_EXT_validation_features"};
 vk::ApplicationInfo app("Nova EOP label test",1,"Nova",1,VK_API_VERSION_1_3);
 vk::ValidationFeatureEnableEXT feature=vk::ValidationFeatureEnableEXT::eSynchronizationValidation;
 vk::ValidationFeaturesEXT features;features.enabledValidationFeatureCount=1;features.pEnabledValidationFeatures=&feature;
 vk::InstanceCreateInfo info;info.pApplicationInfo=&app;info.enabledLayerCount=1;info.ppEnabledLayerNames=&layer;info.enabledExtensionCount=2;info.ppEnabledExtensionNames=extensions;info.pNext=&features;
 auto instance=vk::createInstance(info);
 VkDebugUtilsMessengerCreateInfoEXT di{VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT};di.messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;di.messageType=7;di.pfnUserCallback=debug;
 VkDebugUtilsMessengerEXT messenger;auto create=reinterpret_cast<PFN_vkCreateDebugUtilsMessengerEXT>(instance.getProcAddr("vkCreateDebugUtilsMessengerEXT"));assert(create);assert(create(instance,&di,nullptr,&messenger)==VK_SUCCESS);
 auto physical=instance.enumeratePhysicalDevices().at(0);auto families=physical.getQueueFamilyProperties();unsigned family=0;while(!(families.at(family).queueFlags&vk::QueueFlagBits::eGraphics))++family;
 float priority=1;vk::DeviceQueueCreateInfo qi({},family,1,&priority);vk::PhysicalDeviceVulkan13Features f13;f13.synchronization2=true;vk::DeviceCreateInfo device_info({},1,&qi);device_info.pNext=&f13;
 auto device=physical.createDevice(device_info);auto queue=device.getQueue(family,0);auto pool=device.createCommandPool({{},family});auto command=device.allocateCommandBuffers({pool,vk::CommandBufferLevel::ePrimary,1}).at(0);
 auto props=physical.getMemoryProperties();
 struct Allocation{vk::Buffer b;vk::DeviceMemory m;char* data;};
 auto allocate=[&](uint64_t size){auto b=device.createBuffer({{},size,vk::BufferUsageFlagBits::eTransferSrc|vk::BufferUsageFlagBits::eTransferDst,vk::SharingMode::eExclusive});auto req=device.getBufferMemoryRequirements(b);unsigned type=0;for(;type<props.memoryTypeCount;++type)if((req.memoryTypeBits&(1u<<type))&&(props.memoryTypes[type].propertyFlags&(vk::MemoryPropertyFlagBits::eHostVisible|vk::MemoryPropertyFlagBits::eHostCoherent))==(vk::MemoryPropertyFlagBits::eHostVisible|vk::MemoryPropertyFlagBits::eHostCoherent))break;assert(type<props.memoryTypeCount);auto m=device.allocateMemory({req.size,type});device.bindBufferMemory(b,m,0);return Allocation{b,m,static_cast<char*>(device.mapMemory(m,0,size))};};
 auto staging=allocate(65536),destination=allocate(16384),download=allocate(16384);
 std::memset(destination.data,0xa5,16384);std::memset(download.data,0xcc,16384);
 BufferCache cache;cache.m_scheduler.command.c=command;cache.destination={destination.b,0x20000,16384};cache.m_staging_buffer.b=staging.b;cache.m_staging_buffer.n=65536;cache.m_staging_buffer.bytes=staging.data;
 command.begin(vk::CommandBufferBeginInfo{});
 uint64_t data=0x123456789abcdef0;
 for(auto address:{0ull,0x20001ull,0x24000ull})assert(!cache.WriteEopLabel(address,&data,8));
 assert(!cache.WriteEopLabel(0x20000,&data,16));cache.m_texture_cache.overlap=true;assert(!cache.WriteEopLabel(0x20000,&data,8));cache.m_texture_cache.overlap=false;assert(cache.obtains==0);
 char expected[16384];std::memset(expected,0xa5,sizeof expected);
 for(unsigned i=0;i<512;++i){unsigned size=(i&1)?8:4;uint64_t address=0x20000+(i%128)*8;data=0xfedcba9800000000ull+i;assert(cache.WriteEopLabel(address,&data,size));std::memcpy(expected+address-0x20000,&data,size);data=0;}
 assert(cache.dirty && cache.obtains==512); // No CPU destination publication while recording.
 for(unsigned i=0;i<16384;++i)assert(static_cast<unsigned char>(destination.data[i])==0xa5);
 vk::BufferMemoryBarrier2 before;before.srcStageMask=vk::PipelineStageFlagBits2::eAllCommands;before.srcAccessMask=vk::AccessFlagBits2::eMemoryWrite;before.dstStageMask=vk::PipelineStageFlagBits2::eTransfer;before.dstAccessMask=vk::AccessFlagBits2::eTransferRead;before.srcQueueFamilyIndex=before.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;before.buffer=destination.b;before.offset=0;before.size=16384;
 vk::DependencyInfo dependency;dependency.bufferMemoryBarrierCount=1;dependency.pBufferMemoryBarriers=&before;command.pipelineBarrier2(dependency);command.copyBuffer(destination.b,download.b,vk::BufferCopy(0,0,16384));
 auto host=before;host.srcStageMask=vk::PipelineStageFlagBits2::eTransfer;host.srcAccessMask=vk::AccessFlagBits2::eTransferWrite;host.dstStageMask=vk::PipelineStageFlagBits2::eHost;host.dstAccessMask=vk::AccessFlagBits2::eHostRead;host.buffer=download.b;dependency.pBufferMemoryBarriers=&host;command.pipelineBarrier2(dependency);
 command.end();auto fence=device.createFence({});vk::SubmitInfo submit;submit.commandBufferCount=1;submit.pCommandBuffers=&command;queue.submit(submit,fence);assert(device.waitForFences(fence,true,UINT64_MAX)==vk::Result::eSuccess);assert(!std::memcmp(download.data,expected,sizeof expected));
 device.destroyFence(fence);device.destroyCommandPool(pool);for(auto a:{staging,destination,download}){device.unmapMemory(a.m);device.destroyBuffer(a.b);device.freeMemory(a.m);}device.destroy();
 auto destroy=reinterpret_cast<PFN_vkDestroyDebugUtilsMessengerEXT>(instance.getProcAddr("vkDestroyDebugUtilsMessengerEXT"));destroy(instance,messenger,nullptr);instance.destroy();assert(errors==0);
 puts("NOVA_GPU_LABEL_VULKAN: 512 production staged 32/64-bit label writes, overwrite ordering, readback, invalid/texture fallback; zero synchronization validation errors PASS");
}
'''
optimized = 'inline bool GpuLabelProfile()' in (root/'src/graphics/host_gpu/renderer/novaRenderCosts.h').read_text()
if optimized:
 post=post.replace('NovaRender::EverProfile()', 'NovaRender::GpuLabelProfile()')
 vpre=vpre.replace('#include "novaRenderCosts.h"', '#include "novaRenderCosts.h"\n#include "novaEopLabels.h"')
 vpre=vpre.replace('struct Scheduler {Command command;', 'struct Scheduler {uint64_t CurrentTick(){return 1;}Command command;')
 vpre=vpre.replace('struct BufferCache {Scheduler', 'struct BufferCache {NovaRender::EopLabels m_eop_labels;Scheduler')
 vpre=vpre.replace('uint64_t,bool written){assert(written);', 'uint64_t n,bool written){m_eop_labels.Invalidate(a,n);assert(written);')
 vpost=vpost.replace('device.destroyFence(fence);', '''
 for(unsigned i=0;i<128;++i){uint64_t address=0x20000+i*8;auto known=cache.m_eop_labels.Find(address,(i&1)?8:4);assert(known && known->tick==1);assert(!std::memcmp(known->bytes.data(),download.data+address-0x20000,known->size));}
 device.destroyFence(fence);''')
with tempfile.TemporaryDirectory() as d:
 d=pathlib.Path(d);include=root/'src/graphics/host_gpu/renderer'
 if os.environ.get('NOVA_TEST_GPU_ONLY')!='1':
  p=d/'wait.cpp';p.write_text(pre+'\n#include <cstring>\n'+predicate+wait+post)
  # cstring must precede its use in the mock backing implementation.
  p.write_text('#include <cstring>\n'+p.read_text())
  subprocess.run(['g++','-std=c++20','-O2','-I'+str(include),str(p),'-o',str(d/'wait')],check=True)
  for title in ('PPSA04703','PPSA31162','PPSA15552',''):
   subprocess.run([str(d/'wait')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True)
 p=d/'label.cpp';p.write_text(vpre+write+label+vpost)
 subprocess.run(['g++','-std=c++20','-O2','-I'+str(include),'-I'+str(root/'3rdparty/Vulkan-Headers/include'),str(p),'-Wno-missing-field-initializers','-l:libvulkan.so.1','-o',str(d/'label')],check=True)
 # CI installs lavapipe and validation layers. Local source-only check is explicit.
 if pathlib.Path('/usr/share/vulkan/icd.d').exists() or any(pathlib.Path(p).is_file() for p in os.environ.get('VK_DRIVER_FILES', os.environ.get('VK_ICD_FILENAMES','')).split(':') if p):
  subprocess.run([str(d/'label')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=os.environ.get('NOVA_TEST_LABEL_TITLE','PPSA04703')),check=True)
 elif os.environ.get('GITHUB_ACTIONS'):
  raise SystemExit('Vulkan ICD missing in required CI GPU label gate')
 else: print('NOVA_GPU_LABEL_VULKAN: compiled; execution SKIP locally (ICD/layers absent), required in CI')

