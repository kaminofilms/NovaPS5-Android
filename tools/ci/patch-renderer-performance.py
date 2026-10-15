#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1])
def edit(path, before, after):
    p=root/path
    s=p.read_text()
    if s.count(before)!=1: raise SystemExit(f'NOVA_PERF: anchor changed in {path}: {before[:80]!r} ({s.count(before)})')
    p.write_text(s.replace(before,after,1))
pc='src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp'
ph='src/graphics/host_gpu/renderer/pipeline/pipelineCache.h'
sh='src/graphics/host_gpu/renderer/pipeline/shaders.cpp'
gc='src/graphics/host_gpu/graphicContext.h'
vw='src/graphics/presentation/window/vulkanWindow.cpp'
edit(pc,'#include <xxhash.h>','#include <xxhash.h>\n#include "graphics/host_gpu/renderer/pipeline/novaShaderDisk.h"')
edit(pc,'std::span<const uint32_t> function_code) {','std::span<const uint32_t> function_code,\n                                   const std::vector<uint8_t>& disk_key) {\n\t\tNovaShaderDisk::Entry disk;\n\t\tif (NovaShaderDisk::Load(disk_directory, disk_key, disk) &&\n\t\t    ValidateShaderSpirv(options.dump_label, options.shader_hash, disk.spirv)) {\n\t\t\tconst auto module = CompileSPV(disk.spirv, device);\n\t\t\tif (module != nullptr) {\n\t\t\t\tif (++disk_hits <= 8 || disk_hits % 64 == 0) std::fprintf(stderr,"NOVA_SHADER_DISK: hits=%llu\\n",(unsigned long long)disk_hits);\n\t\t\t\treturn {.function_code={function_code.begin(),function_code.end()},\n\t\t\t\t        .specialization=std::move(specialization), .program=std::move(disk.info),\n\t\t\t\t        .handle={.id=++next_shader_id,.module=module}};\n\t\t\t}\n\t\t}\n')
edit(pc,'\t\tDumpShaderSpirv(stage_name, options.shader_hash, result.spirv);\n\n\t\tconst auto module', '\t\tDumpShaderSpirv(stage_name, options.shader_hash, result.spirv);\n\t\tdisk.info = std::move(result.program).TakeCompiledInfo();\n\t\tdisk.spirv = result.spirv;\n\t\tNovaShaderDisk::Store(disk_directory, disk_key, disk);\n\n\t\tconst auto module')
edit(pc,'.program        = std::move(result.program).TakeCompiledInfo(),','.program        = std::move(disk.info),')
edit(pc,'\t\tentry->second.permutations.push_back(CompilePermutation(','''\t\t// Exact source, static state, linked callees and canonical specialization;
\t\t// runtime buffer addresses do not create unnecessary shader artifacts.
\t\tNovaShaderDisk::Archive key_archive;
\t\tauto code = std::vector<uint32_t>(params.code.begin(), params.code.end());
\t\tauto back = std::vector<uint32_t>(options.back_code.begin(), options.back_code.end());
\t\tauto functions = std::vector<uint32_t>(entry->second.FunctionCode().begin(),entry->second.FunctionCode().end());
\t\tkey_archive.Fields(lookup_key.stage,lookup_key.hash,lookup_key.user_data_count,
\t\t    lookup_key.static_state,options.wave_size,options.user_data_base,push_data_cursor,
\t\t    code,back,functions,entry->second.specialization);
\t\tif (!key_archive.ok) key_archive.bytes.clear();
\t\tentry->second.permutations.push_back(CompilePermutation(''')
edit(pc,'\t\t    entry->second.FunctionCode()));','\t\t    entry->second.FunctionCode(), key_archive.bytes));')
edit(pc,'explicit ProgramCache(vk::Device device): device(device) {','explicit ProgramCache(vk::Device device, const std::string& signature): device(device),\n\t    disk_directory(NovaShaderDisk::Directory(signature, PipelineCacheTitleId())) {')
edit(pc,'uint64_t                                                    next_shader_id = 0;','uint64_t                                                    next_shader_id = 0;\n\tstd::filesystem::path disk_directory;\n\tuint64_t disk_hits = 0;')
edit(pc,'std::make_unique<ProgramCache>(graphics.device)','std::make_unique<ProgramCache>(graphics.device, DriverCacheSignature(graphics.GetPhysicalDeviceProperties()))')
edit(ph,'#include <memory>','#include <memory>\n#include <string>')
edit(ph,'\tstruct GraphicsPrograms {','\tusing LibraryMaps = std::array<std::unordered_map<std::string, vk::Pipeline>, 4>;\n\tstruct GraphicsPrograms {')
edit(ph,'\tstruct ProgramCache;','\tstruct ProgramCache;\n\tLibraryMaps m_libraries;')
edit(ph,'vk::PipelineCache                      driver_cache);','vk::PipelineCache                      driver_cache,\n                            PipelineCache::LibraryMaps& libraries);')
edit(pc,'\tSave();\n\tauto destroy', '\tSave();\n\tfor (auto& part : m_libraries) for (auto& [key, library] : part) m_graphics.device.destroyPipeline(library, nullptr);\n\tauto destroy')
edit(pc,'ps_input_info, programs, static_params, m_driver_cache);','ps_input_info, programs, static_params, m_driver_cache, m_libraries);')
edit(ph,'\tGraphicContext&               m_graphics;','\tGraphicsPipelineKey m_last_graphics_key {};\n\tPipeline* m_last_graphics_pipeline = nullptr;\n\tGraphicContext&               m_graphics;')
edit(pc,'\tif (auto iter = m_graphics_pipelines.find(key); iter != m_graphics_pipelines.end()) {\n\t\treturn *iter->second;\n\t}', '''\t// Stable consecutive draws avoid hashing and probing the whole pipeline table.
\tif (m_last_graphics_pipeline != nullptr && key == m_last_graphics_key) return *m_last_graphics_pipeline;
\tif (auto iter = m_graphics_pipelines.find(key); iter != m_graphics_pipelines.end()) {
\t\tm_last_graphics_key=key; m_last_graphics_pipeline=iter->second.get();
\t\treturn *iter->second;
\t}''')
edit(pc,'\tauto [iter, inserted] = m_graphics_pipelines.emplace(std::move(key), std::move(cached));\n\tEXIT_IF(!inserted);','\tauto [iter, inserted] = m_graphics_pipelines.emplace(std::move(key), std::move(cached));\n\tEXIT_IF(!inserted);\n\tm_last_graphics_key=iter->first; m_last_graphics_pipeline=iter->second.get();')
edit(sh,'vk::PipelineCache                      driver_cache) {','vk::PipelineCache                      driver_cache,\n                            PipelineCache::LibraryMaps& libraries) {')
edit(gc,'\tbool                               memory_budget_ext_enabled', '\tbool graphics_pipeline_library_enabled = false;\n\tbool                               memory_budget_ext_enabled')
edit(vw,'\tphysical_device.getFeatures2(&supported_features2);','''\tconst bool nova_gpl_extensions = HasExtension(device_extensions, VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME) &&
\t    HasExtension(device_extensions, VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME);
\tvk::PhysicalDeviceGraphicsPipelineLibraryFeaturesEXT nova_gpl {};
\tif (nova_gpl_extensions) { nova_gpl.pNext=supported_features2.pNext; supported_features2.pNext=&nova_gpl; }
\tphysical_device.getFeatures2(&supported_features2);
\tvk::PhysicalDeviceGraphicsPipelineLibraryPropertiesEXT nova_gpl_properties {};
\tvk::PhysicalDeviceProperties2 nova_properties {};
\tnova_properties.pNext=&nova_gpl_properties;
\tif (nova_gpl_extensions) physical_device.getProperties2(&nova_properties);
\tgraphics.graphics_pipeline_library_enabled = nova_gpl_extensions && nova_gpl.graphicsPipelineLibrary &&
\t    nova_gpl_properties.graphicsPipelineLibraryFastLinking;
\tLOGF("NOVA_GPL: fast-link libraries %s\\n", graphics.graphics_pipeline_library_enabled ? "enabled" : "unavailable");''')
edit(vw,'\tcreate_info.pQueueCreateInfos       = &queue_create_info;','''\tif (graphics.graphics_pipeline_library_enabled) {
\t    nova_gpl.graphicsPipelineLibrary=VK_TRUE; nova_gpl.pNext=const_cast<void*>(create_info.pNext); create_info.pNext=&nova_gpl;
\t}
\tcreate_info.pQueueCreateInfos       = &queue_create_info;''')
edit(vw,'\t\tif (HasExtension(available_extensions, VK_EXT_MEMORY_BUDGET_EXTENSION_NAME)) {','''\t\tif (HasExtension(available_extensions,VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME) &&
\t\t    HasExtension(available_extensions,VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME)) {
\t\t    device_extensions.push_back(VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME);
\t\t    device_extensions.push_back(VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME);
\t\t}
\t\tif (HasExtension(available_extensions, VK_EXT_MEMORY_BUDGET_EXTENSION_NAME)) {''')
# GPL libraries retain exact layout compatibility, shader identity and all static state.
# Rect-list modules are transient; use the existing whole-pipeline route for them.
edit(sh,'\tresult = graphics.device.createGraphicsPipelines(driver_cache, 1, &pipeline_info, nullptr,\n\t                                                 &pipeline.pipeline);', '''\tbool nova_linked = false;
\tif (graphics.graphics_pipeline_library_enabled && !rect_list && !tessellation) {
\t\tstd::array<std::string,4> keys;
\t\tauto append=[](std::string& key,const auto& value) { key.append(reinterpret_cast<const char*>(&value),sizeof(value)); };
\t\tstd::string layout_key;
\t\tappend(layout_key,pipeline.uses_push_descriptors); append(layout_key,graphics_stages);
\t\tfor(const auto& b:descriptor_bindings) { append(layout_key,b.binding); append(layout_key,b.descriptorType); append(layout_key,b.descriptorCount); append(layout_key,b.stageFlags); }
\t\tfor(auto& key:keys) for(const auto state:dynamic_states) append(key,state);
\t\t// Vertex input and assembly have no shader/layout dependency.
\t\tappend(keys[0],input_assembly.topology); append(keys[0],input_assembly.primitiveRestartEnable);
\t\tappend(keys[0],vertex_input.binding_count); append(keys[0],vertex_input.attribute_count);
\t\tfor(uint32_t i=0;i<vertex_input.binding_count;i++) append(keys[0],input_desc[i]);
\t\tfor(uint32_t i=0;i<vertex_input.attribute_count;i++) append(keys[0],input_attr[i]);
\t\tkeys[1]+=layout_key; keys[2]+=layout_key;
\t\tfor(const auto& program:programs.vertex) append(keys[1],program.id);
\t\tappend(keys[1],static_params.negative_one_to_one); append(keys[1],static_params.depth_clip_enable);
\t\tappend(keys[1],static_params.cull_front); append(keys[1],static_params.cull_back);
\t\tappend(keys[1],static_params.face); append(keys[1],static_params.provoking_vtx_last);
\t\tappend(keys[1],static_params.polygon_mode); append(keys[1],mesh);
\t\tappend(keys[2],pixel_program.id); append(keys[2],ps_active);
\t\tfor(size_t i=1;i<3;i++) { append(keys[i],rendering.depth_format); append(keys[i],rendering.stencil_format); }
\t\tfor(size_t i=2;i<4;i++) { append(keys[i],static_params.samples); append(keys[i],static_params.sample_shading_enable); }
\t\tappend(keys[3],rendering.color_count); append(keys[3],rendering.depth_format); append(keys[3],rendering.stencil_format);
\t\tfor(uint32_t i=0;i<rendering.color_count;i++) {append(keys[3],rendering.color_formats[i]); append(keys[3],color_blend_attachment[i]);}
\t\tstd::array<vk::Pipeline,4> parts {}; uint32_t count=0;
\t\tconst std::array<vk::GraphicsPipelineLibraryFlagsEXT,4> flags {
\t\t    vk::GraphicsPipelineLibraryFlagBitsEXT::eVertexInputInterface,
\t\t    vk::GraphicsPipelineLibraryFlagBitsEXT::ePreRasterizationShaders,
\t\t    vk::GraphicsPipelineLibraryFlagBitsEXT::eFragmentShader,
\t\t    vk::GraphicsPipelineLibraryFlagBitsEXT::eFragmentOutputInterface};
\t\tvk::PipelineRenderingCreateInfo shader_rendering {};
\t\tshader_rendering.depthAttachmentFormat=rendering.depth_format;
\t\tshader_rendering.stencilAttachmentFormat=rendering.stencil_format;
\t\tbool success=true; uint32_t reused=0;
\t\tfor(uint32_t i=0;i<4;i++) {
\t\t    if(i==0 && mesh) continue;
\t\t    if(auto it=libraries[i].find(keys[i]);it!=libraries[i].end()) {parts[count++]=it->second; ++reused; continue;}
\t\t    vk::GraphicsPipelineLibraryCreateInfoEXT library {}; library.flags=flags[i];
\t\t    library.pNext=i==3 ? &rendering_info : &shader_rendering;
\t\t    vk::GraphicsPipelineCreateInfo create {}; create.pNext=&library;
\t\t    create.flags=vk::PipelineCreateFlagBits::eLibraryKHR;
\t\t    create.pDynamicState=&dynamic_state; create.layout=pipeline.pipeline_layout;
\t\t    if(i==0) {create.pVertexInputState=&vertex_input_info;create.pInputAssemblyState=&input_assembly;create.layout=nullptr;}
\t\t    if(i==1) {create.stageCount=shader_stage_count-(ps_active?1u:0u);create.pStages=shader_stages;create.pViewportState=&viewport_state;create.pRasterizationState=&rasterizer;}
\t\t    if(i==2) {create.stageCount=ps_active?1u:0u;create.pStages=ps_active?&shader_stages[shader_stage_count-1]:nullptr;create.pMultisampleState=&multisampling;create.pDepthStencilState=&depth_stencil_info;}
\t\t    if(i==3) {create.pMultisampleState=&multisampling;create.pColorBlendState=&color_blending;create.layout=nullptr;}
\t\t    vk::Pipeline part=nullptr;
\t\t    result=graphics.device.createGraphicsPipelines(driver_cache,1,&create,nullptr,&part);
\t\t    if(result!=vk::Result::eSuccess || part==nullptr) {if(part)graphics.device.destroyPipeline(part,nullptr);success=false;break;}
\t\t    libraries[i].emplace(std::move(keys[i]),part); parts[count++]=part;
\t\t}
\t\tif(success) {
\t\t    vk::PipelineLibraryCreateInfoKHR link {}; link.libraryCount=count;link.pLibraries=parts.data();
\t\t    vk::GraphicsPipelineCreateInfo create {};create.pNext=&link;create.layout=pipeline.pipeline_layout;
\t\t    result=graphics.device.createGraphicsPipelines(driver_cache,1,&create,nullptr,&pipeline.pipeline);
\t\t    nova_linked=result==vk::Result::eSuccess && pipeline.pipeline!=nullptr;
\t\t}
\t\tstatic uint64_t nova_links=0;
\t\tif(nova_linked) {if(++nova_links<=8 || nova_links%64==0)std::fprintf(stderr,"NOVA_GPL: links=%llu reused_parts=%u\\n",(unsigned long long)nova_links,reused);}
\t\telse {if(pipeline.pipeline)graphics.device.destroyPipeline(pipeline.pipeline,nullptr);pipeline.pipeline=nullptr;graphics.graphics_pipeline_library_enabled=false;std::fprintf(stderr,"NOVA_GPL: falling back after result=%d\\n",int(result));}
\t}
\tif(!nova_linked) result = graphics.device.createGraphicsPipelines(driver_cache, 1, &pipeline_info, nullptr,
\t                                                 &pipeline.pipeline);''')
# Avoid redundant binds and empty end-of-list submits. Real work, callbacks,
# semaphore submissions and explicit waits retain the existing ordering.
rh='src/graphics/host_gpu/renderer/render.h'
cx='src/graphics/host_gpu/renderer/context.cpp'
sc='src/graphics/host_gpu/renderer/commandScheduler.cpp'
edit(rh,'\tvoid BeginRendering(const RenderState& state) const;', '\tvoid BindPipeline(vk::PipelineBindPoint point, vk::Pipeline pipeline);\n\tvoid BeginRendering(const RenderState& state) const;')
edit(rh,'\tmutable RenderState m_render_state;', '\tmutable bool m_has_commands = false;\n\tstd::array<vk::Pipeline,2> m_bound_pipelines {};\n\tmutable RenderState m_render_state;')
edit(cx,'\treturn m_buffer;','\tm_has_commands = true;\n\treturn m_buffer;')
edit(cx,'\tauto buffer = Handle();\n\n\tvk::CommandBufferBeginInfo','\tauto buffer = m_buffer;\n\tm_has_commands = false;\n\tm_bound_pipelines = {};\n\n\tvk::CommandBufferBeginInfo')
edit(cx,'void CommandBuffer::End() const {','''void CommandBuffer::BindPipeline(vk::PipelineBindPoint point, vk::Pipeline pipeline) {
\tconst size_t index = point == vk::PipelineBindPoint::eGraphics ? 0u : 1u;
\tif (m_bound_pipelines[index] == pipeline) return;
\tHandle().bindPipeline(point,pipeline);
\tm_bound_pipelines[index] = pipeline;
}

void CommandBuffer::End() const {''')
edit(sc,'void CommandScheduler::Flush(SubmitInfo& submit) {\n\tSubmit(submit);','''void CommandScheduler::Flush(SubmitInfo& submit) {
\tif (!m_command.IsInvalid() && !m_command.m_has_commands &&
\t    submit.num_wait_semaphores == 0 && submit.num_signal_semaphores == 0) {
\t    std::lock_guard lock(m_operation_mutex);
\t    if (m_pending_operations.empty() && m_priority_operations.empty() && !m_priority_active) return;
\t}
\tSubmit(submit);''')
edit('src/graphics/host_gpu/renderer/renderDraw.cpp',
     'vk_buffer.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline.pipeline);',
     'buffer.BindPipeline(vk::PipelineBindPoint::eGraphics, pipeline.pipeline);')
header=Path(__file__).with_name('novaShaderDisk.h')
(root/'src/graphics/host_gpu/renderer/pipeline/novaShaderDisk.h').write_text(header.read_text())
print('NOVA_PERF: translated shader disk artifacts and reusable fast-link graphics libraries')
