#!/usr/bin/env python3
"""Presentation upscaling filter: Bilinear (default) / Bicubic / Sharp (ScaleForce-style).

The final stretch of the game frame to the phone screen used vkCmdBlitImage with linear filtering.
NOVA_PRESENT_FILTER=bicubic|sharp draws that stretch with native/render/shaders/gpu_present_filter.frag
instead (Catmull-Rom; "sharp" clamps to the source neighbourhood, so edges stay crisp without
halos, the goal of yuzu's ScaleForce option). Only the presentation copy changes; HDR output and
same-size frames keep the blit. The swapchain image returns to TRANSFER_DST afterwards, so the
existing overlay/present barriers are unchanged.
"""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1])
repo = Path(__file__).resolve().parents[2]
sc = root / 'src/graphics/presentation/window/swapchain.cpp'
cm = root / 'CMakeLists.txt'
s, c = sc.read_text(), cm.read_text()

def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f'0997: {what} anchor changed ({text.count(old)}); no source written')
    return text.replace(old, new, 1)

c = once(c, 'add_gpu_blit_shader(gpu_video_out_overlay gpu_video_out_overlay.frag)\n',
         'add_gpu_blit_shader(gpu_video_out_overlay gpu_video_out_overlay.frag)\n'
         'add_gpu_blit_shader(gpu_present_filter gpu_present_filter.frag)\n', 'CMake blit shader list')
s = once(s, '#include "gpu_blit_shaders/gpu_video_out_overlay_spv.h"\n',
         '#include "gpu_blit_shaders/gpu_video_out_overlay_spv.h"\n#include "gpu_blit_shaders/gpu_present_filter_spv.h"\n', 'swapchain includes')
s = once(s, '\tvk::Sampler                    m_overlay_sampler     = nullptr;\n',
         '\tvk::Sampler                    m_overlay_sampler     = nullptr;\n'
         '\t// Nova 0997: presentation filter pipeline (lazily created for the current swapchain format).\n'
         '\tvk::DescriptorSetLayout        m_filter_descriptors  = nullptr;\n'
         '\tvk::PipelineLayout             m_filter_layout       = nullptr;\n'
         '\tvk::Pipeline                   m_filter_pipeline     = nullptr;\n'
         '\tvk::Sampler                    m_filter_sampler      = nullptr;\n'
         '\tbool NovaFilterPresent(vk::CommandBuffer command, Presenter::Frame& source, uint32_t mode);\n', 'swapchain members')
s = once(s, '\tm_overlay_pipeline    = nullptr;\n\tm_overlay_layout      = nullptr;\n\tm_overlay_descriptors = nullptr;\n\tm_overlay_sampler     = nullptr;\n',
         '\tm_overlay_pipeline    = nullptr;\n\tm_overlay_layout      = nullptr;\n\tm_overlay_descriptors = nullptr;\n\tm_overlay_sampler     = nullptr;\n'
         '\tgraphics.device.destroyPipeline(m_filter_pipeline, nullptr);\n'
         '\tgraphics.device.destroyPipelineLayout(m_filter_layout, nullptr);\n'
         '\tgraphics.device.destroyDescriptorSetLayout(m_filter_descriptors, nullptr);\n'
         '\tgraphics.device.destroySampler(m_filter_sampler, nullptr);\n'
         '\tm_filter_pipeline = nullptr;\n\tm_filter_layout = nullptr;\n\tm_filter_descriptors = nullptr;\n\tm_filter_sampler = nullptr;\n', 'swapchain cleanup')

old_blit_head = '''	if (source != nullptr) {
		vk::ImageBlit region {};
		region.srcSubresource.aspectMask     = vk::ImageAspectFlagBits::eColor;'''
s = once(s, old_blit_head, '''	static const uint32_t nova_filter_mode = [] {
		const char* value = std::getenv("NOVA_PRESENT_FILTER");
		const std::string_view mode = value ? value : "";
		return mode == "bicubic" ? 1u : mode == "sharp" ? 2u : 0u;
	}();
	if (source != nullptr && nova_filter_mode != 0 && !m_hdr_active &&
	    (source->image.extent.width != m_extent.width || source->image.extent.height != m_extent.height) &&
	    NovaFilterPresent(vk_command, *source, nova_filter_mode)) {
	} else if (source != nullptr) {
		source->Transit(vk_command, vk::ImageLayout::eTransferSrcOptimal, vk::AccessFlagBits2::eTransferRead);
		vk::ImageBlit region {};
		region.srcSubresource.aspectMask     = vk::ImageAspectFlagBits::eColor;''', 'present blit')

