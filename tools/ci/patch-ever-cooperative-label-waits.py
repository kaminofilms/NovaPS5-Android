#!/usr/bin/env python3
"""Suspend Ever Forward's PM4 queue instead of blocking on recorded GPU labels."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
base = 'src/graphics/host_gpu/renderer/'
changes = {}
def edit(path, old, new):
    text = changes.get(path, (root / path).read_text())
    if text.count(old) != 1:
        raise SystemExit('NOVA_COOPERATIVE_LABEL: changed anchor ' + path)
    changes[path] = text.replace(old, new, 1)

edit(base+'commandScheduler.h', '\tvoid                      Wait(uint64_t tick);',
     '\tvoid                      Wait(uint64_t tick);\n\t[[nodiscard]] bool        PollCompletion(uint64_t tick);')
poll = '''bool CommandScheduler::PollCompletion(uint64_t tick) {
    EXIT_IF(tick > CurrentTick());
    // Submit the real producer before yielding. A recorded, unsubmitted tick
    // cannot complete. Flush begins a fresh command buffer without host waiting.
    if (tick == CurrentTick()) Flush();
    if (!IsFree(tick)) return false;
    // GPU completion alone is insufficient when an earlier priority callback
    // is still publishing guest memory. Do not wait on that callback here.
    std::lock_guard lock(m_operation_mutex);
    const bool active_before_or_at = m_priority_active && m_priority_active_tick <= tick;
    const bool queued_before_or_at =
        !m_priority_operations.empty() && m_priority_operations.front().tick <= tick;
    return !active_before_or_at && !queued_before_or_at;
}

'''
edit(base+'commandScheduler.cpp', 'void CommandScheduler::PopPendingOperations() {',
     poll+'void CommandScheduler::PopPendingOperations() {')
edit(base+'cache/bufferCache.h', '\tbool TryReadEopLabel(uint64_t vaddr, void* data, uint64_t size);',
     '\tbool TryReadEopLabel(uint64_t vaddr, void* data, uint64_t size);\n\tbool IsEopLabelPending(uint64_t vaddr, uint64_t size);')
pending = '''bool BufferCache::IsEopLabelPending(uint64_t vaddr, uint64_t size) {
    if (!NovaRender::EverProfile() || (size != 4 && size != 8) ||
        !GuestRange {vaddr, size}.Valid() || !m_gpu_modified_ranges.Contains(vaddr, size)) return false;
    const auto known = m_eop_labels.Find(vaddr, size);
    if (!known || m_texture_cache.FindImageFromRange(vaddr, size)) return false;
    NovaRender::Scope cost(NovaRender::Cost::EopLabelPoll);
    // This is only a pending/ready test, never a value publication. The PM4
    // packet is retried at its original cursor and re-reads current metadata.
    return !m_scheduler.PollCompletion(known->tick);
}

'''
edit(base+'cache/bufferCache.cpp', 'bool BufferCache::TryPublishEopLabels(',
     pending+'bool BufferCache::TryPublishEopLabels(')
path = 'src/graphics/guest_gpu/graphicsRun.cpp'
anchor = '\t// A queued GPU label may not yet be in CPU backing. Resolve only actual dirty'
branch = '''	// Ever Forward: yield only this PM4 queue while a known label is pending.
	// Unknown/GPU-generated data retains the existing coherent readback path.
	if (NovaRender::EverProfile() && m_renderer.GetBufferCache().IsEopLabelPending(
	        reinterpret_cast<uint64_t>(addr), sizeof(T))) {
		NovaRender::Scope cost(NovaRender::Cost::EopLabelSuspend);
		SuspendPm4();
		return;
	}
'''
edit(path, anchor, branch+anchor)
edit(base+'novaRenderCosts.h', 'EopLabelPublish, Count',
     'EopLabelPublish, EopLabelPoll, EopLabelSuspend, Count')
edit(base+'novaRenderCosts.h', '"eop_label_publish"}',
     '"eop_label_publish", "eop_label_poll", "eop_label_suspend"}')
for path, text in changes.items():
    (root / path).write_text(text)
print('NOVA_COOPERATIVE_LABEL: Ever PM4 queue yield; real timeline + prior publications; unchanged predicates and fallback')
