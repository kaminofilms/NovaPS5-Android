#!/usr/bin/env python3
"""Remove measured guest access traps without changing draw/dispatch/sync semantics."""
from pathlib import Path
import sys
root = Path(sys.argv[1])
def once(s, old, new):
    if s.count(old) != 1:
        raise SystemExit(f'NOVA_GPU_PERF: expected one anchor: {old[:90]!r}, got {s.count(old)}')
    return s.replace(old, new, 1)
agc_path = root / 'src/libs/agc.cpp'
gpu_path = root / 'src/graphics/guest_gpu/graphicsRun.cpp'
cache_path = root / 'src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp'
shaders_path = root / 'src/graphics/host_gpu/renderer/pipeline/shaders.cpp'
agc, gpu, cache, shaders = [p.read_text() for p in (agc_path,gpu_path,cache_path,shaders_path)]
helper = '''// Local descriptors preserve the guest ABI while their semantic tables use
// bounded native aliases. Slot-crossing tables retain the fault-safe fallback.
static Shader nova_interpolant_shader(const Shader* guest) {
\tShader local {};
\tGuestMemory::Copy(&local, guest, sizeof(local));
\tlocal.input_semantics = GuestMemory::Ptr(local.input_semantics,
\t    uint64_t {local.num_input_semantics} * sizeof(ShaderSemantic));
\tlocal.output_semantics = GuestMemory::Ptr(local.output_semantics,
\t    uint64_t {local.num_output_semantics} * sizeof(ShaderSemantic));
\treturn local;
}

'''
agc = once(agc, 'int KYTY_SYSV_ABI AgcCreateInterpolantMapping(', helper + 'int KYTY_SYSV_ABI AgcCreateInterpolantMapping(')
for name in ['AgcCreateInterpolantMapping', 'AgcCreateInterpolantMapping2']:
    start = agc.index('int KYTY_SYSV_ABI ' + name + '(')
    end = agc.index('\n}', start) + 2
    body = agc[start:end]
    anchor = '\tEXIT_NOT_IMPLEMENTED(regs == nullptr);'
    body = once(body, anchor, anchor + '''
#if defined(KYTY_NOVA_FEX)
\tShader native_ps {}, native_gs {};
\tif (ps != nullptr) { native_ps = nova_interpolant_shader(ps); ps = &native_ps; }
\tconst uint64_t output_count = std::max<uint64_t>(32u, ps ? ps->num_input_semantics : 0u);
\tregs = GuestMemory::Ptr(regs, output_count * sizeof(ShaderRegister));
#endif''')
    body = once(body, '\tEXIT_NOT_IMPLEMENTED(gs == nullptr);', '''\tEXIT_NOT_IMPLEMENTED(gs == nullptr);
#if defined(KYTY_NOVA_FEX)
\tnative_gs = nova_interpolant_shader(gs); gs = &native_gs;
#endif''')
    agc = agc[:start] + body + agc[end:]
gpu = once(gpu, 'auto*              results      = reinterpret_cast<volatile uint64_t*>(event_address);',
'''// Resolve the full interleaved 16-DB result once. Keep volatile stores,
\t\t\t// all begin slots, ready bits and counter progression unchanged.
\t\t\tauto* results = reinterpret_cast<volatile uint64_t*>(
\t\t\t    GuestMemory::Ptr<uint64_t>(event_address, 32u * sizeof(uint64_t)));''')
if '#include "common/guestMemory.h"' not in gpu:
    gpu = '#include "common/guestMemory.h"\n' + gpu
# Record only misses taking >=100ms; no extra work/logging on cached draws.
cache = once(cache, '#include <cstring>', '#include <cstring>\n#include <chrono>')
cache = once(cache, '\t\tauto result = ShaderRecompiler::CompileProgram(std::move(translated), options,',
'''\t\tconst auto nova_compile_start = std::chrono::steady_clock::now();
\t\tauto result = ShaderRecompiler::CompileProgram(std::move(translated), options,''')
cache = once(cache, '\t\tconst auto module = CompileSPV(result.spirv, device);',
'''\t\tconst auto module = CompileSPV(result.spirv, device);
\t\tconst auto nova_compile_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
\t\t    std::chrono::steady_clock::now() - nova_compile_start).count();
\t\tif (nova_compile_ms >= 100) {
\t\t\tstd::fprintf(stderr, "NOVA_SHADER_TIME: stage=%s hash=%016llx words=%zu ms=%lld\\n",
\t\t\t    stage_name, static_cast<unsigned long long>(options.shader_hash), result.spirv.size(),
\t\t\t    static_cast<long long>(nova_compile_ms));
\t\t}''')
if '#include <chrono>' not in shaders: shaders = '#include <chrono>\n#include <cstdio>\n' + shaders
for kind, anchor, finish in [
    ('graphics', '\tresult = graphics.device.createGraphicsPipelines(driver_cache, 1, &pipeline_info, nullptr,', '\tEXIT_NOT_IMPLEMENTED(pipeline.pipeline == nullptr);'),
    ('compute', '\tresult = graphics.device.createComputePipelines(driver_cache, 1, &info, nullptr,', '\tLOGF("PipelineTrace: vkCreateComputePipelines done result=%s pipeline=%p\\n",')]:
    shaders = once(shaders, anchor, '\tconst auto nova_' + kind + '_start = std::chrono::steady_clock::now();\n' + anchor)
    start = shaders.index('const auto nova_' + kind + '_start')
    # For graphics choose the first finished-pipeline check after creation.
    point = shaders.index(finish, start)
    timing = '''\tconst auto nova_KIND_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
\t    std::chrono::steady_clock::now() - nova_KIND_start).count();
\tif (nova_KIND_ms >= 100) {
\t\tstd::fprintf(stderr, "NOVA_PIPELINE_TIME: kind=KIND ms=%lld cached_driver=%u\\n",
\t\t    static_cast<long long>(nova_KIND_ms), driver_cache != nullptr ? 1u : 0u);
\t}
'''.replace('KIND',kind)
    shaders = shaders[:point] + timing + shaders[point:]
for p,s in zip((agc_path,gpu_path,cache_path,shaders_path),(agc,gpu,cache,shaders)): p.write_text(s)
print('NOVA_GPU_PERF: native occlusion results, interpolant descriptors/tables/registers, slow compilation timing')