method = r'''
bool Swapchain::NovaFilterPresent(vk::CommandBuffer command, Presenter::Frame& source, uint32_t mode) {
	auto device = m_window.graphic_ctx.device;
	if (m_filter_pipeline == nullptr) {
		vk::SamplerCreateInfo sampler {};
		sampler.magFilter    = vk::Filter::eNearest;
		sampler.minFilter    = vk::Filter::eNearest;
		sampler.addressModeU = sampler.addressModeV = sampler.addressModeW = vk::SamplerAddressMode::eClampToEdge;
		if (device.createSampler(&sampler, nullptr, &m_filter_sampler) != vk::Result::eSuccess) return false;
		const vk::DescriptorSetLayoutBinding binding {0, vk::DescriptorType::eCombinedImageSampler, 1, vk::ShaderStageFlagBits::eFragment};
		vk::DescriptorSetLayoutCreateInfo descriptors {};
		descriptors.flags        = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR;
		descriptors.bindingCount = 1;
		descriptors.pBindings    = &binding;
		if (device.createDescriptorSetLayout(&descriptors, nullptr, &m_filter_descriptors) != vk::Result::eSuccess) return false;
		const vk::PushConstantRange push {vk::ShaderStageFlagBits::eFragment, 0, sizeof(uint32_t)};
		vk::PipelineLayoutCreateInfo layout {};
		layout.setLayoutCount         = 1;
		layout.pSetLayouts            = &m_filter_descriptors;
		layout.pushConstantRangeCount = 1;
		layout.pPushConstantRanges    = &push;
		if (device.createPipelineLayout(&layout, nullptr, &m_filter_layout) != vk::Result::eSuccess) return false;
		const auto vertex   = CompileSPV(GPU_BLIT_FS_TRIANGLE_SPV, device);
		const auto fragment = CompileSPV(GPU_PRESENT_FILTER_SPV, device);
		std::array<vk::PipelineShaderStageCreateInfo, 2> stages {};
		stages[0].stage  = vk::ShaderStageFlagBits::eVertex;
		stages[0].module = vertex;
		stages[0].pName  = "main";
		stages[1].stage  = vk::ShaderStageFlagBits::eFragment;
		stages[1].module = fragment;
		stages[1].pName  = "main";
		vk::PipelineVertexInputStateCreateInfo   vertex_input {};
		vk::PipelineInputAssemblyStateCreateInfo assembly {};
		assembly.topology = vk::PrimitiveTopology::eTriangleList;
		vk::PipelineViewportStateCreateInfo viewport {};
		viewport.viewportCount = 1;
		viewport.scissorCount  = 1;
		vk::PipelineRasterizationStateCreateInfo rasterization {};
		rasterization.lineWidth = 1.0f;
		vk::PipelineMultisampleStateCreateInfo multisample {};
		multisample.rasterizationSamples = vk::SampleCountFlagBits::e1;
		vk::PipelineColorBlendAttachmentState attachment {};
		attachment.colorWriteMask = vk::ColorComponentFlagBits::eR | vk::ColorComponentFlagBits::eG |
		                            vk::ColorComponentFlagBits::eB | vk::ColorComponentFlagBits::eA;
		vk::PipelineColorBlendStateCreateInfo blend {};
		blend.attachmentCount = 1;
		blend.pAttachments    = &attachment;
		const std::array dynamic_states {vk::DynamicState::eViewport, vk::DynamicState::eScissor};
		vk::PipelineDynamicStateCreateInfo dynamic {};
		dynamic.dynamicStateCount = static_cast<uint32_t>(dynamic_states.size());
		dynamic.pDynamicStates    = dynamic_states.data();
		vk::PipelineRenderingCreateInfo rendering {};
		rendering.colorAttachmentCount    = 1;
		rendering.pColorAttachmentFormats = &m_format;
		vk::GraphicsPipelineCreateInfo create {};
		create.pNext               = &rendering;
		create.stageCount          = static_cast<uint32_t>(stages.size());
		create.pStages             = stages.data();
		create.pVertexInputState   = &vertex_input;
		create.pInputAssemblyState = &assembly;
		create.pViewportState      = &viewport;
		create.pRasterizationState = &rasterization;
		create.pMultisampleState   = &multisample;
		create.pColorBlendState    = &blend;
		create.pDynamicState       = &dynamic;
		create.layout              = m_filter_layout;
		const auto result = device.createGraphicsPipelines(nullptr, 1, &create, nullptr, &m_filter_pipeline);
		device.destroyShaderModule(fragment, nullptr);
		device.destroyShaderModule(vertex, nullptr);
		if (result != vk::Result::eSuccess) {
			m_filter_pipeline = nullptr;
			return false;
		}
		std::fprintf(stderr, "NOVA_PRESENT_FILTER: %s presentation filter active\n", mode == 2u ? "sharp (ScaleForce-style)" : "bicubic");
	}
	if (source.view == nullptr) {
		vk::ImageViewCreateInfo view {};
		view.image            = source.image.image;
		view.viewType         = vk::ImageViewType::e2D;
		view.format           = source.image.format;
		view.subresourceRange = {vk::ImageAspectFlagBits::eColor, 0, 1, 0, 1};
		if (device.createImageView(&view, nullptr, &source.view) != vk::Result::eSuccess) {
			source.view = nullptr;
			return false;
		}
	}
	source.Transit(command, vk::ImageLayout::eShaderReadOnlyOptimal, vk::AccessFlagBits2::eShaderRead);
	vk::ImageMemoryBarrier to_color {};
	to_color.srcAccessMask       = vk::AccessFlagBits::eTransferWrite;
	to_color.dstAccessMask       = vk::AccessFlagBits::eColorAttachmentWrite;
	to_color.oldLayout           = vk::ImageLayout::eTransferDstOptimal;
	to_color.newLayout           = vk::ImageLayout::eColorAttachmentOptimal;
	to_color.srcQueueFamilyIndex = to_color.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
	to_color.image               = m_images[m_image_index];
	to_color.subresourceRange    = {vk::ImageAspectFlagBits::eColor, 0, 1, 0, 1};
	command.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer, vk::PipelineStageFlagBits::eColorAttachmentOutput, {}, 0,
	                        nullptr, 0, nullptr, 1, &to_color);
	const vk::DescriptorImageInfo image {m_filter_sampler, source.view, vk::ImageLayout::eShaderReadOnlyOptimal};
	vk::WriteDescriptorSet write {};
	write.dstBinding      = 0;
	write.descriptorCount = 1;
	write.descriptorType  = vk::DescriptorType::eCombinedImageSampler;
	write.pImageInfo      = &image;
	command.pushDescriptorSetKHR(vk::PipelineBindPoint::eGraphics, m_filter_layout, 0, 1, &write);
	command.pushConstants(m_filter_layout, vk::ShaderStageFlagBits::eFragment, 0, sizeof(mode), &mode);
	command.bindPipeline(vk::PipelineBindPoint::eGraphics, m_filter_pipeline);
	vk::RenderingAttachmentInfo attachment {};
	attachment.imageView   = m_image_views[m_image_index];
	attachment.imageLayout = vk::ImageLayout::eColorAttachmentOptimal;
	attachment.loadOp      = vk::AttachmentLoadOp::eDontCare;
	attachment.storeOp     = vk::AttachmentStoreOp::eStore;
	vk::RenderingInfo rendering {};
	rendering.renderArea.extent    = m_extent;
	rendering.layerCount           = 1;
	rendering.colorAttachmentCount = 1;
	rendering.pColorAttachments    = &attachment;
	command.beginRendering(&rendering);
	const vk::Viewport viewport {0.0f, 0.0f, static_cast<float>(m_extent.width), static_cast<float>(m_extent.height), 0.0f, 1.0f};
	const vk::Rect2D   scissor {{0, 0}, m_extent};
	command.setViewport(0, 1, &viewport);
	command.setScissor(0, 1, &scissor);
	command.draw(3, 1, 0, 0);
	command.endRendering();
	vk::ImageMemoryBarrier back = to_color;
	back.srcAccessMask = vk::AccessFlagBits::eColorAttachmentWrite;
	back.dstAccessMask = vk::AccessFlagBits::eTransferWrite | vk::AccessFlagBits::eTransferRead;
	back.oldLayout     = vk::ImageLayout::eColorAttachmentOptimal;
	back.newLayout     = vk::ImageLayout::eTransferDstOptimal;
	command.pipelineBarrier(vk::PipelineStageFlagBits::eColorAttachmentOutput, vk::PipelineStageFlagBits::eTransfer, {}, 0,
	                        nullptr, 0, nullptr, 1, &back);
	return true;
}

void Swapchain::RecordPresentCommands('''
s = once(s, '\nvoid Swapchain::RecordPresentCommands(', method, 'RecordPresentCommands definition')
for header in ('#include <string_view>', '#include <cstdio>'):
    if header not in s:
        s = s.replace('#include <algorithm>\n', '#include <algorithm>\n' + header + '\n', 1)
shader_dir = root / 'src/graphics/host_gpu/shaders'
shutil.copyfile(repo / 'native/render/shaders/gpu_present_filter.frag', shader_dir / 'gpu_present_filter.frag')
sc.write_text(s)
cm.write_text(c)
print('0997: presentation filter (NOVA_PRESENT_FILTER=bicubic|sharp)')
