#!/usr/bin/env python3
"""Observational readback attribution. Validate every anchor before writing files."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
base = 'src/graphics/host_gpu/renderer/'
changes = {}
def edit(path, old, new):
    text = changes.get(path, (root / path).read_text())
    if text.count(old) != 1:
        raise SystemExit(f'NOVA_READBACK: anchor changed: {path}: {old[:100]!r}')
    changes[path] = text.replace(old, new, 1)

h, c, r = (base + x for x in ('cache/bufferCache.h', 'cache/bufferCache.cpp', 'renderContext.cpp'))
edit(h, '\tvoid                   InvalidateMemory(uint64_t vaddr, uint64_t size);',
     '\tusing ReadbackCaller = NovaRender::ReadbackCaller;\n'
     '\tusing ReadbackContext = NovaRender::ReadbackContext;\n'
     '\tvoid                   InvalidateMemory(uint64_t vaddr, uint64_t size, ReadbackContext context);')
text = changes[h]
changes[h] = '#include "graphics/host_gpu/renderer/novaReadbackTelemetry.h"\n' + text
edit(h, 'void                   ReadMemory(uint64_t vaddr, uint64_t size, bool is_write = false);',
     'void                   ReadMemory(uint64_t vaddr, uint64_t size, bool is_write, ReadbackContext context);')
edit(h, 'bool DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size);',
     'bool DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size, ReadbackContext context);')
edit(c, 'bool BufferCache::DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size) {',
     'bool BufferCache::DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size, ReadbackContext context) {\n'
     '\tconst NovaRender::ReadbackTicket telemetry {context.caller, NovaRender::ReadbackProfile()};\n'
     '\tNovaRender::ReadbackClassification classification;')
edit(c, '\t    vaddr, size, [&](uint64_t address, uint64_t bytes) noexcept {',
     '\t    vaddr, size, [&](uint64_t address, uint64_t bytes) noexcept {\n'
     '\t\t    if (telemetry.enabled) classification.Tracker(vaddr, size, address, bytes);')
edit(c, '\tif (copies.empty()) {\n\t\treturn false;\n\t}',
     '\tif (copies.empty()) {\n'
     '\t\tif (telemetry.enabled) NovaRender::AddReadback(context.caller, NovaRender::ReadbackField::ZeroCopy, 1);\n'
     '\t\treturn false;\n\t}\n'
     '\tif (telemetry.enabled) {\n'
     '\t\tfor (const auto& copy : copies) classification.Copy(context, buffer_address, copy.srcOffset, copy.size);\n'
     '\t\tNovaRender::RecordReadback(context, classification);\n\t}')
edit(c, '\t                copies = std::move(copies), owner = std::move(temporary)] {',
     '\t                telemetry, copies = std::move(copies), owner = std::move(temporary)] {\n'
     '\t\tNovaRender::ReadbackTimer timer(telemetry, NovaRender::ReadbackField::PublishNs);')
edit(c, '\t\tm_scheduler.DeferPriorityOperation(std::move(publish));',
     '\t\tm_scheduler.DeferPriorityOperation(std::move(publish), telemetry);')
edit(c, '\t\tm_scheduler.Wait(tick);\n\t\tm_scheduler.WaitPriorityOperations(tick);\n\t\tpublish();',
     '\t\t{\n\t\t\tNovaRender::ReadbackTimer timer(telemetry, NovaRender::ReadbackField::WaitNs);\n'
     '\t\t\tm_scheduler.Wait(tick);\n\t\t}\n'
     '\t\t{\n\t\t\tNovaRender::ReadbackTimer timer(telemetry, NovaRender::ReadbackField::PriorityWaitNs);\n'
     '\t\t\tm_scheduler.WaitPriorityOperations(tick);\n\t\t}\n\t\tpublish();')
edit(c, 'void BufferCache::InvalidateMemory(uint64_t vaddr, uint64_t size) {',
     'void BufferCache::InvalidateMemory(uint64_t vaddr, uint64_t size, ReadbackContext context) {')
edit(c, '[this, vaddr, size] { ReadMemory(vaddr, size, true); }',
     '[this, vaddr, size, context] { ReadMemory(vaddr, size, true, context); }')
edit(c, 'void BufferCache::ReadMemory(uint64_t vaddr, uint64_t size, bool is_write) {',
     'void BufferCache::ReadMemory(uint64_t vaddr, uint64_t size, bool is_write, ReadbackContext context) {')
edit(c, '[this, vaddr, size, is_write] {', '[this, vaddr, size, is_write, context] {')
edit(c, 'DownloadBufferMemory<false>(buffer, vaddr, size)', 'DownloadBufferMemory<false>(buffer, vaddr, size, context)')
edit(c, 'DownloadBufferMemory<true>(buffer, buffer.CpuAddress(), buffer.Size())',
     'DownloadBufferMemory<true>(buffer, buffer.CpuAddress(), buffer.Size(), {ReadbackCaller::GarbageCollection, 0, 0, false})')
edit(r, 'm_buffer_cache.InvalidateMemory(fault_vaddr, fault_size);',
     'm_buffer_cache.InvalidateMemory(fault_vaddr, fault_size, {BufferCache::ReadbackCaller::HandleFaultWrite, fault_vaddr, fault_size, true});')
edit(r, 'm_buffer_cache.ReadMemory(fault_vaddr, fault_size);',
     'm_buffer_cache.ReadMemory(fault_vaddr, fault_size, false, {BufferCache::ReadbackCaller::HandleFaultRead, fault_vaddr, fault_size, true});')
text = changes[r]
old = 'm_buffer_cache.InvalidateMemory(vaddr, size);'
if text.count(old) != 2: raise SystemExit('NOVA_READBACK: explicit invalidation anchors changed')
changes[r] = text.replace(old, 'm_buffer_cache.InvalidateMemory(vaddr, size, {BufferCache::ReadbackCaller::InvalidateMemory, 0, 0, false});')
edit(base+'renderCompute.cpp', 'cache.ReadMemory(indirect_args, sizeof(vk::DispatchIndirectCommand));',
     'cache.ReadMemory(indirect_args, sizeof(vk::DispatchIndirectCommand), false, {BufferCache::ReadbackCaller::ComputeLds, 0, 0, false});')
edit(base+'cache/textureCache.cpp', 'm_buffer_cache.ReadMemory(range.address, range.size, false);',
     'm_buffer_cache.ReadMemory(range.address, range.size, false, {BufferCache::ReadbackCaller::TextureMetadata, 0, 0, false});')
edit(base+'cache/textureCache.cpp', 'm_buffer_cache.InvalidateMemory(address, slice_size);',
     'm_buffer_cache.InvalidateMemory(address, slice_size, {BufferCache::ReadbackCaller::InvalidateMemory, 0, 0, false});')
edit('src/kernel/memory.cpp', 'buffers.ReadMemory(vaddr, size);',
     'buffers.ReadMemory(vaddr, size, false, {Graphics::BufferCache::ReadbackCaller::Other, 0, 0, false});')

# Carry observation metadata with the queued operation, never in thread-local state.
sh, sc = base+'commandScheduler.h', base+'commandScheduler.cpp'
edit(sh, '#include <condition_variable>', '#include "graphics/host_gpu/renderer/novaReadbackTelemetry.h"\n#include <condition_variable>')
edit(sh, 'void                      DeferPriorityOperation(Common::UniqueFunction<void>&& operation);',
     'void                      DeferPriorityOperation(Common::UniqueFunction<void>&& operation, NovaRender::ReadbackTicket telemetry = {});')
edit(sh, '\t\tuint64_t                     tick = 0;', '\t\tuint64_t                     tick = 0;\n\t\tNovaRender::ReadbackTicket telemetry {};')
edit(sh, 'void QueueOperation(Common::UniqueFunction<void>&& operation, bool priority);',
     'void QueueOperation(Common::UniqueFunction<void>&& operation, bool priority, NovaRender::ReadbackTicket telemetry = {});')
edit(sc, 'void CommandScheduler::DeferPriorityOperation(Common::UniqueFunction<void>&& operation) {\n\tQueueOperation(std::move(operation), true);',
     'void CommandScheduler::DeferPriorityOperation(Common::UniqueFunction<void>&& operation, NovaRender::ReadbackTicket telemetry) {\n\tQueueOperation(std::move(operation), true, telemetry);')
edit(sc, 'void CommandScheduler::QueueOperation(Common::UniqueFunction<void>&& operation, bool priority) {',
     'void CommandScheduler::QueueOperation(Common::UniqueFunction<void>&& operation, bool priority, NovaRender::ReadbackTicket telemetry) {')
edit(sc, 'queue.push({std::move(operation), CurrentTick()});', 'queue.push({std::move(operation), CurrentTick(), telemetry});')
edit(sc, '\t\tm_master.Wait(operation.tick);',
     '\t\t{\n\t\t\tNovaRender::ReadbackTimer timer(operation.telemetry, NovaRender::ReadbackField::DeferredWaitNs);\n'
     '\t\t\tm_master.Wait(operation.tick);\n\t\t}')
edit(base+'novaRenderCosts.h', '#include <array>', '#include "novaReadbackTelemetry.h"\n#include <array>')
edit(base+'novaRenderCosts.h', '        entries = {};', '        NovaRender::DumpReadbackCounters();\n        entries = {};')
changes[base+'novaReadbackTelemetry.h'] = Path(__file__).with_name('novaReadbackTelemetry.h').read_text()
for path, text in changes.items(): (root/path).write_text(text)
print('NOVA_READBACK: explicit context, orthogonal range attribution and measured phases; waits/publications preserved')
