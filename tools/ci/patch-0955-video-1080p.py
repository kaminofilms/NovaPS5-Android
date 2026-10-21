#!/usr/bin/env python3
"""0.9.55 (owner Wonder Boy log, 0.9.54): the game renders at 3840x2160 because
VideoOutGetOutputStatus reports a 4K display to every title. Most of those passes
cannot be raster-scaled; the frame thread waits 4-4.9 s of every 5 s on the GPU
and the GPU then times out (device lost).

1. Report a 1080p display by default (a PS5 on a 1080p TV); NOVA_VIDEO_OUT_4K=1
   restores the previous 4K report.
2. Readback "off": PM4 WAIT_REG_MEM reads guest memory directly, as shadPS4
   does with readbacks disabled. "relaxed" keeps the coherent buffer-cache read.
3. Readback caller telemetry for every title (NOVA_READBACK_TELEMETRY=0 disables).
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]); src = root / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0955: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


vo = src / 'graphics/presentation/videoOut.cpp'
edit(vo, '''	status->resolution =
	    ((attribute3 & 4) != 0 && ctx->width < 3840 && ctx->height < 2160 ? 1u : 2u);''',
     '''	// Nova 0.9.55: report a 1080p display unless NOVA_VIDEO_OUT_4K=1, so titles
	// choose their 1080p render path (4x fewer pixels than 3840x2160).
	static const bool nova_video_4k = [] {
		const char* value = std::getenv("NOVA_VIDEO_OUT_4K");
		const bool enabled = value && value[0] == '1';
		std::fprintf(stderr, "NOVA_VIDEO_OUT: reporting %s display (Graphics > Console video output)\\n",
		             enabled ? "4K" : "1080p");
		return enabled;
	}();
	status->resolution =
	    nova_video_4k ? ((attribute3 & 4) != 0 && ctx->width < 3840 && ctx->height < 2160 ? 1u : 2u) : 1u;''')
vs = changes[vo]
for inc in ('#include <cstdio>', '#include <cstdlib>'):
    if inc not in vs:
        i = vs.index('#include'); vs = vs[:i] + inc + '\n' + vs[i:]
changes[vo] = vs

gr = src / 'graphics/guest_gpu/graphicsRun.cpp'
edit(gr, '	if (NovaRender::GpuLabelProfile() || !NovaSync::PreciseReadbacks()) {',
     '	if (NovaRender::GpuLabelProfile() || (!NovaSync::PreciseReadbacks() && !NovaSync::ReadbackOff())) {')

tel = src / 'graphics/host_gpu/renderer/novaReadbackTelemetry.h'
edit(tel, '''        return (explicit_enable && std::string_view(explicit_enable) == "1") ||
               (title && std::string_view(title) == "PPSA04703");''',
     '''        (void)title;
        // Nova 0.9.55: every title, so each log names the readback callers.
        return !(explicit_enable && std::string_view(explicit_enable) == "0");''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0955: 1080p display report, direct PM4 wait reads with readbacks off, readback telemetry for all titles')
