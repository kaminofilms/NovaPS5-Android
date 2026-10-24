#!/usr/bin/env python3
"""Apply after 0971. Preserve guest backings; add a validated FSR1 presentation pass."""
from pathlib import Path
import shutil,sys
root=Path(sys.argv[1]);repo=Path(__file__).resolve().parents[2];pending={}
def edit(name,old,new):
 p=root/'src'/name;s=pending.get(p,p.read_text())
 if s.count(old)!=1:raise SystemExit('0972 anchor changed: '+name+': '+old[:90])
 pending[p]=s.replace(old,new,1)
sp='graphics/presentation/window/swapchain.cpp'
edit(sp,'#include "common/assert.h"','#include "common/novaUpscale/policy.h"\n#include "common/assert.h"')
edit(sp,'#include "graphics/host_gpu/vulkanCommon.h"','#include "graphics/host_gpu/vulkanCommon.h"\n#include "common/novaUpscale/novaUpscaler.h"')
edit(sp,'\tVulkanImage   image;','\tVulkanImage   image;\n\tVulkanImage   resample; // Native-sized bit-preserving source for sRGB-to-UNORM resizing.')
edit(sp,'\t\tfor (auto& frame: m_frames) {','\t\tfor (auto& frame: m_frames) {\n\t\t\tif(frame->resample.image)m_window.graphic_ctx.DeleteImage(frame->resample);')
p=root/'src'/sp;s=pending[p];start=s.index('void Presenter::Frame::CopyFrom(');end=s.index('\nvoid Presenter::Frame::Clear(',start)
old=s[start:end]
new=r'''void Presenter::Frame::CopyFrom(CommandBuffer& command_buffer, Image& source) {
    command_buffer.EndRendering();
    auto command=command_buffer.Handle();
    source.Transit(vk::ImageLayout::eTransferSrcOptimal,vk::AccessFlagBits2::eTransferRead,{},command);
    Transit(command,vk::ImageLayout::eTransferDstOptimal,vk::AccessFlagBits2::eTransferWrite);
    const bool resize=source.backing.extent.width!=image.extent.width||source.backing.extent.height!=image.extent.height;
    EXIT_IF(source.backing.layers!=image.layers);
    vk::Image input=source.backing.image;
    if(resize&&source.backing.format!=image.format){
        // A direct sRGB -> UNORM blit changes gamma. Copy compatible texel bits
        // into the prepared-frame format first, then resize in perceptual space.
        auto& graphics=command_buffer.GetGraphics();
        if(resample.image&&(resample.extent!=source.backing.extent||resample.format!=image.format))graphics.DeleteImage(resample);
        if(!resample.image){
            vk::ImageCreateInfo ci{};ci.imageType=vk::ImageType::e2D;ci.format=image.format;ci.extent=source.backing.extent;
            ci.mipLevels=1;ci.arrayLayers=1;ci.samples=vk::SampleCountFlagBits::e1;ci.tiling=vk::ImageTiling::eOptimal;
            ci.usage=vk::ImageUsageFlagBits::eTransferSrc|vk::ImageUsageFlagBits::eTransferDst;
            if(!graphics.CreateImage(ci,resample))EXIT("NOVA_PRESENT_SCALE: resample allocation failed\n");
        }
        vk::ImageMemoryBarrier2 b{};b.image=resample.image;b.oldLayout=resample.state.layout;
        b.newLayout=vk::ImageLayout::eTransferDstOptimal;b.srcQueueFamilyIndex=b.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;
        b.subresourceRange={vk::ImageAspectFlagBits::eColor,0,1,0,1};
        b.srcStageMask=resample.state.layout==vk::ImageLayout::eUndefined?vk::PipelineStageFlags2{}:vk::PipelineStageFlagBits2::eAllCommands;
        b.srcAccessMask=resample.state.layout==vk::ImageLayout::eUndefined?vk::AccessFlags2{}:vk::AccessFlagBits2::eMemoryRead|vk::AccessFlagBits2::eMemoryWrite;
        b.dstStageMask=vk::PipelineStageFlagBits2::eTransfer;b.dstAccessMask=vk::AccessFlagBits2::eTransferWrite;
        vk::DependencyInfo dep{};dep.imageMemoryBarrierCount=1;dep.pImageMemoryBarriers=&b;command.pipelineBarrier2(dep);
        vk::ImageCopy cp{};cp.srcSubresource=cp.dstSubresource={vk::ImageAspectFlagBits::eColor,0,0,1};cp.extent=source.backing.extent;
        command.copyImage(source.backing.image,vk::ImageLayout::eTransferSrcOptimal,resample.image,vk::ImageLayout::eTransferDstOptimal,cp);
        b.oldLayout=vk::ImageLayout::eTransferDstOptimal;b.newLayout=vk::ImageLayout::eTransferSrcOptimal;
        b.srcStageMask=b.dstStageMask=vk::PipelineStageFlagBits2::eTransfer;
        b.srcAccessMask=vk::AccessFlagBits2::eTransferWrite;b.dstAccessMask=vk::AccessFlagBits2::eTransferRead;
        command.pipelineBarrier2(dep);resample.state={b.dstStageMask,b.dstAccessMask,b.newLayout};input=resample.image;
    }
    if(resize){
        vk::ImageBlit region{};region.srcSubresource=region.dstSubresource={vk::ImageAspectFlagBits::eColor,0,0,1};
        region.srcOffsets[1]=vk::Offset3D{int32_t(source.backing.extent.width),int32_t(source.backing.extent.height),1};
        region.dstOffsets[1]=vk::Offset3D{int32_t(image.extent.width),int32_t(image.extent.height),1};
        const auto f=command_buffer.GetGraphics().GetFormatProperties(source.backing.format).optimalTilingFeatures;
        const auto filter=(f&vk::FormatFeatureFlagBits::eSampledImageFilterLinear)?vk::Filter::eLinear:vk::Filter::eNearest;
        command.blitImage(input,vk::ImageLayout::eTransferSrcOptimal,image.image,vk::ImageLayout::eTransferDstOptimal,1,&region,filter);
    }else{
        vk::ImageCopy cp{};cp.srcSubresource={vk::ImageAspectFlagBits::eColor,0,0,source.backing.layers};
        cp.dstSubresource={vk::ImageAspectFlagBits::eColor,0,0,image.layers};cp.extent=image.extent;
        command.copyImage(input,vk::ImageLayout::eTransferSrcOptimal,image.image,vk::ImageLayout::eTransferDstOptimal,cp);
    }
}
'''
pending[p]=s[:start]+new+s[end:]
edit(sp,'\tvoid DrawOverlay(vk::CommandBuffer command, const Presenter::Layer& layer);','\tvoid DrawOverlay(vk::CommandBuffer command, const Presenter::Layer& layer);\n\tvk::Image FilterFrame(vk::CommandBuffer command, Presenter::Frame& frame);\n\tNovaUpscale::State m_upscaler;')
edit(sp,'\tif (m_system_overlay != nullptr) {\n\t\tm_system_overlay->ReleaseVulkan();','\tm_upscaler.Reset(); // Queue idle above protects every FSR image/view/pipeline.\n\tif (m_system_overlay != nullptr) {\n\t\tm_system_overlay->ReleaseVulkan();')
helper=r'''
vk::Image Swapchain::FilterFrame(vk::CommandBuffer command, Presenter::Frame& frame) {
    if(!NovaUpscale::Fsr(frame.image.extent.width,frame.image.extent.height,m_extent.width,m_extent.height,frame.hdr||m_hdr_active))return nullptr;
    auto& g=m_window.graphic_ctx;
    const auto f=frame.image.format;
    const bool color8=f==vk::Format::eR8G8B8A8Unorm||f==vk::Format::eB8G8R8A8Unorm||f==vk::Format::eR8G8B8A8Srgb||f==vk::Format::eB8G8R8A8Srgb;
    const auto features=g.GetFormatProperties(vk::Format::eR16G16B16A16Sfloat).optimalTilingFeatures;
    const auto needed=vk::FormatFeatureFlagBits::eStorageImage|vk::FormatFeatureFlagBits::eSampledImage|vk::FormatFeatureFlagBits::eBlitSrc;
    if(!color8||(features&needed)!=needed||!m_upscaler.Prepare(g.device,g.GetPhysicalDeviceMemoryProperties(),m_extent,ImageCount(),m_image_index)){
        static bool noted=false;if(!noted){std::fprintf(stderr,"NOVA_FSR: bilinear fallback (source format, capabilities or allocation)\n");noted=true;}return nullptr;
    }
    if(!frame.view){
        vk::ImageViewCreateInfo vi{};vi.image=frame.image.image;vi.viewType=vk::ImageViewType::e2D;vi.format=f;
        vi.subresourceRange={vk::ImageAspectFlagBits::eColor,0,1,0,1};
        if(g.device.createImageView(&vi,nullptr,&frame.view)!=vk::Result::eSuccess)return nullptr;
    }
    frame.Transit(command,vk::ImageLayout::eShaderReadOnlyOptimal,vk::AccessFlagBits2::eShaderRead);
    static bool noted=false;if(!noted){std::fprintf(stderr,"NOVA_FSR: AMD EASU + RCAS input=%ux%u output=%ux%u sharpness=%u; spatial upscale, not generated frames\n",frame.image.extent.width,frame.image.extent.height,m_extent.width,m_extent.height,NovaUpscale::Sharpness());noted=true;}
    return m_upscaler.Record(command,m_image_index,frame.view,{frame.image.extent.width,frame.image.extent.height},
        f==vk::Format::eR8G8B8A8Srgb||f==vk::Format::eB8G8R8A8Srgb,
        m_format==vk::Format::eR8G8B8A8Srgb||m_format==vk::Format::eB8G8R8A8Srgb,NovaUpscale::Sharpness());
}
'''
edit(sp,'void Swapchain::RecordPresentCommands(',helper+'\nvoid Swapchain::RecordPresentCommands(')
edit(sp,'\tif (source != nullptr) {\n\t\tsource->Transit(vk_command,','\tconst auto filtered=source?FilterFrame(vk_command,*source):vk::Image{};\n\tif (source != nullptr && !filtered) {\n\t\tsource->Transit(vk_command,')
edit(sp,'static_cast<int>(source->image.extent.width);','static_cast<int>(filtered?m_extent.width:source->image.extent.width);')
edit(sp,'static_cast<int>(source->image.extent.height);','static_cast<int>(filtered?m_extent.height:source->image.extent.height);')
edit(sp,'vk_command.blitImage(source->image.image, vk::ImageLayout::eTransferSrcOptimal,','vk_command.blitImage(filtered?filtered:source->image.image, vk::ImageLayout::eTransferSrcOptimal,')
edit(sp,'&region, vk::Filter::eLinear);','&region, filtered||NovaUpscale::Filter()==0?vk::Filter::eNearest:vk::Filter::eLinear);')
edit(sp,'submit.AddWait(m_image_acquired[m_frame_index], 1, vk::PipelineStageFlagBits::eTransfer);','submit.AddWait(m_image_acquired[m_frame_index], 1, vk::PipelineStageFlagBits::eAllCommands);')
edit(sp,'auto* frame = m_impl->frames.Acquire({info.extent.width, info.extent.height}, frame_format);',
'''const auto requested=NovaUpscale::Extent(info.extent.width,info.extent.height,NovaUpscale::Height());
    auto* frame = m_impl->frames.Acquire({requested.first,requested.second}, frame_format);''')
