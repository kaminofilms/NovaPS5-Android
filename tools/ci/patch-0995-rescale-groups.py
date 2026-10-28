#!/usr/bin/env python3
"""Render-pass-group scaling: scale depth with colour, and scale images that started native.

0.9.109 on Wonder Boy (Render resolution 720p): only 8 images were ever scaled. Depth buffers are
never allocated scaled (and images first seen as textures or CPU uploads are created native), so
every pass that combined a scaled colour target with a native depth buffer demoted the colour
target back to 4K ("mixed-pass-or-side-effect"); full-image CPU uploads demoted the rest ("upload").

Approach (same idea as yuzu's resolution scaler, implemented independently for Kyty's image
model): decide per render pass. When a pass without shader side effects binds targets that are
all eligible for the same scale (same guest size, 2D, single layer/level/sample, blit-capable
format, no hard native use), every native one is scaled down in place (blit; linear for colour,
nearest for depth/stencil), so colour and depth stay compatible. An image is scaled only after it
was eligible in 2 passes, and is never re-scaled after a hard native use (storage, readback,
copies, resolves, descriptor fallbacks, partial uploads) or after 3 soft demotions; a soft
demotion also blocks re-scaling for 600 submissions. A CPU upload covering the whole image is
staged in a native-size temporary and blitted down, instead of demoting the image.
Everything else is the existing rescale path (per-binding guest/host sizes, viewport/scissor
scaling, native fallbacks).
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer'
changes = {}

def edit(path, old, new):
    s = changes.get(path, path.read_text())
    if s.count(old) != 1:
        raise SystemExit(f'0995: {path.name} anchor changed ({s.count(old)}): {old[:70]!r}; no source written')
    changes[path] = s.replace(old, new, 1)

ih = root / 'image/image.h'
im = root / 'image/image.cpp'
rd = root / 'renderDraw.cpp'

edit(ih, '\tvoid NovaNative(const char* reason);\n', '''	void NovaNative(const char* reason);
	// Nova 0995: render-pass-group scaling state (see tools/ci/patch-0995-rescale-groups.py).
	bool     NovaCanScale(uint32_t permille) const { return NovaScaleBlocker(permille) == nullptr; }
	const char* NovaScaleBlocker(uint32_t permille) const;
	bool     NovaScaleDown(uint32_t permille);
	bool     nova_hard_native     = false;
	uint32_t nova_soft_demotions  = 0;
	uint32_t nova_eligible_passes = 0;
	uint64_t nova_block_until     = 0;
''')

# Demotion bookkeeping runs even when the image is already native (a hard use must stop later scaling).
edit(im, 'void Image::NovaNative(const char* reason) {\n\tif (!NovaScaled()) return;\n',
     '''void Image::NovaNative(const char* reason) {
	{
		const std::string_view why(reason);
		if (why == "mixed-pass-or-side-effect" || why == "attachment-refresh-mismatch") {
			if (NovaScaled()) {
				++nova_soft_demotions;
				nova_block_until = m_scheduler.CurrentTick() + 600;
			}
		} else {
			nova_hard_native = true;
		}
	}
	if (!NovaScaled()) return;
''')

helpers = r'''
const char* Image::NovaScaleBlocker(uint32_t permille) const {
	if (permille >= 1000) return "no-scale-wanted";
	if (nova_hard_native) return "hard-native";
	if (nova_soft_demotions >= 3) return "demoted-3x";
	if (depth_id) return "depth-association";
	if (m_scheduler.CurrentTick() < nova_block_until) return "backoff";
	if (info.type != Prospero::ImageType::kColor2D) return "image-type";
	if (info.IsBlock()) return "block-format";
	if (info.resources.layers != 1) return "layers";
	if (info.resources.levels != 1) return "mip-levels";
	if (info.samples != 1) return "msaa";
	const NovaRescale::Candidate candidate {info.extent.width, info.extent.height, info.extent.depth,
	    info.resources.layers, info.resources.levels, info.samples, true, false, false, false};
	if (!NovaRescale::Eligible(candidate, permille)) return "size";
	const auto features = m_graphics.GetFormatProperties(backing.format).optimalTilingFeatures;
	if (!(features & vk::FormatFeatureFlagBits::eBlitSrc)) return "format-no-blit-src";
	if (!(features & vk::FormatFeatureFlagBits::eBlitDst)) return "format-no-blit-dst";
	if (backing.layers != 1 || backing.mip_levels != 1) return "backing-layers-or-mips";
	return nullptr;
}

bool Image::NovaScaleDown(uint32_t permille) {
	if (NovaScaled() || !NovaCanScale(permille)) return false;
	m_scheduler.EndRendering();
	auto create   = nova_create_info;
	create.extent = {NovaRescale::Dimension(info.extent.width, permille), NovaRescale::Dimension(info.extent.height, permille), 1};
	if (create.extent.width >= info.extent.width || create.extent.height >= info.extent.height) return false;
	VulkanImage replacement {};
	if (!m_graphics.CreateImage(create, replacement)) return false;
	auto command = m_scheduler.Current().Handle();
	Transit(vk::ImageLayout::eTransferSrcOptimal, vk::AccessFlagBits2::eTransferRead, {}, command);
	vk::ImageMemoryBarrier2 barrier {};
	barrier.dstStageMask        = vk::PipelineStageFlagBits2::eAllTransfer;
	barrier.dstAccessMask       = vk::AccessFlagBits2::eTransferWrite;
	barrier.oldLayout           = vk::ImageLayout::eUndefined;
	barrier.newLayout           = vk::ImageLayout::eTransferDstOptimal;
	barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
	barrier.image               = replacement.image;
	barrier.subresourceRange    = {FullAspectMask(backing.format), 0, 1, 0, 1};
	vk::DependencyInfo dependency {};
	dependency.imageMemoryBarrierCount = 1;
	dependency.pImageMemoryBarriers    = &barrier;
	command.pipelineBarrier2(dependency);
	const auto aspects  = FullAspectMask(backing.format);
	const auto features = m_graphics.GetFormatProperties(backing.format).optimalTilingFeatures;
	const bool linear   = (aspects & vk::ImageAspectFlagBits::eColor) &&
	                    (features & vk::FormatFeatureFlagBits::eSampledImageFilterLinear);
	for (auto aspect: {vk::ImageAspectFlagBits::eColor, vk::ImageAspectFlagBits::eDepth, vk::ImageAspectFlagBits::eStencil}) {
		if (!(aspects & aspect)) continue;
		vk::ImageBlit region {};
		region.srcSubresource = {aspect, 0, 0, 1};
		region.dstSubresource = {aspect, 0, 0, 1};
		region.srcOffsets[1]  = vk::Offset3D {int32_t(backing.extent.width), int32_t(backing.extent.height), 1};
		region.dstOffsets[1]  = vk::Offset3D {int32_t(create.extent.width), int32_t(create.extent.height), 1};
		command.blitImage(backing.image, vk::ImageLayout::eTransferSrcOptimal, replacement.image,
		                  vk::ImageLayout::eTransferDstOptimal, 1, &region, linear ? vk::Filter::eLinear : vk::Filter::eNearest);
	}
	replacement.state = {vk::PipelineStageFlagBits2::eAllTransfer, vk::AccessFlagBits2::eTransferWrite,
	                     vk::ImageLayout::eTransferDstOptimal};
	auto previous   = std::make_shared<VulkanImage>();
	auto swap_image = [](VulkanImage& a, VulkanImage& b) {
		using std::swap;
		swap(a.format, b.format);swap(a.image_type, b.image_type);swap(a.extent, b.extent);
		swap(a.layers, b.layers);swap(a.mip_levels, b.mip_levels);swap(a.samples, b.samples);
		swap(a.usage, b.usage);swap(a.flags, b.flags);swap(a.image, b.image);
		swap(a.state, b.state);swap(a.subresource_states, b.subresource_states);swap(a.allocation, b.allocation);
	};
	swap_image(*previous, backing);
	auto previous_views = std::move(views);
	views.clear();
	swap_image(backing, replacement);
	nova_permille  = permille;
	auto* graphics = &m_graphics;
	m_scheduler.DeferOperation([graphics, previous, previous_views = std::move(previous_views)]() mutable {
		for (const auto& v: previous_views) if (v.view) graphics->device.destroyImageView(v.view, nullptr);
		graphics->DeleteImage(*previous);
	});
	NovaRescale::Note(true, (aspects & vk::ImageAspectFlagBits::eColor) ? "pass-scale-color" : "pass-scale-depth");
	return true;
}

'''
edit(im, '\nvoid Image::NovaNative(const char* reason) {', helpers + 'void Image::NovaNative(const char* reason) {')

# Full-image CPU upload into a scaled image: stage at native size, then blit down.
edit(im, '''void Image::Upload(std::span<const vk::BufferImageCopy> copies, vk::Buffer buffer, uint64_t offset,
                   uint64_t size) {
	NovaNative("upload");
''', '''void Image::Upload(std::span<const vk::BufferImageCopy> copies, vk::Buffer buffer, uint64_t offset,
                   uint64_t size) {
	if (NovaScaled() && copies.size() == 1 && copies[0].imageOffset == vk::Offset3D {0, 0, 0} &&
	    copies[0].imageExtent.width == info.extent.width && copies[0].imageExtent.height == info.extent.height &&
	    copies[0].imageSubresource.mipLevel == 0 && copies[0].imageSubresource.baseArrayLayer == 0 &&
	    copies[0].imageSubresource.layerCount == 1 && buffer != nullptr && size != 0) {
		// Nova 0995: a whole-image upload keeps the scale (native staging image, blitted down).
		m_scheduler.EndRendering();
		auto create   = nova_create_info;
		create.extent = info.extent;
		create.usage |= vk::ImageUsageFlagBits::eTransferSrc | vk::ImageUsageFlagBits::eTransferDst;
		auto staging = std::make_shared<VulkanImage>();
		if (m_graphics.CreateImage(create, *staging)) {
			auto command = m_scheduler.Current().Handle();
			vk::BufferMemoryBarrier2 source_barrier {};
			source_barrier.srcStageMask  = vk::PipelineStageFlagBits2::eAllCommands;
			source_barrier.srcAccessMask = vk::AccessFlagBits2::eMemoryWrite;
			source_barrier.dstStageMask  = vk::PipelineStageFlagBits2::eTransfer;
			source_barrier.dstAccessMask = vk::AccessFlagBits2::eTransferRead;
			source_barrier.srcQueueFamilyIndex = source_barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
			source_barrier.buffer = buffer;
			source_barrier.offset = offset;
			source_barrier.size   = size;
			vk::ImageMemoryBarrier2 stage_barrier {};
			stage_barrier.dstStageMask  = vk::PipelineStageFlagBits2::eAllTransfer;
			stage_barrier.dstAccessMask = vk::AccessFlagBits2::eTransferWrite;
			stage_barrier.oldLayout     = vk::ImageLayout::eUndefined;
			stage_barrier.newLayout     = vk::ImageLayout::eTransferDstOptimal;
			stage_barrier.srcQueueFamilyIndex = stage_barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
			stage_barrier.image            = staging->image;
			stage_barrier.subresourceRange = {FullAspectMask(backing.format), 0, 1, 0, 1};
			vk::DependencyInfo dependency {};
			dependency.bufferMemoryBarrierCount = 1;
			dependency.pBufferMemoryBarriers    = &source_barrier;
			dependency.imageMemoryBarrierCount  = 1;
			dependency.pImageMemoryBarriers     = &stage_barrier;
			command.pipelineBarrier2(dependency);
			command.copyBufferToImage(buffer, staging->image, vk::ImageLayout::eTransferDstOptimal, 1, copies.data());
			stage_barrier.srcStageMask  = vk::PipelineStageFlagBits2::eAllTransfer;
			stage_barrier.srcAccessMask = vk::AccessFlagBits2::eTransferWrite;
			stage_barrier.dstAccessMask = vk::AccessFlagBits2::eTransferRead;
			stage_barrier.oldLayout     = vk::ImageLayout::eTransferDstOptimal;
			stage_barrier.newLayout     = vk::ImageLayout::eTransferSrcOptimal;
			source_barrier.srcStageMask  = vk::PipelineStageFlagBits2::eTransfer;
			source_barrier.srcAccessMask = vk::AccessFlagBits2::eTransferRead;
			source_barrier.dstStageMask  = vk::PipelineStageFlagBits2::eAllCommands;
			source_barrier.dstAccessMask = vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite;
			command.pipelineBarrier2(dependency);
			Transit(vk::ImageLayout::eTransferDstOptimal, vk::AccessFlagBits2::eTransferWrite, {}, command);
			const auto aspects  = FullAspectMask(backing.format);
			const auto features = m_graphics.GetFormatProperties(backing.format).optimalTilingFeatures;
			const bool linear   = (aspects & vk::ImageAspectFlagBits::eColor) &&
			                    (features & vk::FormatFeatureFlagBits::eSampledImageFilterLinear);
			for (auto aspect: {vk::ImageAspectFlagBits::eColor, vk::ImageAspectFlagBits::eDepth, vk::ImageAspectFlagBits::eStencil}) {
				if (!(aspects & aspect)) continue;
				vk::ImageBlit region {};
				region.srcSubresource = {aspect, 0, 0, 1};
				region.dstSubresource = {aspect, 0, 0, 1};
				region.srcOffsets[1]  = vk::Offset3D {int32_t(info.extent.width), int32_t(info.extent.height), 1};
				region.dstOffsets[1]  = vk::Offset3D {int32_t(backing.extent.width), int32_t(backing.extent.height), 1};
				command.blitImage(staging->image, vk::ImageLayout::eTransferSrcOptimal, backing.image,
				                  vk::ImageLayout::eTransferDstOptimal, 1, &region, linear ? vk::Filter::eLinear : vk::Filter::eNearest);
			}
			Transit(vk::ImageLayout::eGeneral, vk::AccessFlagBits2::eShaderRead | vk::AccessFlagBits2::eTransferRead, {}, command);
			auto* graphics = &m_graphics;
			m_scheduler.DeferOperation([graphics, staging]() mutable { graphics->DeleteImage(*staging); });
			NovaRescale::Note(true, "upload-staged");
			return;
		}
	}
	NovaNative("upload");
''')

# Pass rule: scale every eligible native target of a compatible pass instead of demoting.
old = '''		bool native = false;
		for (const auto* stage : stages) {
			if(stage->runtime->program->has_address_writes || HasShaderBufferWrites(*stage->runtime)) native=true;
			for(const auto& r:stage->runtime->program->info.images) if(r.written) native=true;
		}
'''
new = old + '''		// Nova 0995: when the whole pass can share one scale, scale its native targets
		// (colour and depth) instead of demoting the scaled ones.
		// Why passes do not scale, reported every 5 s (NOVA_RESCALE_GROUP).
		struct GroupStats {
			std::map<std::string, uint64_t> reasons;
			uint64_t passes = 0, grouped = 0;
			std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
		};
		static GroupStats group_stats;
		const auto note_reason = [&](const std::string& why) { ++group_stats.reasons[why]; };
		++group_stats.passes;
		if (native) note_reason("shader-side-effects");
		if (!native && count != 0) {
			const uint32_t wanted = NovaRescale::PermilleFor(targets[0]->info.extent.height);
			bool group = wanted < 1000;
			if (!group) note_reason("first-target-not-taller-than-target-height");
			for (uint32_t i = 0; group && i < count; i++) {
				const auto& t = *targets[i];
				const bool depth = i + 1 == count && state.depth_info.image_id;
				if (t.info.extent.width != targets[0]->info.extent.width || t.info.extent.height != targets[0]->info.extent.height) {
					group = false; note_reason("attachment-sizes-differ");
				} else if (t.NovaScaled() ? t.nova_permille != wanted : !t.NovaCanScale(wanted)) {
					group = false;
					const char* why = t.NovaScaled() ? "different-scale" : t.NovaScaleBlocker(wanted);
					note_reason(std::string(depth ? "depth:" : "color:") + why +
					            (why && std::string_view(why).starts_with("format") ? "(vkformat " + std::to_string(int(t.backing.format)) + ")" : ""));
				}
			}
			if (group) ++group_stats.grouped;
			if (group) {
				bool ready = true;
				for (uint32_t i = 0; i < count; i++) if (!targets[i]->NovaScaled() && ++targets[i]->nova_eligible_passes < 2) ready = false;
				for (uint32_t i = 0; ready && i < count; i++) if (!targets[i]->NovaScaled()) (void)targets[i]->NovaScaleDown(wanted);
			}
		}
		if (const auto now = std::chrono::steady_clock::now(); now - group_stats.start >= std::chrono::seconds(5)) {
			std::string line;
			std::vector<std::pair<uint64_t, std::string>> top;
			for (const auto& [why, n]: group_stats.reasons) top.emplace_back(n, why);
			std::sort(top.rbegin(), top.rend());
			for (size_t k = 0; k < top.size() && k < 8; ++k) line += " " + top[k].second + "=" + std::to_string(top[k].first);
			std::fprintf(stderr, "NOVA_RESCALE_GROUP: passes=%llu groupable=%llu%s\\n", (unsigned long long)group_stats.passes,
			             (unsigned long long)group_stats.grouped, line.c_str());
			group_stats = {};
			group_stats.start = now;
		}
'''
edit(rd, old, new)

for path, s in changes.items():
    if path == im and '#include <string_view>' not in s:
        s = '#include <string_view>\n' + s
    if path == rd:
        for header in ('#include <map>', '#include <string>', '#include <string_view>', '#include <chrono>', '#include <algorithm>', '#include <vector>'):
            if header not in s:
                s = header + '\n' + s
    path.write_text(s)
print('0995: render-pass-group scaling (depth with colour, scale-down of native targets, staged full uploads)')
