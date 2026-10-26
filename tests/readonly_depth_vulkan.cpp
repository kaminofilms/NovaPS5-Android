// SPDX-License-Identifier: GPL-2.0-or-later
// Real Vulkan clear/LOAD/STORE/readback validation, not a game-performance test.
#include <vulkan/vulkan.h>
#include "native/render/ReadOnlyDepth.h"
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <vector>
static std::atomic<unsigned> errors{0};
static VKAPI_ATTR VkBool32 VKAPI_CALL Debug(VkDebugUtilsMessageSeverityFlagBitsEXT severity,VkDebugUtilsMessageTypeFlagsEXT,const VkDebugUtilsMessengerCallbackDataEXT* d,void*){
 if(severity&VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT){++errors;std::cerr<<d->pMessage<<'\n';}return VK_FALSE;
}
#define OK(x) do{auto result=(x);if(result!=VK_SUCCESS){std::cerr<<#x<<" result="<<result<<'\n';std::abort();}}while(0)
int main(){
 VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.apiVersion=VK_API_VERSION_1_3;
 const char* layer="VK_LAYER_KHRONOS_validation";const char* extension=VK_EXT_DEBUG_UTILS_EXTENSION_NAME;
 VkValidationFeatureEnableEXT sync=VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT;
 VkValidationFeaturesEXT validation{VK_STRUCTURE_TYPE_VALIDATION_FEATURES_EXT};validation.enabledValidationFeatureCount=1;validation.pEnabledValidationFeatures=&sync;
 VkDebugUtilsMessengerCreateInfoEXT debug{VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT};
 debug.pNext=&validation;debug.messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;debug.messageType=VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT;debug.pfnUserCallback=Debug;
 VkInstanceCreateInfo ic{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ic.pApplicationInfo=&app;ic.enabledLayerCount=1;ic.ppEnabledLayerNames=&layer;ic.enabledExtensionCount=1;ic.ppEnabledExtensionNames=&extension;ic.pNext=&debug;
 VkInstance instance;OK(vkCreateInstance(&ic,nullptr,&instance));debug.pNext=nullptr;
 VkDebugUtilsMessengerEXT messenger;auto createDebug=(PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(instance,"vkCreateDebugUtilsMessengerEXT");OK(createDebug(instance,&debug,nullptr,&messenger));
 uint32_t count=0;OK(vkEnumeratePhysicalDevices(instance,&count,nullptr));assert(count);std::vector<VkPhysicalDevice> physical(count);OK(vkEnumeratePhysicalDevices(instance,&count,physical.data()));auto gpu=physical.front();
 VkPhysicalDeviceProperties props;vkGetPhysicalDeviceProperties(gpu,&props);std::cout<<"Device: "<<props.deviceName<<'\n';
 uint32_t familyCount=0;vkGetPhysicalDeviceQueueFamilyProperties(gpu,&familyCount,nullptr);std::vector<VkQueueFamilyProperties> families(familyCount);vkGetPhysicalDeviceQueueFamilyProperties(gpu,&familyCount,families.data());uint32_t family=0;while(!(families[family].queueFlags&VK_QUEUE_GRAPHICS_BIT))++family;
 float priority=1;VkDeviceQueueCreateInfo qc{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qc.queueFamilyIndex=family;qc.queueCount=1;qc.pQueuePriorities=&priority;
 VkPhysicalDeviceVulkan13Features f13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};f13.synchronization2=VK_TRUE;f13.dynamicRendering=VK_TRUE;
 VkPhysicalDeviceVulkan12Features f12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};f12.separateDepthStencilLayouts=VK_TRUE;f12.pNext=&f13;
 VkDeviceCreateInfo dc{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};dc.queueCreateInfoCount=1;dc.pQueueCreateInfos=&qc;dc.pNext=&f12;
 VkDevice device;OK(vkCreateDevice(gpu,&dc,nullptr,&device));VkQueue queue;vkGetDeviceQueue(device,family,0,&queue);
 VkPhysicalDeviceMemoryProperties memory;vkGetPhysicalDeviceMemoryProperties(gpu,&memory);
 auto allocate=[&](VkMemoryRequirements req,VkMemoryPropertyFlags flags){uint32_t type=0;for(;type<memory.memoryTypeCount;type++)if((req.memoryTypeBits&(1u<<type))&&(memory.memoryTypes[type].propertyFlags&flags)==flags)break;assert(type<memory.memoryTypeCount);VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=type;VkDeviceMemory m;OK(vkAllocateMemory(device,&ai,nullptr,&m));return m;};
 VkCommandPoolCreateInfo pc{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pc.queueFamilyIndex=family;pc.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;VkCommandPool pool;OK(vkCreateCommandPool(device,&pc,nullptr,&pool));
 VkCommandBufferAllocateInfo ca{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};ca.commandPool=pool;ca.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;ca.commandBufferCount=1;VkCommandBuffer command;OK(vkAllocateCommandBuffers(device,&ca,&command));
 constexpr unsigned side=16,pixels=side*side;constexpr auto aspects=VK_IMAGE_ASPECT_DEPTH_BIT|VK_IMAGE_ASPECT_STENCIL_BIT;
 std::vector<uint8_t> reference;
 for(bool optimized:{false,true}){
  VkImageCreateInfo ii{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};ii.imageType=VK_IMAGE_TYPE_2D;ii.format=VK_FORMAT_D32_SFLOAT_S8_UINT;ii.extent={side,side,1};ii.mipLevels=1;ii.arrayLayers=1;ii.samples=VK_SAMPLE_COUNT_1_BIT;ii.tiling=VK_IMAGE_TILING_OPTIMAL;ii.usage=VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_TRANSFER_DST_BIT;
  VkImage image;OK(vkCreateImage(device,&ii,nullptr,&image));VkMemoryRequirements req;vkGetImageMemoryRequirements(device,image,&req);auto imageMemory=allocate(req,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);OK(vkBindImageMemory(device,image,imageMemory,0));
  VkImageViewCreateInfo vi{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};vi.image=image;vi.viewType=VK_IMAGE_VIEW_TYPE_2D;vi.format=ii.format;vi.subresourceRange={aspects,0,1,0,1};VkImageView view;OK(vkCreateImageView(device,&vi,nullptr,&view));
  VkBufferCreateInfo bi{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};bi.size=pixels*5;bi.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT;VkBuffer buffer;OK(vkCreateBuffer(device,&bi,nullptr,&buffer));vkGetBufferMemoryRequirements(device,buffer,&req);auto bufferMemory=allocate(req,VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);OK(vkBindBufferMemory(device,buffer,bufferMemory,0));
  constexpr VkImageLayout layouts[]={VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_STENCIL_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_STENCIL_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_READ_ONLY_STENCIL_ATTACHMENT_OPTIMAL};
  OK(vkResetCommandBuffer(command,0));VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};OK(vkBeginCommandBuffer(command,&begin));
  VkImageLayout current=VK_IMAGE_LAYOUT_UNDEFINED;unsigned transitions=0,noneStores=0;
  auto barrier=[&](VkImageLayout next,VkPipelineStageFlags2 srcStage,VkAccessFlags2 srcAccess,VkPipelineStageFlags2 dstStage,VkAccessFlags2 dstAccess){VkImageMemoryBarrier2 b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2};b.srcStageMask=srcStage;b.srcAccessMask=srcAccess;b.dstStageMask=dstStage;b.dstAccessMask=dstAccess;b.oldLayout=current;b.newLayout=next;b.srcQueueFamilyIndex=b.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;b.image=image;b.subresourceRange=vi.subresourceRange;VkDependencyInfo dep{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};dep.imageMemoryBarrierCount=1;dep.pImageMemoryBarriers=&b;vkCmdPipelineBarrier2(command,&dep);transitions+=current!=next;current=next;};
  barrier(VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,0,0,VK_PIPELINE_STAGE_2_TRANSFER_BIT,VK_ACCESS_2_TRANSFER_WRITE_BIT);VkClearDepthStencilValue initial{.75f,7};vkCmdClearDepthStencilImage(command,image,current,&initial,1,&vi.subresourceRange);
  constexpr auto tests=VK_PIPELINE_STAGE_2_EARLY_FRAGMENT_TESTS_BIT|VK_PIPELINE_STAGE_2_LATE_FRAGMENT_TESTS_BIT;
  constexpr auto access=VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_READ_BIT|VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;
  for(unsigned n=0;n<64;n++){
   auto next=layouts[n%4];const bool clearing=n%4==0;
   const bool omit=optimized&&NovaRender::CanOmitDepthStore(props.apiVersion,false,
       clearing?aspects:VkImageAspectFlags{0},clearing,clearing);
   const auto dstAccess=omit?VkAccessFlags2(VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_READ_BIT|VK_ACCESS_2_SHADER_READ_BIT):access;
   const auto stages=tests|VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT;
   // Preserve all real dependencies; this test changes attachment stores only.
   barrier(next,n?stages:VK_PIPELINE_STAGE_2_TRANSFER_BIT,n?access:VK_ACCESS_2_TRANSFER_WRITE_BIT,stages,dstAccess);
   VkRenderingAttachmentInfo attachment{VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO};
   attachment.imageView=view;attachment.imageLayout=next;attachment.loadOp=VK_ATTACHMENT_LOAD_OP_LOAD;
   attachment.storeOp=omit?VK_ATTACHMENT_STORE_OP_NONE:VK_ATTACHMENT_STORE_OP_STORE;
   if(omit)++noneStores;
   VkRenderingInfo rendering{VK_STRUCTURE_TYPE_RENDERING_INFO};rendering.renderArea.extent={side,side};rendering.layerCount=1;
   rendering.pDepthAttachment=&attachment;rendering.pStencilAttachment=&attachment;
   vkCmdBeginRendering(command,&rendering);
   if(n%4==0){VkClearAttachment clear{};clear.aspectMask=aspects;clear.clearValue.depthStencil={.25f+float(n)/256,float(n)==0?1u:n};VkClearRect rect{{{0,0},{side,side}},0,1};vkCmdClearAttachments(command,1,&clear,1,&rect);}
   vkCmdEndRendering(command);
  }
  barrier(VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,tests,access,VK_PIPELINE_STAGE_2_TRANSFER_BIT,VK_ACCESS_2_TRANSFER_READ_BIT);
  VkBufferImageCopy copies[2]{};copies[0].imageSubresource={VK_IMAGE_ASPECT_DEPTH_BIT,0,0,1};copies[0].imageExtent={side,side,1};copies[1].bufferOffset=pixels*4;copies[1].imageSubresource={VK_IMAGE_ASPECT_STENCIL_BIT,0,0,1};copies[1].imageExtent={side,side,1};vkCmdCopyImageToBuffer(command,image,current,buffer,2,copies);
  VkBufferMemoryBarrier2 read{VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER_2};read.srcStageMask=VK_PIPELINE_STAGE_2_TRANSFER_BIT;read.srcAccessMask=VK_ACCESS_2_TRANSFER_WRITE_BIT;read.dstStageMask=VK_PIPELINE_STAGE_2_HOST_BIT;read.dstAccessMask=VK_ACCESS_2_HOST_READ_BIT;read.srcQueueFamilyIndex=read.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;read.buffer=buffer;read.size=VK_WHOLE_SIZE;VkDependencyInfo dep{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};dep.bufferMemoryBarrierCount=1;dep.pBufferMemoryBarriers=&read;vkCmdPipelineBarrier2(command,&dep);
  OK(vkEndCommandBuffer(command));VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};submit.commandBufferCount=1;submit.pCommandBuffers=&command;OK(vkQueueSubmit(queue,1,&submit,VK_NULL_HANDLE));OK(vkQueueWaitIdle(queue));
  void* mapped;OK(vkMapMemory(device,bufferMemory,0,bi.size,0,&mapped));std::vector<uint8_t> bytes((uint8_t*)mapped,(uint8_t*)mapped+bi.size);vkUnmapMemory(device,bufferMemory);
  for(unsigned n=0;n<pixels;n++){float depth;std::memcpy(&depth,bytes.data()+n*4,4);assert(std::abs(depth-(.25f+60.f/256))<1e-6f);assert(bytes[pixels*4+n]==60);}
  if(optimized)assert(bytes==reference);else reference=bytes;
  assert(noneStores==(optimized?48u:0u));
  std::cout<<(optimized?"STORE_NONE":"reference")<<" transitions="<<transitions<<" read_only_passes_using_NONE="<<noneStores<<" depth/stencil readback PASS\n";
  vkDestroyBuffer(device,buffer,nullptr);vkFreeMemory(device,bufferMemory,nullptr);vkDestroyImageView(device,view,nullptr);vkDestroyImage(device,image,nullptr);vkFreeMemory(device,imageMemory,nullptr);
 }
 vkDestroyCommandPool(device,pool,nullptr);vkDestroyDevice(device,nullptr);auto destroyDebug=(PFN_vkDestroyDebugUtilsMessengerEXT)vkGetInstanceProcAddr(instance,"vkDestroyDebugUtilsMessengerEXT");destroyDebug(instance,messenger,nullptr);vkDestroyInstance(instance,nullptr);assert(errors==0);std::cout<<"PASS zero validation errors; reference/STORE_NONE output identical (clear/LOAD replay, no shader draw or device FPS test)\n";
}
