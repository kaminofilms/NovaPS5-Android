#!/usr/bin/env python3
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);pending={}
def edit(name,old,new):
 p=root/name;s=pending.get(p,p.read_text())
 if s.count(old)!=1:raise SystemExit('0983 incompatible anchor '+name+' '+old[:80])
 pending[p]=s.replace(old,new,1)
h='src/graphics/host_gpu/renderer/renderTarget.h'
edit(h,'\tbool                    stencil_clear = false;','\tbool                    stencil_clear = false;\n\tbool                    depth_stencil_read_only = false;')
r='src/graphics/host_gpu/renderer/renderDraw.cpp'
edit(r,'\t\tvk::ImageAspectFlags sampled_aspects;','\t\tvk::ImageAspectFlags sampled_aspects;\n\t\tbool depth_other_binding=false;')
edit(r,'\t\t\t\tif (binding.image_id != depth.image_id ||\n\t\t\t\t    binding.desc.type != TextureCache::BindingType::Texture) continue;','\t\t\t\tif(binding.image_id!=depth.image_id)continue;\n\t\t\t\tif(binding.desc.type!=TextureCache::BindingType::Texture){depth_other_binding=true;continue;}')
edit(r,'\t\t// The attachment store writes even when guest depth/stencil tests do not.\n\t\tconst auto access = vk::AccessFlagBits2::eDepthStencilAttachmentRead |\n\t\t                    vk::AccessFlagBits2::eDepthStencilAttachmentWrite;','''\t\t// A truly read-only native pass needs no attachment store. Keep a stable
\t\t// read superset when shader sampling is toggled, without claiming writes.
\t\tconst bool read_only = !depth_other_binding && NovaRender::CanOmitDepthStore(
\t\t    m_context.GetGraphics().physical_device_properties.apiVersion,NovaRaster::Enabled(),
\t\t    static_cast<VkImageAspectFlags>(draw_writes),depth.depth_load_clear_enable,depth.stencil_clear_enable);
\t\tvk::AccessFlags2 access=vk::AccessFlagBits2::eDepthStencilAttachmentRead;
\t\tif(read_only)access|=vk::AccessFlagBits2::eShaderRead;
\t\telse {access|=vk::AccessFlagBits2::eDepthStencilAttachmentWrite;if(sampled_aspects)access|=vk::AccessFlagBits2::eShaderRead;}''')
edit(r,'\t\tattachment.image_access = access;','\t\tattachment.image_access = access;\n\t\tattachment.depth_stencil_read_only = read_only;')
p=root/r;pending[p]='#include "common/novaRender/ReadOnlyDepth.h"\n'+pending[p]
c='src/graphics/host_gpu/renderer/context.cpp'
edit(c,'\tdepth.storeOp                       = vk::AttachmentStoreOp::eStore;','\tdepth.storeOp = depth_stencil.depth_stencil_read_only ? vk::AttachmentStoreOp::eNone : vk::AttachmentStoreOp::eStore;')
edit(c,'\tstencil.storeOp                         = vk::AttachmentStoreOp::eStore;','\tstencil.storeOp = depth_stencil.depth_stencil_read_only ? vk::AttachmentStoreOp::eNone : vk::AttachmentStoreOp::eStore;')
for p,s in pending.items():p.write_text(s)
(root/'src/common/novaRender').mkdir(parents=True,exist_ok=True)
shutil.copyfile(repo/'native/render/ReadOnlyDepth.h',root/'src/common/novaRender/ReadOnlyDepth.h')
print('0983: guarded read-only STORE_OP_NONE and stable read access; writes/clears/scaled passes preserved')
