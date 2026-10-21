#!/usr/bin/env python3
"""0.9.56: readback "off" is no longer the default.

With "off" a CPU write to a page the GPU wrote drops the GPU copy without
downloading it, so when both touched the same page one result erased the other
(the class of bug other Kyty-based Android ports reported: CPU and GPU writes in
shared memory overwriting each other). It also did not raise FPS on device
(0.9.54/0.9.55 owner logs). Default is "relaxed" again: CPU writes download the
GPU data first. "off" stays available only when NOVA_READBACK_MODE=off.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/graphics/host_gpu/novaSync.h'
s = p.read_text()
old = '        return !value || std::string_view(value) == "off";'
new = '        return value && std::string_view(value) == "off"; // 0.9.56: opt-in only'
if s.count(old) != 1:
    raise SystemExit('NOVA_0956_READBACK: anchor changed')
s = s.replace(old, new)
s = s.replace('// "off" (default, shadPS4 GpuReadbacksMode::Disabled)', '// "off" (opt-in since 0.9.56, shadPS4 GpuReadbacksMode::Disabled)')
p.write_text(s)
print('NOVA_0956_READBACK: default readback mode is relaxed; off is opt-in')
