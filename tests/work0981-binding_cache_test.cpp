#include "native/render/BindingCache.h"
#include <cassert>
#include <random>
#include <vector>
using NovaRender::BindingCache;
template<class H> H handle(uintptr_t id){using Raw=typename H::CType;if constexpr(std::is_pointer_v<Raw>)return H(reinterpret_cast<Raw>(id));else return H(static_cast<Raw>(id));}
int main(){
 BindingCache cache;cache.Reset();auto layout=handle<vk::PipelineLayout>(1),other=handle<vk::PipelineLayout>(2);
 vk::Buffer buffers[]={handle<vk::Buffer>(11),handle<vk::Buffer>(12)};vk::DeviceSize offsets[]={0,256},sizes[]={128,256};
 assert(cache.VertexNeeded(0,2,buffers,offsets,sizes));assert(!cache.VertexNeeded(0,2,buffers,offsets,sizes));
 offsets[0]=16;assert(cache.VertexNeeded(0,2,buffers,offsets,sizes));assert(!cache.VertexNeeded(0,1,buffers,offsets,sizes));
 sizes[1]=512;assert(cache.VertexNeeded(0,2,buffers,offsets,sizes));
 cache.Reset();assert(cache.VertexNeeded(0,2,buffers,offsets,sizes));
 vk::DescriptorBufferInfo info{buffers[0],16,128};vk::WriteDescriptorSet write{};write.dstBinding=3;write.descriptorType=vk::DescriptorType::eUniformBuffer;write.descriptorCount=1;write.pBufferInfo=&info;
 auto writes=std::span(&write,1);
 assert(cache.DescriptorsNeeded(0,layout,false,writes));assert(!cache.DescriptorsNeeded(0,layout,false,writes));
 auto moved=info;write.pBufferInfo=&moved;assert(!cache.DescriptorsNeeded(0,layout,false,writes)); // addresses are not identity
 moved.offset=32;assert(cache.DescriptorsNeeded(0,layout,false,writes));
 assert(cache.DescriptorsNeeded(1,layout,false,writes));assert(!cache.DescriptorsNeeded(0,layout,false,writes));
 assert(cache.DescriptorsNeeded(0,other,false,writes));assert(cache.DescriptorsNeeded(0,layout,true,writes));
 write.pNext=&info;assert(cache.DescriptorsNeeded(0,layout,true,writes));write.pNext=nullptr;assert(cache.DescriptorsNeeded(0,layout,true,writes));
 vk::DescriptorImageInfo image{handle<vk::Sampler>(7),handle<vk::ImageView>(8),vk::ImageLayout::eShaderReadOnlyOptimal};
 write.pBufferInfo=nullptr;write.pImageInfo=&image;write.descriptorType=vk::DescriptorType::eCombinedImageSampler;
 assert(cache.DescriptorsNeeded(0,layout,true,writes));assert(!cache.DescriptorsNeeded(0,layout,true,writes));
 image.imageLayout=vk::ImageLayout::eGeneral;assert(cache.DescriptorsNeeded(0,layout,true,writes));
 image.imageView=handle<vk::ImageView>(9);assert(cache.DescriptorsNeeded(0,layout,true,writes));
 write.descriptorCount=UINT32_MAX;assert(cache.DescriptorsNeeded(0,layout,true,writes));write.descriptorCount=1;assert(cache.DescriptorsNeeded(0,layout,true,writes));
 std::array<uint32_t,4> values{1,2,3,4};auto vertex=vk::ShaderStageFlagBits::eVertex,fragment=vk::ShaderStageFlagBits::eFragment;
 assert(cache.PushNeeded(layout,vertex,0,16,values.data()));assert(!cache.PushNeeded(layout,vertex,0,16,values.data()));
 assert(cache.PushNeeded(layout,fragment,0,16,values.data()));
 values[1]=99;assert(cache.PushNeeded(layout,fragment,4,4,&values[1]));
 values[1]=2;assert(!cache.PushNeeded(layout,vertex,0,16,values.data()));
 assert(cache.PushNeeded(other,vertex,0,16,values.data()));assert(cache.PushNeeded(layout,vertex,0,16,values.data()));
 assert(cache.PushNeeded(layout,vertex,256,4,values.data()));assert(cache.PushNeeded(layout,vertex,0,16,values.data()));
 // Differential byte-state oracle across overlapping partial writes and stage masks.
 cache.Reset();std::array<std::array<unsigned char,256>,2> gpu{},reference{};std::mt19937 rng(981);
 std::array<std::array<bool,256>,2> valid{};
 unsigned emitted=0,skipped=0;
 for(int i=0;i<10000;++i){unsigned off=4*(rng()%60),n=4*(1+rng()%4);unsigned stages=1+rng()%3;std::array<unsigned char,16> payload{};for(unsigned b=0;b<n;++b)payload[b]=rng()%4;
  vk::ShaderStageFlags flags{};if(stages&1)flags|=vertex;if(stages&2)flags|=fragment;
  bool issue=cache.PushNeeded(layout,flags,off,n,payload.data());if(issue)++emitted;else ++skipped;
  for(unsigned s=0;s<2;++s)if(stages&(1<<s))for(unsigned b=0;b<n;++b){reference[s][off+b]=payload[b];valid[s][off+b]=true;if(issue)gpu[s][off+b]=payload[b];}
  for(unsigned s=0;s<2;++s)for(unsigned b=0;b<256;++b)if(valid[s][b])assert(gpu[s][b]==reference[s][b]);
  if((i%8)==0){assert(!cache.PushNeeded(layout,flags,off,n,payload.data()));++skipped;}
 }
 assert(emitted>0&&skipped>0);cache.Reset();assert(cache.PushNeeded(layout,vertex,0,16,values.data()));
}
