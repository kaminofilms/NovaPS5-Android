#!/usr/bin/env python3
"""Keep writable depth layouts for unbound, whole, unsampled attachments only."""
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1])
p=root/'src/graphics/host_gpu/renderer/renderDraw.cpp';s=p.read_text()
old='\t\tauto layout = depth_attachment_layout(depth);\n\t\tif (sampled_aspects & ~DepthReadableAspects(layout)) {'
if s.count(old)!=1:raise SystemExit('0974 stable depth anchor changed; no source written')
new='''\t\tauto layout = depth_attachment_layout(depth);
        static const bool stable_enabled=[] {const auto* v=std::getenv("NOVA_STABLE_DEPTH");return v&&v[0]=='1';}();
        const auto& stable_view=depth.desc.view_info;
        const bool stable_whole=stable_enabled && stable_view.base_level==0 && stable_view.base_layer==0 &&
            stable_view.level_count==image.info.resources.levels &&
            stable_view.layer_count==image.info.resources.layers && image.backing.subresource_states.empty();
        const auto stable=NovaRender::StableDepthLayout(
            static_cast<VkImageLayout>(image.backing.state.layout),static_cast<VkImageLayout>(layout),
            static_cast<VkImageAspectFlags>(ImageViewOps::DepthAspectMask(stable_view.format)),
            static_cast<bool>(sampled_aspects),image.binding.is_bound,stable_whole);
        if(stable!=static_cast<VkImageLayout>(layout)){
            layout=static_cast<vk::ImageLayout>(stable);
            static thread_local uint64_t retained=0;
            if((++retained&4095u)==0)std::fprintf(stderr,"NOVA_DEPTH_STABLE: layout_choices_retained=%llu; not measured pass savings\\n",(unsigned long long)retained);
        }
\t\tif (sampled_aspects & ~DepthReadableAspects(layout)) {'''
s='#include "common/novaRender/StableDepth.h"\n#include <cstdlib>\n'+s.replace(old,new,1)
shutil.copytree(repo/'native/render',root/'src/common/novaRender',dirs_exist_ok=True)
p.write_text(s)
print('NOVA_DEPTH_STABLE: whole unsampled/unbound writable depth layouts retained; pipeline writes, access barriers and feedback path unchanged')
