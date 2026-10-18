#!/usr/bin/env python3
"""Execute production PollCompletion against a real Vulkan timeline and buffer write."""
from pathlib import Path
import subprocess
import sys
import tempfile

root=Path(sys.argv[1])
s=(root/'src/graphics/host_gpu/renderer/commandScheduler.cpp').read_text()
poll=s[s.index('bool CommandScheduler::PollCompletion('):s.index('void CommandScheduler::PopPendingOperations(')]
pre=r'''
#include <vulkan/vulkan.h>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <thread>
#include <vector>
#define EXIT_IF(x) do{if(x)throw std::runtime_error("invalid timeline");}while(0)
void check(VkResult r,const char* call){if(r!=VK_SUCCESS){std::fprintf(stderr,"%s: VkResult=%d\n",call,int(r));throw std::runtime_error(call);}}
struct CommandScheduler {
 VkDevice device{};VkQueue queue{};VkSemaphore semaphore{};VkCommandBuffer command{};
 uint64_t current=1;unsigned submits=0;
 bool m_priority_active=false;uint64_t m_priority_active_tick=0;
 struct Op{uint64_t tick;};std::queue<Op> m_priority_operations;std::mutex m_operation_mutex;
 uint64_t CurrentTick(){return current;}
 void Flush(){
  const uint64_t tick=current++;
  VkTimelineSemaphoreSubmitInfo timeline{VK_STRUCTURE_TYPE_TIMELINE_SEMAPHORE_SUBMIT_INFO};
  timeline.signalSemaphoreValueCount=1;timeline.pSignalSemaphoreValues=&tick;
  VkSubmitInfo info{VK_STRUCTURE_TYPE_SUBMIT_INFO};info.pNext=&timeline;
  info.commandBufferCount=1;info.pCommandBuffers=&command;
  info.signalSemaphoreCount=1;info.pSignalSemaphores=&semaphore;
  check(vkQueueSubmit(queue,1,&info,VK_NULL_HANDLE),"vkQueueSubmit");++submits;
 }
 bool IsFree(uint64_t tick){uint64_t done=0;check(vkGetSemaphoreCounterValue(device,semaphore,&done),"vkGetSemaphoreCounterValue");return done>=tick;}
 bool PollCompletion(uint64_t);
};
'''
post=r'''
int main(){
 VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.apiVersion=VK_API_VERSION_1_2;
 VkInstanceCreateInfo ci{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ci.pApplicationInfo=&app;
 VkInstance instance;check(vkCreateInstance(&ci,nullptr,&instance),"vkCreateInstance");
 uint32_t n=0;check(vkEnumeratePhysicalDevices(instance,&n,nullptr),"vkEnumeratePhysicalDevices");assert(n);
 std::vector<VkPhysicalDevice> devices(n);check(vkEnumeratePhysicalDevices(instance,&n,devices.data()),"vkEnumeratePhysicalDevices");
 const auto physical=devices.front();uint32_t count=0;vkGetPhysicalDeviceQueueFamilyProperties(physical,&count,nullptr);
 std::vector<VkQueueFamilyProperties> props(count);vkGetPhysicalDeviceQueueFamilyProperties(physical,&count,props.data());
 uint32_t family=0;while(family<count&&!(props[family].queueFlags&VK_QUEUE_GRAPHICS_BIT))++family;assert(family<count);
 VkPhysicalDeviceTimelineSemaphoreFeatures timeline{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TIMELINE_SEMAPHORE_FEATURES};timeline.timelineSemaphore=VK_TRUE;
 float priority=1;VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qi.queueFamilyIndex=family;qi.queueCount=1;qi.pQueuePriorities=&priority;
 VkDeviceCreateInfo di{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};di.pNext=&timeline;di.queueCreateInfoCount=1;di.pQueueCreateInfos=&qi;
 CommandScheduler scheduler;check(vkCreateDevice(physical,&di,nullptr,&scheduler.device),"vkCreateDevice");
 vkGetDeviceQueue(scheduler.device,family,0,&scheduler.queue);
 VkSemaphoreTypeCreateInfo type{VK_STRUCTURE_TYPE_SEMAPHORE_TYPE_CREATE_INFO};type.semaphoreType=VK_SEMAPHORE_TYPE_TIMELINE;
 VkSemaphoreCreateInfo si{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};si.pNext=&type;
 check(vkCreateSemaphore(scheduler.device,&si,nullptr,&scheduler.semaphore),"vkCreateSemaphore");
 VkBufferCreateInfo bi{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};bi.size=4;bi.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT;bi.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
 VkBuffer buffer;check(vkCreateBuffer(scheduler.device,&bi,nullptr,&buffer),"vkCreateBuffer");
 VkMemoryRequirements req;vkGetBufferMemoryRequirements(scheduler.device,buffer,&req);
 VkPhysicalDeviceMemoryProperties mem;vkGetPhysicalDeviceMemoryProperties(physical,&mem);uint32_t mt=0;
 const auto wanted=VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
 while(mt<mem.memoryTypeCount&&(!(req.memoryTypeBits&(1u<<mt))||(mem.memoryTypes[mt].propertyFlags&wanted)!=wanted))++mt;assert(mt<mem.memoryTypeCount);
 VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=mt;
 VkDeviceMemory memory;check(vkAllocateMemory(scheduler.device,&ai,nullptr,&memory),"vkAllocateMemory");check(vkBindBufferMemory(scheduler.device,buffer,memory,0),"vkBindBufferMemory");
 void* mapped;check(vkMapMemory(scheduler.device,memory,0,4,0,&mapped),"vkMapMemory");*static_cast<uint32_t*>(mapped)=0;
 VkCommandPoolCreateInfo pi{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pi.queueFamilyIndex=family;
 VkCommandPool pool;check(vkCreateCommandPool(scheduler.device,&pi,nullptr,&pool),"vkCreateCommandPool");
 VkCommandBufferAllocateInfo ca{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};ca.commandPool=pool;ca.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;ca.commandBufferCount=1;
 check(vkAllocateCommandBuffers(scheduler.device,&ca,&scheduler.command),"vkAllocateCommandBuffers");
 VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};check(vkBeginCommandBuffer(scheduler.command,&begin),"vkBeginCommandBuffer");
 vkCmdFillBuffer(scheduler.command,buffer,0,4,0x12345678);
 VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};barrier.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_HOST_READ_BIT;
 vkCmdPipelineBarrier(scheduler.command,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&barrier,0,nullptr,0,nullptr);
 check(vkEndCommandBuffer(scheduler.command),"vkEndCommandBuffer");
 scheduler.m_priority_active=true;scheduler.m_priority_active_tick=1;
 assert(!scheduler.PollCompletion(1)&&scheduler.submits==1);
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(10);
 while(!scheduler.IsFree(1)){assert(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}
 assert(!scheduler.PollCompletion(1)); // actual GPU completion cannot bypass prior CPU publication
 assert(*static_cast<uint32_t*>(mapped)==0x12345678);
 scheduler.m_priority_active=false;assert(scheduler.PollCompletion(1)&&scheduler.submits==1);
 vkUnmapMemory(scheduler.device,memory);vkDestroyCommandPool(scheduler.device,pool,nullptr);
 vkDestroyBuffer(scheduler.device,buffer,nullptr);vkFreeMemory(scheduler.device,memory,nullptr);
 vkDestroySemaphore(scheduler.device,scheduler.semaphore,nullptr);vkDestroyDevice(scheduler.device,nullptr);vkDestroyInstance(instance,nullptr);
 puts("NOVA_LABEL_POLL_VULKAN: production poll, real queue submission/timeline/buffer write, prior publication gate PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);(p/'test.cpp').write_text(pre+poll+post)
    subprocess.run(['c++','-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-Wno-misleading-indentation',str(p/'test.cpp'),'-lvulkan','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,timeout=20)