edit(sp,'''\tframe->Configure(m_impl->window.graphic_ctx,
\t                 {image.backing.extent.width, image.backing.extent.height}, frame_format);''',
'''    auto target=NovaUpscale::Extent(image.backing.extent.width,image.backing.extent.height,NovaUpscale::Height());
    const auto srcFeatures=m_impl->window.graphic_ctx.GetFormatProperties(image.backing.format).optimalTilingFeatures;
    const auto dstFeatures=m_impl->window.graphic_ctx.GetFormatProperties(frame_format).optimalTilingFeatures;
    if(!(srcFeatures&vk::FormatFeatureFlagBits::eBlitSrc)||!(dstFeatures&vk::FormatFeatureFlagBits::eBlitDst)||image.backing.layers!=1)
        target={image.backing.extent.width,image.backing.extent.height};
    frame->Configure(m_impl->window.graphic_ctx,{target.first,target.second},frame_format);''')
# Resolution policy: use temporary raster proxies; never replace a guest backing
# during binding/descriptor preparation. Compute/readback see their original image.
edit('common/novaRasterScale.h','#include "common/novaRescale.h"','#include "common/novaRescale.h"\n#include "common/novaUpscale/policy.h"')
edit('common/novaRasterScale.h','inline bool Enabled(){return NovaRescale::Enabled() || ScalePct()<100;}',
     'inline bool Enabled(){return NovaRescale::Enabled() || NovaUpscale::Height()>0 || ScalePct()<100;}')
