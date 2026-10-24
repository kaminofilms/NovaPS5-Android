// Exercises the exact production FSR state and shaders on a headless Vulkan device.
#include "novaUpscaler.h"
#include <cassert>
#include <atomic>
#include <iostream>
#include <cstring>
#include <vector>
VULKAN_HPP_DEFAULT_DISPATCH_LOADER_DYNAMIC_STORAGE
static std::atomic<unsigned> errors{};
static VKAPI_ATTR VkBool32 VKAPI_CALL Report(VkDebugUtilsMessageSeverityFlagBitsEXT severity,VkDebugUtilsMessageTypeFlagsEXT,const VkDebugUtilsMessengerCallbackDataEXT* m,void*){
 if(severity&VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT){++errors;std::cerr<<m->pMessage<<'\n';}return VK_FALSE;
}
static void Ok(vk::Result r){assert(r==vk::Result::eSuccess);}
static uint32_t Type(vk::PhysicalDeviceMemoryProperties m,uint32_t bits,vk::MemoryPropertyFlags flags){for(uint32_t i=0;i<m.memoryTypeCount;i++)if((bits&(1u<<i))&&(m.memoryTypes[i].propertyFlags&flags)==flags)return i;std::abort();}
struct Buffer{vk::Buffer buffer;vk::DeviceMemory memory;void* mapped;size_t bytes;};
static Buffer Allocate(vk::Device d,vk::PhysicalDeviceMemoryProperties m,size_t size,vk::BufferUsageFlags usage){
 Buffer b{};b.bytes=size;vk::BufferCreateInfo ci{};ci.size=size;ci.usage=usage;Ok(d.createBuffer(&ci,nullptr,&b.buffer));auto r=d.getBufferMemoryRequirements(b.buffer);
 vk::MemoryAllocateInfo ai{r.size,Type(m,r.memoryTypeBits,vk::MemoryPropertyFlagBits::eHostVisible|vk::MemoryPropertyFlagBits::eHostCoherent)};
 Ok(d.allocateMemory(&ai,nullptr,&b.memory));Ok(d.bindBufferMemory(b.buffer,b.memory,0));Ok(d.mapMemory(b.memory,0,VK_WHOLE_SIZE,{},&b.mapped));return b;
}
static void Free(vk::Device d,Buffer& b){d.unmapMemory(b.memory);d.destroyBuffer(b.buffer);d.freeMemory(b.memory);}
int main(){
 VULKAN_HPP_DEFAULT_DISPATCHER.init(vkGetInstanceProcAddr);
 vk::ApplicationInfo app{};app.pApplicationName="Nova FSR production validation";app.apiVersion=VK_API_VERSION_1_1;
 const char* extensions[]={VK_EXT_DEBUG_UTILS_EXTENSION_NAME,VK_EXT_VALIDATION_FEATURES_EXTENSION_NAME};const char* layers[]={"VK_LAYER_KHRONOS_validation"};
 vk::ValidationFeatureEnableEXT sync=vk::ValidationFeatureEnableEXT::eSynchronizationValidation;
 vk::ValidationFeaturesEXT vf{};vf.enabledValidationFeatureCount=1;vf.pEnabledValidationFeatures=&sync;
 vk::InstanceCreateInfo ici{};ici.pApplicationInfo=&app;ici.enabledExtensionCount=2;ici.ppEnabledExtensionNames=extensions;ici.enabledLayerCount=1;ici.ppEnabledLayerNames=layers;ici.pNext=&vf;
 vk::Instance instance;Ok(vk::createInstance(&ici,nullptr,&instance));VULKAN_HPP_DEFAULT_DISPATCHER.init(instance);
 vk::DebugUtilsMessengerCreateInfoEXT debug{};debug.messageSeverity=vk::DebugUtilsMessageSeverityFlagBitsEXT::eError;debug.messageType=vk::DebugUtilsMessageTypeFlagBitsEXT::eValidation|vk::DebugUtilsMessageTypeFlagBitsEXT::eGeneral;debug.pfnUserCallback=Report;
 vk::DebugUtilsMessengerEXT messenger;Ok(instance.createDebugUtilsMessengerEXT(&debug,nullptr,&messenger));
 uint32_t n=0;Ok(instance.enumeratePhysicalDevices(&n,nullptr));assert(n);std::vector<vk::PhysicalDevice> physical(n);Ok(instance.enumeratePhysicalDevices(&n,physical.data()));auto p=physical[0];auto memory=p.getMemoryProperties();
 const auto available=p.getFeatures();assert(available.shaderStorageImageExtendedFormats);uint32_t family=0;const auto qs=p.getQueueFamilyProperties();while(!(qs[family].queueFlags&vk::QueueFlagBits::eCompute))++family;
 float priority=1;vk::DeviceQueueCreateInfo qi{};qi.queueFamilyIndex=family;qi.queueCount=1;qi.pQueuePriorities=&priority;
 const char* extension=VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME;vk::PhysicalDeviceFeatures features{};features.shaderStorageImageExtendedFormats=VK_TRUE;
 vk::DeviceCreateInfo di{};di.queueCreateInfoCount=1;di.pQueueCreateInfos=&qi;di.enabledExtensionCount=1;di.ppEnabledExtensionNames=&extension;di.pEnabledFeatures=&features;
 vk::Device d;Ok(p.createDevice(&di,nullptr,&d));VULKAN_HPP_DEFAULT_DISPATCHER.init(d);auto queue=d.getQueue(family,0);
 vk::CommandPoolCreateInfo pi{vk::CommandPoolCreateFlagBits::eResetCommandBuffer,family};vk::CommandPool pool;Ok(d.createCommandPool(&pi,nullptr,&pool));
 vk::CommandBufferAllocateInfo cai{pool,vk::CommandBufferLevel::ePrimary,1};vk::CommandBuffer cmd;Ok(d.allocateCommandBuffers(&cai,&cmd));
 NovaUpscale::State state;
 auto run=[&](unsigned w,unsigned h,unsigned ow,unsigned oh,unsigned slot,bool srgb,bool outputSrgb,unsigned sharp,bool pattern){
  vk::ImageCreateInfo ci{};ci.imageType=vk::ImageType::e2D;ci.format=srgb?vk::Format::eR8G8B8A8Srgb:vk::Format::eR8G8B8A8Unorm;ci.extent=vk::Extent3D{w,h,1};ci.mipLevels=ci.arrayLayers=1;ci.samples=vk::SampleCountFlagBits::e1;ci.tiling=vk::ImageTiling::eOptimal;ci.usage=vk::ImageUsageFlagBits::eSampled|vk::ImageUsageFlagBits::eTransferDst;
  vk::Image input;Ok(d.createImage(&ci,nullptr,&input));auto requirements=d.getImageMemoryRequirements(input);vk::MemoryAllocateInfo ai{requirements.size,Type(memory,requirements.memoryTypeBits,vk::MemoryPropertyFlagBits::eDeviceLocal)};vk::DeviceMemory im;Ok(d.allocateMemory(&ai,nullptr,&im));Ok(d.bindImageMemory(input,im,0));
  vk::ImageViewCreateInfo vi{};vi.image=input;vi.viewType=vk::ImageViewType::e2D;vi.format=ci.format;vi.subresourceRange={vk::ImageAspectFlagBits::eColor,0,1,0,1};vk::ImageView view;Ok(d.createImageView(&vi,nullptr,&view));
  auto upload=Allocate(d,memory,w*h*4,vk::BufferUsageFlagBits::eTransferSrc);auto read=Allocate(d,memory,ow*oh*8+64,vk::BufferUsageFlagBits::eTransferDst);std::memset(read.mapped,0x6c,read.bytes);
  auto* bytes=static_cast<uint8_t*>(upload.mapped);for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){auto* c=bytes+(y*w+x)*4;if(pattern)c[0]=c[1]=c[2]=((x/3+y/3)&1)?240:15;else{c[0]=128;c[1]=64;c[2]=192;}c[3]=255;}
  assert(state.Prepare(d,memory,{ow,oh},3,slot));assert(!state.Prepare(d,memory,{ow+1,oh},3,slot));
  Ok(cmd.reset());Ok(cmd.begin(vk::CommandBufferBeginInfo{vk::CommandBufferUsageFlagBits::eOneTimeSubmit}));
  vk::ImageMemoryBarrier barrier{};barrier.oldLayout=vk::ImageLayout::eUndefined;barrier.newLayout=vk::ImageLayout::eTransferDstOptimal;barrier.dstAccessMask=vk::AccessFlagBits::eTransferWrite;barrier.image=input;barrier.srcQueueFamilyIndex=barrier.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;barrier.subresourceRange=vi.subresourceRange;
  cmd.pipelineBarrier(vk::PipelineStageFlagBits::eTopOfPipe,vk::PipelineStageFlagBits::eTransfer,{},0,nullptr,0,nullptr,1,&barrier);
  vk::BufferImageCopy copy{};copy.imageSubresource={vk::ImageAspectFlagBits::eColor,0,0,1};copy.imageExtent=ci.extent;cmd.copyBufferToImage(upload.buffer,input,vk::ImageLayout::eTransferDstOptimal,1,&copy);
  barrier.oldLayout=vk::ImageLayout::eTransferDstOptimal;barrier.newLayout=vk::ImageLayout::eShaderReadOnlyOptimal;barrier.srcAccessMask=vk::AccessFlagBits::eTransferWrite;barrier.dstAccessMask=vk::AccessFlagBits::eShaderRead;
  cmd.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,vk::PipelineStageFlagBits::eComputeShader,{},0,nullptr,0,nullptr,1,&barrier);
  auto result=state.Record(cmd,slot,view,{w,h},srgb,outputSrgb,sharp);copy.imageExtent=vk::Extent3D{ow,oh,1};cmd.copyImageToBuffer(result,vk::ImageLayout::eTransferSrcOptimal,read.buffer,1,&copy);
  vk::MemoryBarrier host{};host.srcAccessMask=vk::AccessFlagBits::eTransferWrite;host.dstAccessMask=vk::AccessFlagBits::eHostRead;cmd.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,vk::PipelineStageFlagBits::eHost,{},1,&host,0,nullptr,0,nullptr);
  Ok(cmd.end());vk::SubmitInfo submit{};submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;Ok(queue.submit(1,&submit,nullptr));Ok(queue.waitIdle());
  std::vector<float> values(ow*oh*4);const auto* raw=static_cast<const uint16_t*>(read.mapped);for(size_t i=0;i<values.size();i++){_Float16 f;std::memcpy(&f,raw+i,2);values[i]=float(f);assert(std::isfinite(values[i])&&values[i]>=0&&values[i]<=1.001f);}
  for(size_t i=ow*oh*8;i<read.bytes;i++)assert(static_cast<uint8_t*>(read.mapped)[i]==0x6c);
  if(!pattern)for(size_t i=0;i<values.size();i++){float expected=(i%4==0?128.f:i%4==1?64.f:i%4==2?192.f:255.f)/255.f;if(outputSrgb&&i%4!=3)expected=expected<=.04045f?expected/12.92f:std::pow((expected+.055f)/1.055f,2.4f);assert(std::abs(values[i]-expected)<.012f);}
  Free(d,upload);Free(d,read);d.destroyImageView(view);d.destroyImage(input);d.freeMemory(im);return values;
 };
 for(unsigned frame=0;frame<12;frame++)run(19,11,33,19,frame%3,frame&1,(frame>>1)&1,(frame%5)*25,false);
 auto a=run(19,11,33,19,0,false,false,0,true),b=run(19,11,33,19,1,false,false,100,true);double difference=0;for(size_t i=0;i<a.size();i++)difference+=std::abs(a[i]-b[i]);assert(difference>.01);
 state.Reset();run(9,7,17,13,2,false,false,25,false);Ok(d.waitIdle());state.Reset();d.destroyCommandPool(pool);d.destroy();instance.destroyDebugUtilsMessengerEXT(messenger);instance.destroy();assert(errors==0);
 std::cout<<"PASS production EASU/RCAS: constants, sRGB, sharpness, odd extents, bounds, three-slot reuse, resize and zero Vulkan synchronization errors\n";
}
