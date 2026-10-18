#!/usr/bin/env python3
"""Ever Forward: reconcile fully-known constant-label pages after real completion."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);base='src/graphics/host_gpu/renderer/'
changes={}
def edit(path,old,new):
    text=changes.get(path,(root/path).read_text())
    if text.count(old)!=1: raise SystemExit("NOVA_LABEL_PUBLISH: changed anchor "+path)
    changes[path]=text.replace(old,new,1)
edit(base+'cache/bufferCache.h',
     '\tbool TryReadEopLabel(uint64_t vaddr, void* data, uint64_t size);',
     '\tbool TryReadEopLabel(uint64_t vaddr, void* data, uint64_t size);\n\tbool TryPublishEopLabels(uint64_t vaddr, uint64_t size, ReadbackContext context);')
method="bool BufferCache::TryPublishEopLabels(uint64_t vaddr, uint64_t size, ReadbackContext context) {\n    if (!NovaRender::EverProfile() || !context.is_fault_origin || !GuestRange {vaddr, size}.Valid()) return false;\n    struct Part { uint64_t address; NovaRender::EopLabels::Entry entry; };\n    struct Plan { std::vector<Part> parts; std::vector<std::pair<uint64_t, uint64_t>> domains; uint64_t tick = 0; bool valid = true; };\n    const auto collect = [&] {\n        Plan plan;\n        m_memory_tracker.ForEachDownloadRange<false>(vaddr, size, [&](uint64_t address, uint64_t bytes) noexcept {\n            if (!plan.valid) return;\n            if (m_texture_cache.FindImageFromRange(address, bytes)) { plan.valid = false; return; }\n            plan.domains.emplace_back(address, bytes);\n            m_gpu_modified_ranges.ForEachInRange(address, bytes, [&](uint64_t begin, uint64_t end) {\n                if ((begin & 3u) != 0 || ((end - begin) & 3u) != 0) { plan.valid = false; return; }\n                for (auto at = begin; at < end && plan.valid; at += 4) {\n                    const auto known = m_eop_labels.Find(at, 4);\n                    if (!known || plan.parts.size() >= 256) { plan.valid = false; break; }\n                    plan.parts.push_back({at, *known});\n                    plan.tick = std::max(plan.tick, known->tick);\n                }\n            });\n        });\n        return plan;\n    };\n    const auto plan = collect();\n    if (!plan.valid || plan.parts.empty()) return false;\n    NovaRender::Scope cost(NovaRender::Cost::EopLabelPublish);\n    // Wait for actual recorded uploads and prior CPU publications. Do not append\n    // a redundant download command merely to read immutable constant bytes.\n    m_scheduler.Wait(plan.tick);\n    m_scheduler.WaitPriorityOperations(plan.tick);\n    const auto current = collect();\n    if (!current.valid || current.domains != plan.domains || current.parts.size() != plan.parts.size()) return false;\n    for (size_t i = 0; i < plan.parts.size(); ++i) {\n        const auto& a = plan.parts[i]; const auto& b = current.parts[i];\n        if (a.address != b.address || a.entry.address != b.entry.address || a.entry.size != b.entry.size ||\n            a.entry.tick != b.entry.tick || a.entry.bytes != b.entry.bytes) return false;\n    }\n    for (const auto& part : plan.parts)\n        Libs::LibKernel::Memory::WriteBacking(part.address, part.entry.bytes.data() + (part.address - part.entry.address), 4);\n    for (const auto& [address, bytes] : plan.domains) {\n        m_eop_labels.Invalidate(address, bytes);\n        m_gpu_modified_ranges.Subtract(address, bytes);\n    }\n    // ReadMemory performs the existing page ownership/protection reconciliation.\n    return true;\n}\n\n"
edit(base+'cache/bufferCache.cpp','bool BufferCache::TryReadEopLabel(',method+'bool BufferCache::TryReadEopLabel(')
edit(base+'cache/bufferCache.cpp',
     'bool BufferCache::DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size, ReadbackContext context) {',
     'bool BufferCache::DownloadBufferMemory(Buffer& buffer, uint64_t vaddr, uint64_t size, ReadbackContext context) {\n\tif constexpr (!async) {\n\t\tif (TryPublishEopLabels(vaddr, size, context)) return true;\n\t}')
edit(base+'novaRenderCosts.h','EopLabelRead, Count','EopLabelRead, EopLabelPublish, Count')
edit(base+'novaRenderCosts.h','"eop_label_read"}','"eop_label_read", "eop_label_publish"}')
for path,text in changes.items():(root/path).write_text(text)
print("NOVA_LABEL_PUBLISH: Ever-only known labels, actual completion/publication, post-wait validation; unknown data keeps normal readback")
