#!/usr/bin/env python3
"""0.9.58: Lossless Scaling frame generation in Nova's presenter.

Uses the user's own Lossless.dll (imported in the launcher; never shipped) through
libnovalsfg.so (lsfg-vk 1.0.0 + lsfg-vk-android AHardwareBuffer patches, MIT).

  * Device: enable VK_ANDROID_external_memory_android_hardware_buffer (and
    VK_EXT_queue_family_foreign when present) only when frame generation is requested.
  * Swapchain: enough images to queue the generated frames (multiplier + 1).
  * Presenter: per real frame, blit the game frame into the shared input image in the
    present command buffer, wait for that submit, generate, present each generated
    frame (own acquire/submit/present, renderer lock only around recording), then
    present the real frame. Any failure turns frame generation off for the session
    and the normal path continues.

The source of the presenter state is native/novalsfg/novaFramegen.h.
"""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]); src = root / 'src'
repo = Path(__file__).resolve().parents[2]
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0958_FRAMEGEN: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


shutil.copyfile(repo / 'native/novalsfg/novaFramegen.h', src / 'graphics/presentation/window/novaFramegen.h')

# ---- device extensions ----
vw = src / 'graphics/presentation/window/vulkanWindow.cpp'
edit(vw, '''		if (HasExtension(available_extensions, VK_EXT_ATTACHMENT_FEEDBACK_LOOP_LAYOUT_EXTENSION_NAME) &&
		    HasExtension(available_extensions, VK_EXT_ATTACHMENT_FEEDBACK_LOOP_DYNAMIC_STATE_EXTENSION_NAME)) {
			device_extensions.push_back(VK_EXT_ATTACHMENT_FEEDBACK_LOOP_LAYOUT_EXTENSION_NAME);
			device_extensions.push_back(VK_EXT_ATTACHMENT_FEEDBACK_LOOP_DYNAMIC_STATE_EXTENSION_NAME);
		}
	}
''', '''		if (HasExtension(available_extensions, VK_EXT_ATTACHMENT_FEEDBACK_LOOP_LAYOUT_EXTENSION_NAME) &&
		    HasExtension(available_extensions, VK_EXT_ATTACHMENT_FEEDBACK_LOOP_DYNAMIC_STATE_EXTENSION_NAME)) {
			device_extensions.push_back(VK_EXT_ATTACHMENT_FEEDBACK_LOOP_LAYOUT_EXTENSION_NAME);
			device_extensions.push_back(VK_EXT_ATTACHMENT_FEEDBACK_LOOP_DYNAMIC_STATE_EXTENSION_NAME);
		}
		// Nova 0.9.58: AHardwareBuffer image sharing for Lossless Scaling frame generation.
		if (NovaFramegen::Requested()) {
			if (HasExtension(available_extensions, "VK_ANDROID_external_memory_android_hardware_buffer")) {
				device_extensions.push_back("VK_ANDROID_external_memory_android_hardware_buffer");
				if (HasExtension(available_extensions, "VK_EXT_queue_family_foreign")) {
					device_extensions.push_back("VK_EXT_queue_family_foreign");
				}
				NovaFramegen::AhbEnabled() = true;
				// 0.9.60: compositor-timed presents pace generated frames without sleeping.
				if (HasExtension(available_extensions, "VK_GOOGLE_display_timing")) {
					device_extensions.push_back("VK_GOOGLE_display_timing");
					NovaFramegen::DisplayTiming() = true;
				} else {
					std::fprintf(stderr, "NOVA_FRAMEGEN: no VK_GOOGLE_display_timing; generated frames are shown unpaced\\n");
				}
			} else {
				std::fprintf(stderr, "NOVA_FRAMEGEN: off (driver lacks VK_ANDROID_external_memory_android_hardware_buffer)\\n");
			}
		}
	}
''')
s = changes[vw]
if 'novaFramegen.h' not in s:
    i = s.index('#include')
    s = s[:i] + '#include "graphics/presentation/window/novaFramegen.h"\n#include <cstdio>\n' + s[i:]
changes[vw] = s

# ---- swapchain ----
sc = src / 'graphics/presentation/window/swapchain.cpp'
edit(sc, '#include "graphics/presentation/window/windowInternal.h"\n',
     '#include "graphics/presentation/window/windowInternal.h"\n#include "graphics/presentation/window/novaFramegen.h"\n')
edit(sc, '''	uint32_t image_count = surface.capabilities.minImageCount + 1;
	if (surface.capabilities.maxImageCount != 0) {''', '''	uint32_t image_count = surface.capabilities.minImageCount + 1;
	if (NovaFramegen::Requested()) {
		// Real frame held while the generated ones are queued.
		image_count = std::max(image_count, static_cast<uint32_t>(NovaFramegen::Multiplier()) + 1u);
	}
	if (surface.capabilities.maxImageCount != 0) {''')
