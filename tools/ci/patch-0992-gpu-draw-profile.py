#!/usr/bin/env python3
"""Tasks 1-4 measurement: which GPU work makes a Wonder Boy gameplay frame cost ~42 ms?

Adds native/render/NovaGpuProfile.h (sampled per-draw/per-dispatch timestamps, report by pipeline;
see the header) and brackets every guest draw/dispatch plus Kyty's own tiler, blit and fault
dispatches. Active only with NOVA_GPU_DRAW_PROFILE=1; otherwise each bracket is one bool test.
Measurement only: no command is reordered, skipped or changed.
"""
from pathlib import Path
import shutil
import sys

repo = Path(__file__).resolve().parents[2]
root = Path(sys.argv[1])
r = root / 'src/graphics/host_gpu/renderer'
include = '#include "common/novaRender/NovaGpuProfile.h"\n'
edits = {}

def text(path):
    if path not in edits:
        edits[path] = path.read_text()
    return edits[path]

def once(path, old, new):
    s = text(path)
    if s.count(old) != 1:
        raise SystemExit(f'0992: {path.name} anchor changed ({s.count(old)}): {old[:60]!r}; no source written')
    edits[path] = s.replace(old, new, 1)

def add_include(path):
    s = text(path)
    if include not in s:
        first = s.index('#include')
        edits[path] = s[:first] + include + s[first:]

P = 'static_cast<VkCommandBuffer>'
# Command-buffer begin (outside any render pass).
cs = r / 'commandScheduler.cpp'
add_include(cs)
once(cs, '\tm_command.Begin();\n\tNovaGpuTimeBegin();\n',
     '\tm_command.Begin();\n\tNovaGpuTimeBegin();\n'
     '\tif (NovaGpuProfile::Enabled()) {\n'
     '\t\tconst auto& d = VULKAN_HPP_DEFAULT_DISPATCHER;\n'
     '\t\tNovaGpuProfile::Profiler::Get().BeginCommandBuffer(static_cast<VkDevice>(m_graphics.device),\n'
     '\t\t    m_graphics.physical_device_properties.limits, static_cast<VkCommandBuffer>(m_command.m_buffer),\n'
     '\t\t    d.vkCreateQueryPool, d.vkGetQueryPoolResults, d.vkCmdResetQueryPool, d.vkCmdWriteTimestamp);\n'
     '\t}\n')
# Guest draws.
rd = r / 'renderDraw.cpp'
add_include(rd)
once(rd, '\tif (mesh_active) {\n\t\tvk_buffer.drawMeshTasksEXT(mesh_groups, draw.instance_count, 1);\n\t} else {\n\t\tEmitDrawPrimitives(ucfg, vk_buffer, draw, emit);\n\t}\n',
     '\t{\n'
     f'\t\tNovaGpuProfile::Scope nova_gpu_profile({P}(vk_buffer),\n'
     '\t\t    {NovaGpuProfile::Kind::Draw, reinterpret_cast<uint64_t>(static_cast<VkPipeline>(pipeline.pipeline)),\n'
     '\t\t     rendering.nova_backing_scaled ? uint32_t(rendering.width * rendering.nova_scale_x + 0.5f) : rendering.width,\n'
     '\t\t     rendering.nova_backing_scaled ? uint32_t(rendering.height * rendering.nova_scale_y + 0.5f) : rendering.height,\n'
     '\t\t     rendering.num_color_attachments, draw.index_count, draw.instance_count});\n'
     '\t\tif (mesh_active) {\n\t\t\tvk_buffer.drawMeshTasksEXT(mesh_groups, draw.instance_count, 1);\n\t\t} else {\n\t\t\tEmitDrawPrimitives(ucfg, vk_buffer, draw, emit);\n\t\t}\n'
     '\t}\n')
# Guest compute.
rc = r / 'renderCompute.cpp'
add_include(rc)
once(rc, '\tvk_buffer.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline.pipeline);\n\tvk_buffer.dispatch(thread_group_x, thread_group_y, thread_group_z);\n',
     '\tvk_buffer.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline.pipeline);\n'
     '\t{\n'
     f'\t\tNovaGpuProfile::Scope nova_gpu_profile({P}(vk_buffer),\n'
     '\t\t    {NovaGpuProfile::Kind::Dispatch, reinterpret_cast<uint64_t>(static_cast<VkPipeline>(pipeline.pipeline)),\n'
     '\t\t     thread_group_x, thread_group_y, 0, thread_group_z, 1});\n'
     '\t\tvk_buffer.dispatch(thread_group_x, thread_group_y, thread_group_z);\n'
     '\t}\n')
once(rc, '\tvk_buffer.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline.pipeline);\n\tvk_buffer.dispatchIndirect(args_buffer->Handle(), args_offset);\n',
     '\tvk_buffer.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline.pipeline);\n'
     '\t{\n'
     f'\t\tNovaGpuProfile::Scope nova_gpu_profile({P}(vk_buffer),\n'
     '\t\t    {NovaGpuProfile::Kind::DispatchIndirect, reinterpret_cast<uint64_t>(static_cast<VkPipeline>(pipeline.pipeline))});\n'
     '\t\tvk_buffer.dispatchIndirect(args_buffer->Handle(), args_offset);\n'
     '\t}\n')
# Kyty's own GPU work: tiler (3 sites, told apart by `targets`), blit, fault buffer parser.
tl = r / 'image/tiler.cpp'
add_include(tl)
for site, old in enumerate(['\tcommand.dispatch(groups_x, groups_y, 1);\n',
                            '\t\t\tcommand.dispatch(static_cast<uint32_t>(groups_x), rows, 1);\n',
                            '\tcommand.dispatch((pixels + 63u) / 64u, 1, 1);\n'], start=1):
    indent = old[:len(old) - len(old.lstrip('\t'))]
    call = old.strip()
    once(tl, old, f'{indent}{{\n{indent}\tNovaGpuProfile::Scope nova_gpu_profile({P}(command), {{NovaGpuProfile::Kind::Tiler, 0, 0, 0, {site}}});\n{indent}\t{call}\n{indent}}}\n')
bh = r / 'image/blitHelper.cpp'
add_include(bh)
once(bh, '\tcommand.draw(3, 1, 0, 0);\n',
     f'\t{{\n\t\tNovaGpuProfile::Scope nova_gpu_profile({P}(command), {{NovaGpuProfile::Kind::Blit, 0, destination_info.extent.width, destination_info.extent.height, 1, 3, 1}});\n\t\tcommand.draw(3, 1, 0, 0);\n\t}}\n')
fm = r / 'cache/faultManager.cpp'
add_include(fm)
once(fm, '\tcommand.dispatch(static_cast<uint32_t>(num_workgroups), 1, 1);\n',
     f'\t{{\n\t\tNovaGpuProfile::Scope nova_gpu_profile({P}(command), {{NovaGpuProfile::Kind::Fault}});\n\t\tcommand.dispatch(static_cast<uint32_t>(num_workgroups), 1, 1);\n\t}}\n')

(root / 'src/common/novaRender').mkdir(parents=True, exist_ok=True)
shutil.copyfile(repo / 'native/render/NovaGpuProfile.h', root / 'src/common/novaRender/NovaGpuProfile.h')
for path, s in edits.items():
    path.write_text(s)
print('0992: sampled per-draw/dispatch GPU timing by pipeline (NOVA_GPU_DRAW_PROFILE=1 -> NOVA_GPU_DRAW lines)')
