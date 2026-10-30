#!/usr/bin/env python3
"""Tasks 1-4 measurement: what the most expensive translated shaders contain.

0.9.113 on Wonder Boy (720p, VRS off): one pipeline costs ~2.4 ms per draw (3-4 draws per frame)
and several full-screen draws 0.4-0.8 ms each; VRS 2x2 roughly halved the top one, so the cost is
per-pixel shader work in Kyty's translated SPIR-V. Under NOVA_GPU_DRAW_PROFILE=1 every shader
module created is summarized and every graphics/compute pipeline is mapped to its modules; the
profile report then prints, for the top pipelines,

  NOVA_GPU_SHADER: rank=1 pipeline=0x... stage=ps hash=... instrs=... loops=... samples=...
                   loads(bda=... ssbo=... ubo=...) ...

and, with NOVA_SHADER_EXPORT_DIR set by the app, writes the top 4 pipelines' SPIR-V there once
per shader. Measurement only: no shader or pipeline is changed.
"""
from pathlib import Path
import sys

r = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer/pipeline'
include = '#include "common/novaRender/NovaGpuProfile.h"\n'
edits = {}

def text(path):
    if path not in edits:
        edits[path] = path.read_text()
    return edits[path]

def once(path, old, new):
    s = text(path)
    if s.count(old) != 1:
        raise SystemExit(f'0999: {path.name} anchor changed ({s.count(old)}): {old[:60]!r}; no source written')
    edits[path] = s.replace(old, new, 1)

def add_include(path):
    s = text(path)
    if include not in s:
        first = s.index('#include')
        edits[path] = s[:first] + include + s[first:]

M = 'reinterpret_cast<uint64_t>(static_cast<VkShaderModule>(module))'
pc = r / 'pipelineCache.cpp'
add_include(pc)
once(pc, '\t\t\tconst auto module = CompileSPV(disk.spirv, device);\n',
     '\t\t\tconst auto module = CompileSPV(disk.spirv, device);\n'
     f'\t\t\tNovaGpuProfile::Shaders::Get().NoteModule({M}, stage_name, options.shader_hash, disk.spirv.data(), disk.spirv.size());\n')
once(pc, '\t\tconst auto module = CompileSPV(result.spirv, device);\n',
     '\t\tconst auto module = CompileSPV(result.spirv, device);\n'
     f'\t\tNovaGpuProfile::Shaders::Get().NoteModule({M}, stage_name, options.shader_hash, result.spirv.data(), result.spirv.size());\n')

sh = r / 'shaders.cpp'
add_include(sh)
once(sh, '\tEXIT_NOT_IMPLEMENTED(pipeline.pipeline == nullptr);\n\n\tif (tess_control_shader_module != nullptr) {',
     '\tEXIT_NOT_IMPLEMENTED(pipeline.pipeline == nullptr);\n'
     '\tif (NovaGpuProfile::Enabled()) {\n'
     '\t\tuint64_t nova_modules[4] {};\n'
     '\t\tfor (uint32_t i = 0; i < shader_stage_count && i < 4; ++i)\n'
     '\t\t\tnova_modules[i] = reinterpret_cast<uint64_t>(static_cast<VkShaderModule>(shader_stages[i].module));\n'
     '\t\tNovaGpuProfile::Shaders::Get().NotePipeline(reinterpret_cast<uint64_t>(static_cast<VkPipeline>(pipeline.pipeline)),\n'
     '\t\t                                            nova_modules, shader_stage_count < 4 ? shader_stage_count : 4);\n'
     '\t}\n'
     '\n\tif (tess_control_shader_module != nullptr) {')
once(sh, '\tLOGF("PipelineTrace: vkCreateComputePipelines done result=%s pipeline=%p\\n",',
     '\tif (NovaGpuProfile::Enabled() && result == vk::Result::eSuccess && pipeline.pipeline != nullptr) {\n'
     '\t\tconst uint64_t nova_module = reinterpret_cast<uint64_t>(static_cast<VkShaderModule>(info.stage.module));\n'
     '\t\tNovaGpuProfile::Shaders::Get().NotePipeline(reinterpret_cast<uint64_t>(static_cast<VkPipeline>(pipeline.pipeline)), &nova_module, 1);\n'
     '\t}\n'
     '\tLOGF("PipelineTrace: vkCreateComputePipelines done result=%s pipeline=%p\\n",')

for path, s in edits.items():
    path.write_text(s)
print('0999: top-pipeline shader summaries (NOVA_GPU_SHADER) and optional SPIR-V export (NOVA_SHADER_EXPORT_DIR)')
