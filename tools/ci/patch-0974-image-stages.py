#!/usr/bin/env python3
"""Apply after 0971 (also compatible with 0972). Preserve all image hazards."""
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2]
root=Path(sys.argv[1])
p=root/'src/graphics/host_gpu/renderer/image/image.cpp'
s=p.read_text()
old='''\tconst auto transfer_access =
\t    vk::AccessFlagBits2::eTransferRead | vk::AccessFlagBits2::eTransferWrite;
\tvk::PipelineStageFlags2 destination_stage {};
\tif (static_cast<bool>(destination_access & transfer_access)) {
\t\tdestination_stage |= vk::PipelineStageFlagBits2::eTransfer;
\t}
\tif (!destination_access ||
\t    static_cast<bool>(destination_access & ~vk::AccessFlags2 {transfer_access})) {
\t\tdestination_stage |=
\t\t    vk::PipelineStageFlagBits2::eAllGraphics | vk::PipelineStageFlagBits2::eComputeShader;
\t}'''
if s.count(old)!=1:raise SystemExit('0974: Image::Transit stage anchor changed; no files modified')
new='''\tconst vk::PipelineStageFlags2 destination_stage {
\t    NovaRender::ImageStages(static_cast<VkAccessFlags2>(destination_access))};'''
s=s.replace(old,new,1)
s='#include "common/novaRender/ImageStages.h"\n'+s
shutil.copytree(repo/'native/render',root/'src/common/novaRender',dirs_exist_ok=True)
p.write_text(s)
print('NOVA_0974: access-derived image stages; barrier access/layout/range/ordering unchanged')
