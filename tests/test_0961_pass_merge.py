#!/usr/bin/env python3
"""0.9.61: structure of render-pass merging and the Unreal command-line file."""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src'; r = src / 'graphics/host_gpu/renderer'
rh, cx = (r / 'render.h').read_text(), (r / 'context.cpp').read_text()
gr = (src / 'graphics/guest_gpu/graphicsRun.cpp').read_text()
bc, ds = (r / 'cache/bufferCache.cpp').read_text(), (r / 'pipeline/descriptors.cpp').read_text()
rc, fs = (r / 'renderCompute.cpp').read_text(), (src / 'kernel/fileSystem.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


# Barrier: skipped only with an open pass and no storage/dma/dispatch since the last emitted one.
eb = between(gr, 'void CommandProcessor::EmitGlobalBarrier() {', 'CurrentBuffer().Handle().pipelineBarrier2(dependency);')
assert 'bits == 0 && GetScheduler().Active() && CurrentBuffer().NovaRendering()' in eb
assert eb.index('return;') < eb.index('NovaPassMerge::Unsynced().store(0') < eb.index('GetScheduler().EndRendering();')
assert 'std::atomic<uint32_t> bits {kDispatch}' in rh            # first barrier always emitted
assert rc.count('NovaPassMerge::Unsynced().fetch_or(NovaPassMerge::kDispatch') == 2
assert 'fetch_or(NovaPassMerge::kDma' in ds and ds.count('fetch_or(NovaPassMerge::kStorage') == 2
# Deferred work runs at the end of the pass, in order, and before any memory-writing draw.
ep = between(cx, 'void CommandBuffer::EndRendering(std::source_location where) const {', '\n}\n')
assert ep.index('Handle().endRendering();') < ep.index('m_rendering=false;') < ep.index('for (auto& w: work) w(Handle());')
assert 'if (is_written) command.NovaFlushAfterPass();' in bc and 'NovaFlushAfterPass();' in ds
dwf = between(bc, 'const auto record = [source = buffer.Handle()', 'm_scheduler.DeferPriorityOperation([this, job, mapped, offset, total]')
assert 'command.NovaAfterPass(record);' in dwf and 'command.EndRendering();\n\t\trecord(command.Handle());' in dwf
assert 'return v == nullptr || v[0] != \'0\';' in rh                 # NOVA_PASS_MERGE=0 restores 0.9.60
# Unreal: only the root of /app0, only when the dump has no such file, never writes the game folder.
ue = between(fs, 'Unreal picks /app0 as its file root', 'if (Common::IsArchivePath(p.dir)) {\n\t\t\treturn p.dir / native_rel_path;')
assert 'p.point.starts_with("/app0") && rel_path.find(\'/\') == std::string::npos' in ue
assert 'lower == "ue4commandline.txt" || lower == "uecommandline.txt"' in ue
assert ue.index('std::filesystem::exists(own, ec)') < ue.index('std::getenv("NOVA_WORKDIR")')
assert 'std::filesystem::path(work) / ("nova_" + lower)' in ue
print('NOVA_0961_PASS_MERGE: PASS')