edit(sc, '''	uint64_t Submit(CommandScheduler& scheduler);
	[[nodiscard]] Status Present();
''', '''	uint64_t Submit(CommandScheduler& scheduler);
	[[nodiscard]] Status Present();
	[[nodiscard]] uint32_t ImageIndex() const noexcept { return m_image_index; }
	// Nova 0.9.60: desired display time for the next Present() only (VK_GOOGLE_display_timing).
	void NovaSetPresentTime(uint64_t monotonic_ns) noexcept { m_nova_present_time_ns = monotonic_ns; }
	uint64_t m_nova_present_time_ns = 0;
	uint32_t m_nova_present_id      = 0;
	// Nova 0.9.58: show one generated frame before the real frame `real_index`.
	[[nodiscard]] Status NovaPresentGenerated(CommandScheduler& scheduler, Common::Mutex& render_mutex,
	                                          vk::Image generated, vk::Extent2D extent, uint32_t real_index);
''')
edit(sc, '''	present.pWaitSemaphores    = &ready;
	present.waitSemaphoreCount = 1;
''', '''	present.pWaitSemaphores    = &ready;
	present.waitSemaphoreCount = 1;
	// Nova 0.9.60: compositor-timed frame-generation presents.
	VkPresentTimeGOOGLE     nova_time {};
	VkPresentTimesInfoGOOGLE nova_times {};
	if (m_nova_present_time_ns != 0 && NovaFramegen::DisplayTiming()) {
		nova_time.presentID          = ++m_nova_present_id;
		nova_time.desiredPresentTime = m_nova_present_time_ns;
		nova_times.sType             = VK_STRUCTURE_TYPE_PRESENT_TIMES_INFO_GOOGLE;
		nova_times.swapchainCount    = 1;
		nova_times.pTimes            = &nova_time;
		present.pNext                = &nova_times;
	}
	m_nova_present_time_ns = 0;
''')
edit(sc, '''Presenter::Presenter(WindowContext& window): m_impl(std::make_unique<Impl>(window)) {}''',
     '''Swapchain::Status Swapchain::NovaPresentGenerated(CommandScheduler& scheduler, Common::Mutex& render_mutex,
                                                  vk::Image generated, vk::Extent2D extent,
                                                  uint32_t real_index) {
	auto status = AcquireNextImage(scheduler);
	if (status != Status::Success) {
		m_image_index = real_index;
		return status;
	}
	{
		Common::LockGuard lock(render_mutex);
		auto& command = scheduler.BeginCommand();
		NovaFramegen::State::RecordOutput(command.Handle(), generated, extent, m_images[m_image_index], m_extent);
		(void)Submit(scheduler);
	}
	status        = Present();
	m_image_index = real_index;
	return status;
}

Presenter::Presenter(WindowContext& window): m_impl(std::make_unique<Impl>(window)) {}''')
edit(sc, '''	std::array<Layer, 2>  layers {};
	std::atomic<uint64_t> presented_overlay_revision {0};
};''', '''	std::array<Layer, 2>  layers {};
	std::atomic<uint64_t> presented_overlay_revision {0};
	NovaFramegen::State   framegen;
};''')
edit(sc, '''		{
			Common::LockGuard render_lock(renderer.GetMutex());
			auto&             command = present_scheduler.BeginCommand();
			const bool        draw_system_overlay =
			    overlay_visual.active && swapchain.PrepareSystemOverlay();
			swapchain.RecordPresentCommands(command, layers[0].frame, layers[1],
			                                draw_system_overlay);
			const auto tick = swapchain.Submit(present_scheduler);
			for (const auto& layer: layers) {
				if (layer.frame != nullptr) {
					layer.frame->present_tick = tick;
				}
			}
		}
		status = swapchain.Present();''', '''		bool     nova_fg_input = false;
		uint64_t nova_fg_tick  = 0;
		{
			Common::LockGuard render_lock(renderer.GetMutex());
			auto&             command = present_scheduler.BeginCommand();
			const bool        draw_system_overlay =
			    overlay_visual.active && swapchain.PrepareSystemOverlay();
			// Nova 0.9.58: copy the finished game frame into the frame-generation input.
			if (auto* source = layers[0].frame; source != nullptr && !source->blank && framegen.Active()) {
				source->Transit(command.Handle(), vk::ImageLayout::eTransferSrcOptimal,
				                vk::AccessFlagBits2::eTransferRead);
				nova_fg_input = framegen.RecordInput(window.graphic_ctx, command.Handle(), source->image.image,
				                                     vk::Extent2D {source->image.extent.width, source->image.extent.height});
			}
			swapchain.RecordPresentCommands(command, layers[0].frame, layers[1],
			                                draw_system_overlay);
			const auto tick = swapchain.Submit(present_scheduler);
			nova_fg_tick    = tick;
			for (const auto& layer: layers) {
				if (layer.frame != nullptr) {
					layer.frame->present_tick = tick;
				}
			}
		}
		if (nova_fg_input) {
			// The other Vulkan device reads the input: wait for the copy, then generate and
			// show the in-between frames before this real frame.
			present_scheduler.Wait(nova_fg_tick);
			framegen.CountReal();
			const uint32_t real_index = swapchain.ImageIndex();
			const auto     generated  = framegen.Generate();
			for (size_t i = 0; i < generated.size(); i++) {
				if (i != 0) swapchain.NovaSetPresentTime(framegen.NextSlotNs());
				if (swapchain.NovaPresentGenerated(present_scheduler, renderer.GetMutex(), generated[i],
				                                   framegen.Extent(), real_index) != Swapchain::Status::Success) {
					break;
				}
			}
			if (!generated.empty()) swapchain.NovaSetPresentTime(framegen.NextSlotNs());
		}
		status = swapchain.Present();''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0958_FRAMEGEN: Lossless Scaling frame generation in the presenter (NOVA_FRAMEGEN / NOVA_LSFG_DLL)')
