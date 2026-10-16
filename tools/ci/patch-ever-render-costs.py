#!/usr/bin/env python3
"""Bound render-thread cache work without changing shaders or GPU synchronization."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
base = 'src/graphics/host_gpu/renderer/'
changes = {}

def read(path):
    if path not in changes:
        changes[path] = (root / path).read_text()
    return changes[path]

def edit(path, old, new):
    text = read(path)
    if text.count(old) != 1:
        raise SystemExit(f'NOVA_EVER: anchor changed: {path}: {old[:100]!r}')
    changes[path] = text.replace(old, new, 1)

pc = base + 'pipeline/pipelineCache.cpp'
ph = base + 'pipeline/pipelineCache.h'
edit(ph, '#include <memory>', '#include <memory>\n#include "graphics/host_gpu/renderer/novaLatestTask.h"')
edit(ph, '\tstd::filesystem::path         m_driver_cache_path;',
     '\tstd::filesystem::path         m_driver_cache_path;\n\tNovaRender::LatestTask m_snapshot_writer;')
edit(pc, 'void PipelineCache::Save(bool preserve_cache) {',
     'void PipelineCache::Save(bool preserve_cache) {\n\tNovaRender::Scope nova_cost(NovaRender::Cost::Snapshot);\n'
     '\tif (!preserve_cache) m_snapshot_writer.Drain();')
start = read(pc).index('\tif (!Common::File::CreateDirectories(m_driver_cache_path.parent_path()))', read(pc).index('void PipelineCache::Save('))
end = read(pc).index('\n\tif (!preserve_cache) {', start)
old = read(pc)[start:end]
body = old.replace('m_driver_cache_path', 'path')
edit(pc, old,
     '\t// Snapshot Vulkan data on its owner thread. Only immutable bytes and a\n'
     '\t// copied path reach the writer; it never touches this or a Vulkan handle.\n'
     '\tauto write = [path = m_driver_cache_path, prefix = std::move(prefix),\n'
     '\t              payload = std::move(payload)] {\n' + body + '\n\t};\n'
     '\tif (preserve_cache) {\n\t\tm_snapshot_writer.Post(std::move(write));\n'
     '\t} else {\n\t\twrite();\n\t}')

# Always materialize the current resources. The MRU is an index, never a pointer
# into the vector (which can move when a new permutation is compiled).
edit(pc, '\t\t\tfor (auto& candidate: permutations) {',
     '\t\t\tfor (size_t probe = 0; probe < permutations.size(); ++probe) {\n'
     '\t\t\t\tconst size_t index = probe == 0 ? last_permutation :\n'
     '\t\t\t\t    (probe <= last_permutation ? probe - 1 : probe);\n'
     '\t\t\t\tauto& candidate = permutations[index];')
edit(pc, '\t\t\t\treturn &candidate;', '\t\t\t\tlast_permutation = index;\n\t\t\t\treturn &candidate;')
edit(pc, '\t\tstd::vector<Permutation>                    permutations;',
     '\t\tstd::vector<Permutation>                    permutations;\n\t\tsize_t last_permutation = 0;')
edit(pc, '\t\tconst auto& permutation = entry->second.permutations.back();',
     '\t\tentry->second.last_permutation = entry->second.permutations.size() - 1;\n'
     '\t\tconst auto& permutation = entry->second.permutations.back();')

def scope(path, signature, name):
    edit(path, signature, signature + f'\n\tNovaRender::Scope nova_cost(NovaRender::Cost::{name});')

scope(pc, '\t                  uint32_t& push_data_cursor) {', 'Shader')
scope(pc, '    bool primitive_restart_enable, const GraphicsPrograms& programs) {', 'Pipeline')
scope(pc, '                                  const ShaderProgram&          compute_program) {', 'Pipeline')
scope(base+'commandScheduler.cpp', 'uint64_t CommandScheduler::Submit(SubmitInfo submit) {', 'Submit')
scope(base+'masterSemaphore.cpp', 'void MasterSemaphore::Wait(uint64_t tick) {', 'Wait')
scope(base+'renderDraw.cpp', '                               const DrawIndexArgs& args) {', 'Draw')
scope(base+'renderDraw.cpp', 'void RenderExecutor::DrawAuto(uint64_t submit_id, CommandBuffer& buffer, const DrawAutoArgs& args) {', 'Draw')
scope(base+'renderCompute.cpp', '                                    uint32_t thread_group_z, uint32_t mode, bool async_compute) {', 'Dispatch')
scope(base+'renderCompute.cpp', '                                      uint64_t args_addr, uint32_t mode, bool async_compute) {', 'Dispatch')
scope('src/graphics/presentation/window/swapchain.cpp', 'void Presenter::Present(std::span<const Layer> layers) {', 'Present')

for path in list(changes):
    if path.endswith('.cpp'):
        changes[path] = '#include "graphics/host_gpu/renderer/novaRenderCosts.h"\n' + changes[path]

# Validate all anchors before publishing any change.
for path, text in changes.items():
    (root / path).write_text(text)
for header in ('novaLatestTask.h', 'novaRenderCosts.h'):
    (root / base / header).write_text(Path(__file__).with_name(header).read_text())
print('NOVA_EVER: bounded asynchronous cache writes, exact MRU shader lookup, inclusive host costs')
