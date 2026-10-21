#!/usr/bin/env python3
"""0.9.60: structure of the GPU diagnostics (NOVA_GPU_TIME, NOVA_PASS_BREAK); log only."""
from pathlib import Path
import sys

r = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer'
rh, cx = (r / 'render.h').read_text(), (r / 'context.cpp').read_text()
sh, sc = (r / 'commandScheduler.h').read_text(), (r / 'commandScheduler.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


assert 'void EndRendering(std::source_location where = std::source_location::current()) const;' in rh
assert 'void           EndRendering(std::source_location where = std::source_location::current());' in sh
end = between(cx, 'void CommandBuffer::EndRendering(std::source_location where) const {', 'Handle().endRendering();')
assert end.index('if (!m_rendering)') < end.index('NovaCountPassBreak(where);')   # only real pass ends
assert 'Current().EndRendering(where);' in sc
# Timestamps: raw handle (no m_has_commands change), reset outside a pass at begin, end after EndRendering.
begin = between(sc, 'void CommandScheduler::NovaGpuTimeBegin() {', 'void CommandScheduler::NovaGpuTimeEnd() {')
assert 'static_cast<VkCommandBuffer>(m_command.m_buffer)' in begin and 'Handle()' not in begin
assert begin.index('vkCmdResetQueryPool') < begin.index('VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT')
assert 'VK_QUERY_RESULT_WITH_AVAILABILITY_BIT' in begin and 'std::max(both[0], m_nova_last_end)' in begin
assert 'm_nova_qp_failed = true;' in begin
gend = between(sc, 'void CommandScheduler::NovaGpuTimeEnd() {', '\n}\n')
assert gend.index('m_command.EndRendering();') < gend.index('VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT')
cmd = between(sc, 'CommandBuffer& CommandScheduler::BeginCommand() {', '\n}\n')
assert cmd.index('m_command.Begin();') < cmd.index('NovaGpuTimeBegin();')
sub = between(sc, 'uint64_t CommandScheduler::Submit(SubmitInfo submit) {', 'graphics.queue.submit(')
assert sub.index('NovaGpuTimeEnd();') < sub.index('m_command.End();')
print('NOVA_0960_GPU_DIAG: PASS')
