#!/usr/bin/env python3
"""Apply after 0976. Preserve GPU completion and guest sample clocks."""
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);pending={}
def edit(name,old,new):
 p=root/name;s=pending.get(p,p.read_text())
 if s.count(old)!=1:raise SystemExit('0978 incompatible anchor: '+name+' '+old[:60])
 pending[p]=s.replace(old,new,1)
bc='src/graphics/host_gpu/renderer/cache/bufferCache.cpp'
edit(bc,'if (!is_written && size <= CACHING_PAGESIZE &&','''// Read-only CPU-owned snapshots use existing completion-tracked stream offsets.
\t// Texel/image transfers preserve their original cache ownership path.
\tif (!is_written && !is_texel_buffer && size <= 64 * 1024 &&''')
edit(bc,'m_graphics.physical_device_properties.limits.minUniformBufferOffsetAlignment, 1);','''std::max<uint64_t>(m_graphics.physical_device_properties.limits.minUniformBufferOffsetAlignment,
\t\t                       m_graphics.physical_device_properties.limits.minStorageBufferOffsetAlignment), 4);''')
im='src/graphics/host_gpu/renderer/image/image.cpp'
edit(im,'''\t\tif (state.layout == destination_layout && state.access_mask == destination_access &&
\t\t    !repeated_write) {
\t\t\treturn {};
\t\t}''','''\t\tif (state.layout == destination_layout && state.access_mask == destination_access &&
\t\t    !repeated_write) {
\t\t\tstate.pl_stage |= destination_stage;
\t\t\tif (NovaReadToRead(state,destination_layout,destination_access)) NovaCountImageBarrier(true);
\t\t\treturn {};
\t\t}''')
# No barriers across different layouts are skipped.
a='src/libs/audio.cpp'
edit(a,'#include "common/novaAudio/QueueWait.h"','#include "common/novaAudio/QueueWait.h"\n#include "common/novaAudio/Float12Stereo.h"')
edit(a,'\tif (port.stereo_fold) {','''\tif (port.stereo_fold && channels==12 && FormatIsFloat(port.format)) {
\t\tNovaAudio::Float12Stereo(static_cast<const float*>(data),reinterpret_cast<float*>(buffer->data()),frames,scales.data());
\t\treturn buffer->data();
\t}
\tif (port.stereo_fold) {''')
edit(a,'LibKernel::KernelGetProcessTime() - wait_start > 200000','LibKernel::KernelGetProcessTime() - wait_start > std::clamp<uint64_t>(buffer_us,1000,20000)')
# Existing timeout recovery clears the stalled SDL stream, resets priming and
# submits the new PCM block. AudioOutOutputs retains its sample-clock pacing.
for p,s in pending.items():p.write_text(s)
shutil.copyfile(repo/'native/audio/Float12Stereo.h',root/'src/common/novaAudio/Float12Stereo.h')
print('0978: bounded snapshots, image reader stages, float12 NEON, bounded SDL stall recovery')