edit('common/novaRasterScale.h',' const uint32_t rw=(w*ScalePct()/100)&~1u, rh=(h*ScalePct()/100)&~1u;',
''' if(NovaUpscale::Height()) {const auto e=NovaUpscale::Extent(w,h,NovaUpscale::Height());return e.second<h?e:std::pair<uint32_t,uint32_t>{};}
 const uint32_t rw=(w*ScalePct()/100)&~1u, rh=(h*ScalePct()/100)&~1u;''')
# The fragment-coordinate/push-constant ABI differs from 0.9.71 native mode.
# Never load an old shader disk entry with a different raster ABI.
edit('graphics/host_gpu/renderer/pipeline/pipelineCache.cpp',
     'signature + (NovaRescale::Enabled()?":rescale64":":native64")',
     'signature + (NovaRaster::Enabled()?":raster72":":native72")')
# Log the real Vulkan result, without treating a failed/timed-out wait as completed.
ms='graphics/host_gpu/renderer/masterSemaphore.cpp'
edit(ms,'#include "common/assert.h"','#include "common/assert.h"\n#include <cstdio>')
edit(ms,'\tconst auto result = m_graphics.device.waitSemaphores(&wait_info, UINT64_MAX);',
'''\tconst auto result = m_graphics.device.waitSemaphores(&wait_info, UINT64_MAX);
    if(result!=vk::Result::eSuccess)std::fprintf(stderr,"NOVA_GPU_WAIT_ERROR: operation=waitSemaphores result=%d requested=%llu completed=%llu\\n",int(result),(unsigned long long)tick,(unsigned long long)m_gpu_tick.load());''')
# Anisotropy override only affects samplers that already request anisotropic
# filtering; keep integer, point and unnormalized-coordinate sampling untouched.
sc='graphics/host_gpu/renderer/cache/samplerCache.cpp'
edit(sc,'#include "common/assert.h"','#include "common/assert.h"\n#include "common/novaUpscale/policy.h"')
edit(sc,'\tsampler_info.maxAnisotropy           = aniso_ratio;',
'''    const auto requestedAniso=NovaUpscale::Setting("NOVA_ANISOTROPY",0,16);
    if(aniso&&requestedAniso)aniso_ratio=std::min(float(requestedAniso),m_graphics.GetPhysicalDeviceProperties().limits.maxSamplerAnisotropy);
\tsampler_info.maxAnisotropy           = aniso_ratio;''')
for p,s in pending.items():p.write_text(s)
shutil.copytree(repo/'native/upscale',root/'src/common/novaUpscale',dirs_exist_ok=True)
print('NOVA_0972: temporary raster targets, native-sized guest images, exact output resolution, AMD EASU/RCAS, anisotropy and Vulkan error evidence')
