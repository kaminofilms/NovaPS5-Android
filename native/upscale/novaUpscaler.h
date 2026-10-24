// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <vulkan/vulkan.hpp>
#include <array>
#include <vector>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <algorithm>
#include "fsr_shaders.h"
namespace NovaUpscale {
// A scratch pair per acquired swapchain image. The caller waits at ALL_COMMANDS
// on the acquire semaphore and calls Reset only after its presentation queue is idle.
class State {
    struct Image { vk::Image image{}; vk::DeviceMemory memory{}; vk::ImageView view{};
                   vk::ImageLayout layout=vk::ImageLayout::eUndefined; };
    struct Slot { Image easu,rcas; };
    vk::Device device{};
    vk::PhysicalDeviceMemoryProperties memory{};
    vk::Extent2D extent{};
    std::vector<Slot> slots;
    vk::DescriptorSetLayout descriptors{};
    vk::PipelineLayout layout{};
    vk::Pipeline easu{},rcas{};
    vk::Sampler sampler{};
    bool failed=false;
    static uint32_t Bits(float f){uint32_t u;std::memcpy(&u,&f,4);return u;}
    void Delete(Image& i){if(i.view)device.destroyImageView(i.view);if(i.image)device.destroyImage(i.image);if(i.memory)device.freeMemory(i.memory);i={};}
    bool Allocate(Image& i) {
        vk::ImageCreateInfo ci{};ci.imageType=vk::ImageType::e2D;ci.format=vk::Format::eR16G16B16A16Sfloat;
        ci.extent=vk::Extent3D{extent.width,extent.height,1};ci.mipLevels=1;ci.arrayLayers=1;ci.samples=vk::SampleCountFlagBits::e1;
        ci.tiling=vk::ImageTiling::eOptimal;
        ci.usage=vk::ImageUsageFlagBits::eStorage|vk::ImageUsageFlagBits::eSampled|vk::ImageUsageFlagBits::eTransferSrc;
        if(device.createImage(&ci,nullptr,&i.image)!=vk::Result::eSuccess)return false;
        auto requirements=device.getImageMemoryRequirements(i.image);uint32_t type=UINT32_MAX;
        for(uint32_t n=0;n<memory.memoryTypeCount;n++)if((requirements.memoryTypeBits&(1u<<n))&&
          (memory.memoryTypes[n].propertyFlags&vk::MemoryPropertyFlagBits::eDeviceLocal)){type=n;break;}
        if(type==UINT32_MAX)return false;
        vk::MemoryAllocateInfo ai{};ai.allocationSize=requirements.size;ai.memoryTypeIndex=type;
        if(device.allocateMemory(&ai,nullptr,&i.memory)!=vk::Result::eSuccess)return false;
        if(VULKAN_HPP_DEFAULT_DISPATCHER.vkBindImageMemory(VkDevice(device),VkImage(i.image),VkDeviceMemory(i.memory),0)!=VK_SUCCESS)return false;
        vk::ImageViewCreateInfo vi{};vi.image=i.image;vi.viewType=vk::ImageViewType::e2D;vi.format=ci.format;
        vi.subresourceRange={vk::ImageAspectFlagBits::eColor,0,1,0,1};
        return device.createImageView(&vi,nullptr,&i.view)==vk::Result::eSuccess;
    }
    bool Pipeline(const uint32_t* code,size_t bytes,vk::Pipeline& pipeline){
        vk::ShaderModuleCreateInfo mi{};mi.codeSize=bytes;mi.pCode=code;vk::ShaderModule module{};
        if(device.createShaderModule(&mi,nullptr,&module)!=vk::Result::eSuccess)return false;
        vk::ComputePipelineCreateInfo ci{};ci.layout=layout;ci.stage.stage=vk::ShaderStageFlagBits::eCompute;
        ci.stage.module=module;ci.stage.pName="main";
        const auto result=device.createComputePipelines(nullptr,1,&ci,nullptr,&pipeline);
        device.destroyShaderModule(module);return result==vk::Result::eSuccess;
    }
    bool Initialize(){
        const std::array bindings={vk::DescriptorSetLayoutBinding{0,vk::DescriptorType::eCombinedImageSampler,1,vk::ShaderStageFlagBits::eCompute},
                                  vk::DescriptorSetLayoutBinding{1,vk::DescriptorType::eStorageImage,1,vk::ShaderStageFlagBits::eCompute}};
        vk::DescriptorSetLayoutCreateInfo di{};di.flags=vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR;
        di.bindingCount=2;di.pBindings=bindings.data();
        if(device.createDescriptorSetLayout(&di,nullptr,&descriptors)!=vk::Result::eSuccess)return false;
        vk::PushConstantRange range{vk::ShaderStageFlagBits::eCompute,0,80};vk::PipelineLayoutCreateInfo li{};
        li.setLayoutCount=1;li.pSetLayouts=&descriptors;li.pushConstantRangeCount=1;li.pPushConstantRanges=&range;
        if(device.createPipelineLayout(&li,nullptr,&layout)!=vk::Result::eSuccess)return false;
        vk::SamplerCreateInfo si{};si.minFilter=si.magFilter=vk::Filter::eNearest;
        si.addressModeU=si.addressModeV=si.addressModeW=vk::SamplerAddressMode::eClampToEdge;
        if(device.createSampler(&si,nullptr,&sampler)!=vk::Result::eSuccess)return false;
        return Pipeline(easuShader,sizeof(easuShader),easu)&&Pipeline(rcasShader,sizeof(rcasShader),rcas);
    }
    static void Transition(vk::CommandBuffer cmd,Image& i,vk::ImageLayout next,vk::AccessFlags access,vk::PipelineStageFlags stage){
        vk::ImageMemoryBarrier b{};b.oldLayout=i.layout;b.newLayout=next;
        b.srcAccessMask=i.layout==vk::ImageLayout::eUndefined?vk::AccessFlags{}:vk::AccessFlagBits::eMemoryRead|vk::AccessFlagBits::eMemoryWrite;
        b.dstAccessMask=access;b.image=i.image;b.srcQueueFamilyIndex=b.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;
        b.subresourceRange={vk::ImageAspectFlagBits::eColor,0,1,0,1};
        cmd.pipelineBarrier(i.layout==vk::ImageLayout::eUndefined?vk::PipelineStageFlagBits::eTopOfPipe:vk::PipelineStageFlagBits::eAllCommands,
                            stage,{},0,nullptr,0,nullptr,1,&b);i.layout=next;
    }
    void Dispatch(vk::CommandBuffer cmd,vk::Pipeline pipeline,vk::ImageView input,Image& output,const uint32_t* constants){
        Transition(cmd,output,vk::ImageLayout::eGeneral,vk::AccessFlagBits::eShaderWrite,vk::PipelineStageFlagBits::eComputeShader);
        const std::array images={vk::DescriptorImageInfo{sampler,input,vk::ImageLayout::eShaderReadOnlyOptimal},
                                 vk::DescriptorImageInfo{nullptr,output.view,vk::ImageLayout::eGeneral}};
        std::array<vk::WriteDescriptorSet,2> writes{};
        for(uint32_t n=0;n<2;n++){writes[n].dstBinding=n;writes[n].descriptorCount=1;writes[n].pImageInfo=&images[n];
          writes[n].descriptorType=n?vk::DescriptorType::eStorageImage:vk::DescriptorType::eCombinedImageSampler;}
        cmd.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute,layout,0,2,writes.data());
        cmd.pushConstants(layout,vk::ShaderStageFlagBits::eCompute,0,80,constants);
        cmd.bindPipeline(vk::PipelineBindPoint::eCompute,pipeline);
        cmd.dispatch((extent.width+7)/8,(extent.height+7)/8,1);
    }
public:
    State()=default;State(const State&)=delete;State& operator=(const State&)=delete;
    ~State(){Reset();}
    void Reset(){
        if(device){for(auto& s:slots){Delete(s.easu);Delete(s.rcas);}device.destroyPipeline(easu);device.destroyPipeline(rcas);
          device.destroyPipelineLayout(layout);device.destroyDescriptorSetLayout(descriptors);device.destroySampler(sampler);}
        slots.clear();device=nullptr;extent=vk::Extent2D{};descriptors=nullptr;layout=nullptr;easu=nullptr;rcas=nullptr;sampler=nullptr;failed=false;
    }
    // Allocate before recording any work. Failure leaves the normal blit path usable.
    bool Prepare(vk::Device d,const vk::PhysicalDeviceMemoryProperties& props,vk::Extent2D output,uint32_t count,uint32_t slot){
        if(failed||slot>=count||!count||!output.width||!output.height)return false;
        if(!device){device=d;memory=props;extent=output;slots.resize(count);if(!Initialize()){failed=true;return false;}}
        if(d!=device||output!=extent||count!=slots.size())return false;
        auto& s=slots[slot];
        if(!s.easu.image){if(!Allocate(s.easu)||!Allocate(s.rcas)){Delete(s.easu);Delete(s.rcas);failed=true;return false;}}
        return true;
    }
    vk::Image Record(vk::CommandBuffer cmd,uint32_t slot,vk::ImageView input,vk::Extent2D source,bool inputSrgb,bool outputSrgb,unsigned sharpness){
        auto& s=slots.at(slot);std::array<uint32_t,20> con{};
        // AMD FsrEasuCon: viewport equals the entire prepared input resource.
        const float iw=float(source.width),ih=float(source.height),ow=float(extent.width),oh=float(extent.height);
        con[0]=Bits(iw/ow);con[1]=Bits(ih/oh);con[2]=Bits(.5f*iw/ow-.5f);con[3]=Bits(.5f*ih/oh-.5f);
        con[4]=Bits(1/iw);con[5]=Bits(1/ih);con[6]=Bits(1/iw);con[7]=Bits(-1/ih);
        con[8]=Bits(-1/iw);con[9]=Bits(2/ih);con[10]=Bits(1/iw);con[11]=Bits(2/ih);con[12]=Bits(0);con[13]=Bits(4/ih);
        con[16]=inputSrgb;Dispatch(cmd,easu,input,s.easu,con.data());
        Transition(cmd,s.easu,vk::ImageLayout::eShaderReadOnlyOptimal,vk::AccessFlagBits::eShaderRead,vk::PipelineStageFlagBits::eComputeShader);
        con={};const auto amount=std::min(sharpness,100u);
        con[0]=Bits(std::exp2(-2.f*(1.f-float(amount)/100.f)));con[17]=outputSrgb;con[18]=amount!=0;
        Dispatch(cmd,rcas,s.easu.view,s.rcas,con.data());
        Transition(cmd,s.rcas,vk::ImageLayout::eTransferSrcOptimal,vk::AccessFlagBits::eTransferRead,vk::PipelineStageFlagBits::eTransfer);
        return s.rcas.image;
    }
};
}
