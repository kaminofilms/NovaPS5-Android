#pragma once
#include <vulkan/vulkan.hpp>
#include <array>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <type_traits>
namespace NovaRender {
template<class H> uint64_t HandleBits(H handle){
 using Raw=typename H::CType;Raw raw=static_cast<Raw>(handle);
 if constexpr(std::is_pointer_v<Raw>)return reinterpret_cast<uintptr_t>(raw);
 else return static_cast<uint64_t>(raw);
}
// Only records binding COMMAND state. Never caches resource contents or bypasses
// ownership, resource preparation, memory dependencies or GPU completion.
class BindingCache {
 static constexpr size_t MaxVertices=32,MaxWords=1024,PushBytes=256,Stages=32;
 struct Vertex {vk::Buffer buffer{};uint64_t offset=0,size=0;bool valid=false;};
 std::array<Vertex,MaxVertices> vertices{};
 struct Descriptors {std::array<uint64_t,MaxWords> words;size_t count=0;};
 std::array<Descriptors,2> descriptors;
 struct PushStage {uint64_t layout=0;std::array<uint64_t,4> valid{};std::array<std::byte,PushBytes> bytes;};
 std::array<PushStage,Stages> push;
public:
 void Reset(){for(auto& v:vertices)v.valid=false;for(auto& d:descriptors)d.count=0;for(auto& p:push){p.layout=0;p.valid.fill(0);}}
 bool VertexNeeded(uint32_t first,uint32_t count,const vk::Buffer* buffers,const vk::DeviceSize* offsets,const vk::DeviceSize* sizes){
  if(!count||first>MaxVertices||count>MaxVertices-first||!buffers||!offsets||!sizes){for(auto& v:vertices)v.valid=false;return true;}
  bool changed=false;
  for(uint32_t i=0;i<count;++i){auto& old=vertices[first+i];changed|=!old.valid||old.buffer!=buffers[i]||old.offset!=offsets[i]||old.size!=sizes[i];}
  if(changed)for(uint32_t i=0;i<count;++i)vertices[first+i]={buffers[i],offsets[i],sizes[i],true};
  return changed;
 }
 // Set zero and zero dynamic offsets only; dynamic descriptor types fall back.
 bool DescriptorsNeeded(unsigned point,vk::PipelineLayout layout,bool pushed,std::span<const vk::WriteDescriptorSet> writes){
  if(point>=descriptors.size())return true;
  auto& old=descriptors[point];std::array<uint64_t,MaxWords> words;size_t count=0;
  const auto add=[&](uint64_t value){if(count==words.size())return false;words[count++]=value;return true;};
  const auto fail=[&](){old.count=0;return true;};
  if(!layout||writes.empty()||!add(HandleBits(layout))||!add(pushed)||!add(writes.size()))return fail();
  for(const auto& w:writes){
   if(w.pNext||!w.descriptorCount||w.descriptorCount>MaxWords/3||!add(w.dstBinding)||!add(w.dstArrayElement)||!add(uint64_t(w.descriptorType))||!add(w.descriptorCount))return fail();
   for(uint32_t i=0;i<w.descriptorCount;++i){
    switch(w.descriptorType){
    case vk::DescriptorType::eUniformBuffer:case vk::DescriptorType::eStorageBuffer:
     if(!w.pBufferInfo||!add(HandleBits(w.pBufferInfo[i].buffer))||!add(w.pBufferInfo[i].offset)||!add(w.pBufferInfo[i].range))return fail();
     break;
    case vk::DescriptorType::eSampler:case vk::DescriptorType::eCombinedImageSampler:
    case vk::DescriptorType::eSampledImage:case vk::DescriptorType::eStorageImage:case vk::DescriptorType::eInputAttachment:
     if(!w.pImageInfo||!add(HandleBits(w.pImageInfo[i].sampler))||!add(HandleBits(w.pImageInfo[i].imageView))||!add(uint64_t(w.pImageInfo[i].imageLayout)))return fail();
     break;
    case vk::DescriptorType::eUniformTexelBuffer:case vk::DescriptorType::eStorageTexelBuffer:
     if(!w.pTexelBufferView||!add(HandleBits(w.pTexelBufferView[i])))return fail();
     break;
    default:return fail();
    }
   }
  }
  if(old.count==count&&std::equal(words.begin(),words.begin()+count,old.words.begin()))return false;
  std::copy_n(words.begin(),count,old.words.begin());old.count=count;return true;
 }
 bool PushNeeded(vk::PipelineLayout layout,vk::ShaderStageFlags flags,uint32_t offset,uint32_t size,const void* data){
  const uint32_t stages=static_cast<VkShaderStageFlags>(flags);
  if(!layout||!stages||!size||!data||offset%4||size%4||offset>PushBytes||size>PushBytes-offset){for(auto& p:push){p.layout=0;p.valid.fill(0);}return true;}
  const auto* bytes=static_cast<const std::byte*>(data);const auto key=HandleBits(layout);bool changed=false;
  for(unsigned s=0;s<Stages;++s)if(stages&(uint32_t(1)<<s)){
   const auto& p=push[s];if(p.layout!=key){changed=true;continue;}
   for(uint32_t b=0;b<size;++b){size_t at=offset+b;if(!(p.valid[at/64]&(uint64_t(1)<<(at%64)))||p.bytes[at]!=bytes[b]){changed=true;break;}}
  }
  if(changed)for(unsigned s=0;s<Stages;++s)if(stages&(uint32_t(1)<<s)){
   auto& p=push[s];if(p.layout!=key){p.layout=key;p.valid.fill(0);}
   std::memcpy(p.bytes.data()+offset,data,size);
   for(size_t b=offset;b<offset+size;++b)p.valid[b/64]|=uint64_t(1)<<(b%64);
  }
  return changed;
 }
};
}
