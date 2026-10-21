#!/usr/bin/env python3
"""0.9.56: cheaper internal-resolution passes.

A scaled render pass copies (blits) every attachment from native size down to the
low-resolution copy when the pass begins and back up when it ends. When the pass
clears the attachment, the down-copy is wasted work: the clear overwrites it.
Skip it for cleared colour and depth attachments. The up-copy stays, so every
reader still sees a native-sized image. Each skipped copy is counted in the
NOVA_RESOLUTION_RASTER log line.
"""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0956_RASTER: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


h = src / 'graphics/host_gpu/renderer/image/image.h'
edit(h, ''' vk::ImageView BeginRasterScale(vk::ImageView view, uint32_t width, uint32_t height,
                               vk::ImageLayout restore, vk::CommandBuffer command);''',
     ''' // load=false (the pass clears the attachment): skip the native-to-proxy copy.
 vk::ImageView BeginRasterScale(vk::ImageView view, uint32_t width, uint32_t height,
                               vk::ImageLayout restore, vk::CommandBuffer command, bool load = true);''')

c = src / 'graphics/host_gpu/renderer/image/image.cpp'
edit(c, '''vk::ImageView Image::BeginRasterScale(vk::ImageView, uint32_t width,uint32_t height,
                                     vk::ImageLayout restore,vk::CommandBuffer command) {
 EXIT_IF(!raster_proxy || raster_proxy->backing.extent.width!=width || raster_proxy->backing.extent.height!=height);
 const auto aspect=RasterAspect(*this);
''', '''vk::ImageView Image::BeginRasterScale(vk::ImageView, uint32_t width,uint32_t height,
                                     vk::ImageLayout restore,vk::CommandBuffer command, bool load) {
 EXIT_IF(!raster_proxy || raster_proxy->backing.extent.width!=width || raster_proxy->backing.extent.height!=height);
 const auto aspect=RasterAspect(*this);
 if(!load){
  // Nova 0.9.56: the render pass clears this attachment; nothing to copy in.
  NovaRaster::NoteSkippedCopy();
  RasterTransition(command,*raster_proxy,restore,aspect);
  return raster_proxy->view;
 }
''')
cs = changes[c]
if 'common/novaRasterScale.h' not in cs:
    i = cs.index('#include')
    changes[c] = cs[:i] + '#include "common/novaRasterScale.h"\n' + cs[i:]

ctx = src / 'graphics/host_gpu/renderer/context.cpp'
edit(ctx, '''attachment.raster_owner->BeginRasterScale(attachment.image_view,state.raster_width,state.raster_height,attachment.image_layout,Handle())''',
     '''attachment.raster_owner->BeginRasterScale(attachment.image_view,state.raster_width,state.raster_height,attachment.image_layout,Handle(),!attachment.is_clear)''')
# Depth: skip only when depth is cleared and there is no stencil (scaled passes never have stencil).
edit(ctx, '''depth_stencil.raster_owner->BeginRasterScale(depth_stencil.image_view,state.raster_width,state.raster_height,depth_stencil.image_layout,Handle())''',
     '''depth_stencil.raster_owner->BeginRasterScale(depth_stencil.image_view,state.raster_width,state.raster_height,depth_stencil.image_layout,Handle(),!(depth_stencil.depth_clear && !depth_stencil.has_stencil))''')

rs = src / 'common/novaRasterScale.h'
edit(rs, 'inline void Note(uint32_t w,uint32_t h,uint32_t rw,uint32_t rh){',
     '''inline std::atomic<uint64_t>& SkippedCopies(){static std::atomic<uint64_t> n{0};return n;}
inline void NoteSkippedCopy(){SkippedCopies().fetch_add(1,std::memory_order_relaxed);}
inline void Note(uint32_t w,uint32_t h,uint32_t rw,uint32_t rh){''')
edit(rs, '''native-sized compute/readback preserved\\n",''', '''native-sized compute/readback preserved; cleared_copies_skipped=%llu\\n",''')
edit(rs, '''(unsigned long long)scaled,(unsigned long long)native);''',
     '''(unsigned long long)scaled,(unsigned long long)native,(unsigned long long)SkippedCopies().exchange(0,std::memory_order_relaxed));''')

changes[rs] = '#include <atomic>\n' + changes[rs]

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0956_RASTER: cleared attachments skip the native-to-proxy copy')
