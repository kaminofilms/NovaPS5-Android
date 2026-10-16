#!/usr/bin/env python3
"""Avoid downloading already-known constant EOP bytes after real GPU completion.
Only Ever Forward and the owner's identified Super Meat Boy title opt in.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]);base='src/graphics/host_gpu/renderer/';changes={}
def edit(path,old,new):
    s=changes.get(path,(root/path).read_text())
    if s.count(old)!=1:raise SystemExit(f'NOVA_EOP_READ: anchor changed {path}: {old[:90]!r}')
    changes[path]=s.replace(old,new,1)

cost=base+'novaRenderCosts.h'
edit(cost,'enum class Cost : unsigned {', '''inline bool GpuLabelProfile() {
    static const bool enabled = [] {
        const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
        return title && (std::string_view(title) == "PPSA04703" ||
                         std::string_view(title) == "PPSA31162");
    }();
    return enabled;
}
enum class Cost : unsigned {''')
edit(cost,'ReadbackWrite, ReadbackRead, Count','ReadbackWrite, ReadbackRead, EopLabelRead, Count')
edit(cost,'"readback_write", "readback_read"','"readback_write", "readback_read", "eop_label_read"')
h=base+'cache/bufferCache.h';c=base+'cache/bufferCache.cpp';t=base+'cache/textureCache.cpp'
edit(h,'#include <map>','#include "graphics/host_gpu/renderer/novaEopLabels.h"\n#include <map>')
edit(h,'\tbool WriteEopLabel(uint64_t vaddr, const void* data, uint64_t size);',
     '\tbool WriteEopLabel(uint64_t vaddr, const void* data, uint64_t size);\n'
     '\t// GPU-thread only; a miss preserves the existing coherent download.\n'
     '\tbool TryReadEopLabel(uint64_t vaddr, void* data, uint64_t size);')
edit(h,'\tRangeSet                                          m_gpu_modified_ranges;',
     '\tRangeSet                                          m_gpu_modified_ranges;\n\tNovaRender::EopLabels m_eop_labels;')
edit(c,'\tWriteDataBuffer(*buffer, vaddr, data, size);\n\treturn true;',
     '\tWriteDataBuffer(*buffer, vaddr, data, size);\n'
     '\t// Record only after the immutable staging copy and its GPU command exist.\n'
     '\tm_eop_labels.Record(vaddr, data, size, m_scheduler.CurrentTick());\n\treturn true;')
edit(c,'void BufferCache::Register(BufferId id) {', '''bool BufferCache::TryReadEopLabel(uint64_t vaddr, void* data, uint64_t size) {
	if (!NovaRender::GpuLabelProfile() || data == nullptr || (size != 4 && size != 8) ||
	    !GuestRange {vaddr, size}.Valid() || !m_gpu_modified_ranges.Contains(vaddr, size)) return false;
	const auto known = m_eop_labels.Find(vaddr, size);
	if (!known || m_texture_cache.FindImageFromRange(vaddr, size)) return false;
	NovaRender::Scope nova_label_read_cost(NovaRender::Cost::EopLabelRead);
	// The value is useful only AFTER the upload's real GPU timeline point and
	// earlier host publications finish. No GPU work or guest predicate is skipped.
	m_scheduler.Wait(known->tick);
	m_scheduler.WaitPriorityOperations(known->tick);
	const auto current = m_eop_labels.Find(vaddr, size);
	if (!current || current->tick != known->tick || current->bytes != known->bytes ||
	    !m_gpu_modified_ranges.Contains(vaddr, size)) return false;
	std::memcpy(data, current->bytes.data() + (vaddr-current->address), size);
	// Do not publish CPU backing or remove GPU ownership/page protection. Guest
	// CPU readers/writers still reconcile the real buffer through the fault path.
	return true;
}

void BufferCache::Register(BufferId id) {''')
edit(c,'\tif (is_written) {\n\t\tm_gpu_modified_ranges.Add(vaddr, size);',
     '\tif (is_written) {\n\t\tm_eop_labels.Invalidate(vaddr, size);\n\t\tm_gpu_modified_ranges.Add(vaddr, size);')
edit(c,'\t\t    m_gpu_modified_ranges.Subtract(address, bytes);',
     '\t\t    m_eop_labels.Invalidate(address, bytes);\n\t\t    m_gpu_modified_ranges.Subtract(address, bytes);')
edit(c,'void BufferCache::Unregister(BufferId id) {\n\tChangeRegister<false>(id);',
     'void BufferCache::Unregister(BufferId id) {\n'
     '\tconst auto& buffer = m_slot_buffers[id];\n'
     '\tm_eop_labels.Invalidate(buffer.CpuAddress(), buffer.Size());\n\tChangeRegister<false>(id);')
edit(t,'\tm_texture_cache.DownloadImage(image, buffer, buf_offset, copy_size, levels);',
     '\tm_eop_labels.Invalidate(image.info.data.address, copy_size);\n'
     '\tm_texture_cache.DownloadImage(image, buffer, buf_offset, copy_size, levels);')
edit('src/kernel/memory.cpp','\t\tauto& buffers = GetGpuResources().GetBufferCache();\n\t\tif (buffers.HasGpuDirtyBytes(vaddr, size)) {',
     '\t\tauto& buffers = GetGpuResources().GetBufferCache();\n'
     '\t\tif (buffers.HasGpuDirtyBytes(vaddr, size)) {\n'
     '\t\t\tif (buffers.TryReadEopLabel(vaddr, data, size)) return true;')
gr='src/graphics/guest_gpu/graphicsRun.cpp'
s=(root/gr).read_text()
if s.count('NovaRender::EverProfile()')!=6:raise SystemExit('NOVA_EOP_READ: title profile anchors changed')
changes[gr]=s.replace('NovaRender::EverProfile()','NovaRender::GpuLabelProfile()')
changes[base+'novaEopLabels.h']=Path(__file__).with_name('novaEopLabels.h').read_text()
for path,s in changes.items():(root/path).write_text(s)
print('NOVA_EOP_READ: constant label bytes reuse real completion; overlapping writes/downloads/retirement invalidate; Ever and Meat Boy only')
