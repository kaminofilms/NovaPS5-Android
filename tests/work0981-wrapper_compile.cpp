#include "native/render/BindingCache.h"
struct CommandBuffer {
 NovaRender::BindingCache m_nova_bindings;
 vk::CommandBuffer Handle();
 void BindVertexBuffers(uint32_t,uint32_t,const vk::Buffer*,const vk::DeviceSize*,const vk::DeviceSize*);
 void PushConstants(vk::PipelineLayout,vk::ShaderStageFlags,uint32_t,uint32_t,const void*);
 bool DescriptorBindingsNeeded(vk::PipelineBindPoint,vk::PipelineLayout,bool,std::span<const vk::WriteDescriptorSet>);
};
void CommandBuffer::BindVertexBuffers(uint32_t first,uint32_t count,const vk::Buffer* buffers,const vk::DeviceSize* offsets,const vk::DeviceSize* sizes){
	if(m_nova_bindings.VertexNeeded(first,count,buffers,offsets,sizes))Handle().bindVertexBuffers2(first,count,buffers,offsets,sizes,nullptr);
}
void CommandBuffer::PushConstants(vk::PipelineLayout layout,vk::ShaderStageFlags stages,uint32_t offset,uint32_t size,const void* data){
	if(m_nova_bindings.PushNeeded(layout,stages,offset,size,data))Handle().pushConstants(layout,stages,offset,size,data);
}
bool CommandBuffer::DescriptorBindingsNeeded(vk::PipelineBindPoint point,vk::PipelineLayout layout,bool pushed,std::span<const vk::WriteDescriptorSet> writes){
	return m_nova_bindings.DescriptorsNeeded(point==vk::PipelineBindPoint::eGraphics?0u:1u,layout,pushed,writes);
}

