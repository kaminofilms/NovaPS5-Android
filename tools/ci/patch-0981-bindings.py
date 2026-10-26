#!/usr/bin/env python3
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);pending={}
def edit(name,old,new):
 p=root/name;s=pending.get(p,p.read_text())
 if s.count(old)!=1:raise SystemExit('0981 changed anchor '+name+' '+old[:80])
 pending[p]=s.replace(old,new,1)
h='src/graphics/host_gpu/renderer/render.h'
edit(h,'#include <array>','#include "common/novaRender/BindingCache.h"\n#include <array>')
edit(h,'\tvoid BindPipeline(vk::PipelineBindPoint point, vk::Pipeline pipeline);','''\tvoid BindPipeline(vk::PipelineBindPoint point, vk::Pipeline pipeline);
\tvoid BindVertexBuffers(uint32_t first,uint32_t count,const vk::Buffer* buffers,const vk::DeviceSize* offsets,const vk::DeviceSize* sizes);
\tvoid PushConstants(vk::PipelineLayout layout,vk::ShaderStageFlags stages,uint32_t offset,uint32_t size,const void* data);
\tbool DescriptorBindingsNeeded(vk::PipelineBindPoint point,vk::PipelineLayout layout,bool pushed,std::span<const vk::WriteDescriptorSet> writes);
\tvoid InvalidateBindingCache() const {m_nova_bindings.Reset();m_bound_pipelines={};}''')
edit(h,'\tstd::array<vk::Pipeline,2> m_bound_pipelines {};','\tmutable std::array<vk::Pipeline,2> m_bound_pipelines {};\n\tmutable NovaRender::BindingCache m_nova_bindings;')
c='src/graphics/host_gpu/renderer/context.cpp'
edit(c,'\tm_bound_pipelines = {};','\tm_bound_pipelines = {};\n\tInvalidateBindingCache();')
edit(c,'void CommandBuffer::EndRendering(std::source_location where) const {','''void CommandBuffer::EndRendering(std::source_location where) const {
\t// Raw tiler/transfer helpers may change Vulkan binding state after this boundary.
\tInvalidateBindingCache();''')
edit(c,'void CommandBuffer::End() const {','''void CommandBuffer::BindVertexBuffers(uint32_t first,uint32_t count,const vk::Buffer* buffers,const vk::DeviceSize* offsets,const vk::DeviceSize* sizes){
\tif(m_nova_bindings.VertexNeeded(first,count,buffers,offsets,sizes))Handle().bindVertexBuffers2(first,count,buffers,offsets,sizes,nullptr);
}
void CommandBuffer::PushConstants(vk::PipelineLayout layout,vk::ShaderStageFlags stages,uint32_t offset,uint32_t size,const void* data){
\tif(m_nova_bindings.PushNeeded(layout,stages,offset,size,data))Handle().pushConstants(layout,stages,offset,size,data);
}
bool CommandBuffer::DescriptorBindingsNeeded(vk::PipelineBindPoint point,vk::PipelineLayout layout,bool pushed,std::span<const vk::WriteDescriptorSet> writes){
\treturn m_nova_bindings.DescriptorsNeeded(point==vk::PipelineBindPoint::eGraphics?0u:1u,layout,pushed,writes);
}

void CommandBuffer::End() const {''')
d='src/graphics/host_gpu/renderer/renderDraw.cpp'
edit(d,'static void CommitVertexBuffers(vk::CommandBuffer            vk_buffer,','static void CommitVertexBuffers(CommandBuffer&              owner,')
edit(d,'\t\tvk_buffer.bindVertexBuffers2(0, prepared.count, prepared.buffers.data(),','\t\towner.BindVertexBuffers(0, prepared.count, prepared.buffers.data(),')
edit(d,'prepared.offsets.data(), prepared.sizes.data(), nullptr);','prepared.offsets.data(), prepared.sizes.data());')
edit(d,'\t\tCommitVertexBuffers(vk_buffer, vertex_bindings);','\t\tCommitVertexBuffers(buffer, vertex_bindings);')
edit(d,'\t\tvk_buffer.pushConstants(pipeline.pipeline_layout,','\t\tbuffer.PushConstants(pipeline.pipeline_layout,')
edit(d,'    vk_buffer.pushConstants(pipeline.pipeline_layout,raster_stages,0,sizeof(raster_inverse),raster_inverse);','    buffer.PushConstants(pipeline.pipeline_layout,raster_stages,0,sizeof(raster_inverse),raster_inverse);')
p='src/graphics/host_gpu/renderer/pipeline/descriptors.cpp'
edit(p,'\t\tvk_buffer.pushConstants(pipeline.pipeline_layout, push_stages, 0, sizeof(push_data),','\t\tbuffer.PushConstants(pipeline.pipeline_layout, push_stages, 0, sizeof(push_data),')
edit(p,'\tif (!m_descriptor_writes.empty()) {','''\tif (!m_descriptor_writes.empty() && buffer.DescriptorBindingsNeeded(
\t        pipeline_bind_point,pipeline.pipeline_layout,pipeline.uses_push_descriptors,m_descriptor_writes)) {''')
for p,s in pending.items():p.write_text(s)
(root/'src/common/novaRender').mkdir(parents=True,exist_ok=True)
shutil.copyfile(repo/'native/render/BindingCache.h',root/'src/common/novaRender/BindingCache.h')
print('0981: command-local descriptor/vertex/push binding cache; preparation and barriers remain')
