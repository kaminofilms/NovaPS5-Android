// Nova PS5: Lossless Scaling frame generation in the presenter (copied into Kyty as
// src/graphics/presentation/window/novaFramegen.h by tools/ci/patch-0958-framegen.py).
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Per real frame: the finished game frame is blitted into one of two shared images
// (AHardwareBuffer-backed, alternating), the present submit is waited for, libnovalsfg
// generates (multiplier - 1) frames between the previous and the current input on its
// own Vulkan device, and the presenter shows them before the real frame.
#pragma once

#include "graphics/host_gpu/graphicContext.h"
#include "graphics/host_gpu/vulkanCommon.h"
#include "novaFrameExtent.h"

#include <thread>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>
#include <vector>

#if defined(__ANDROID__)
#include <android/hardware_buffer.h>
#include <dlfcn.h>
#include <vulkan/vulkan_android.h>
#endif

namespace Libs::Graphics::NovaFramegen {

// NOVA_FRAMEGEN = output multiplier 2..4 (anything else: off).
inline int Multiplier() {
	static const int value = [] {
		const char* text = std::getenv("NOVA_FRAMEGEN");
		const int   n    = text != nullptr ? std::atoi(text) : 1;
		return n >= 2 && n <= 4 ? n : 1;
	}();
	return value;
}
inline bool Requested() {
	return Multiplier() > 1 && std::getenv("NOVA_LSFG_DLL") != nullptr;
}
// Set during device creation when VK_ANDROID_external_memory_android_hardware_buffer is enabled.
inline bool& AhbEnabled() {
	static bool enabled = false;
	return enabled;
}
// Set during device creation when VK_GOOGLE_display_timing is enabled (0.9.60 pacing).
inline bool& DisplayTiming() {
	static bool enabled = false;
	return enabled;
}
inline float FlowScale() {
	static const float value = [] {
		const char* text = std::getenv("NOVA_FRAMEGEN_FLOW");
		const float f    = text != nullptr ? static_cast<float>(std::atof(text)) : 0.5f;
		return f >= 0.25f && f <= 1.0f ? f : 0.5f;
	}();
	return value;
}
inline bool Performance() {
	const char* text = std::getenv("NOVA_FRAMEGEN_PERF");
	return text != nullptr && text[0] == '1';
}

#if defined(__ANDROID__)
class State {
public:
	[[nodiscard]] bool Active() const { return !m_failed && Requested() && AhbEnabled() && DisplayTiming(); }
	[[nodiscard]] vk::Extent2D Extent() const { return m_extent; }

	// Records the copy of the finished game frame (already in TRANSFER_SRC_OPTIMAL).
	bool RecordInput(GraphicContext& g, vk::CommandBuffer command, vk::Image source, vk::Extent2D extent) {
		if (!Active() || !Ensure(g, extent)) return false;
		auto& target = m_inputs[m_frame % 2];
		Barrier(command, target.image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0,
		        VK_ACCESS_TRANSFER_WRITE_BIT);
		Blit(command, source, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, extent, target.image,
		     VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, m_extent);
		Barrier(command, target.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL,
		        VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_MEMORY_READ_BIT);
		return true;
	}

	// After the input copy has completed on the GPU: returns the generated images to show
	// before the real frame (empty for the very first input or on failure).
	std::vector<vk::Image> Generate() {
		std::vector<vk::Image> images;
		if (!Active() || m_context < 0) return images;
		const auto start = std::chrono::steady_clock::now();
		char       error[256] {};
		if (m_present(m_context, error, sizeof(error)) != 0) {
			Disable(error);
			return images;
		}
		const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count();
		m_generate_ns += static_cast<uint64_t>(ns);
		if (m_frame++ != 0) {
			for (const auto& out: m_outputs) images.push_back(out.image);
			m_generated += images.size();
		}
		Report();
		return images;
	}

	// Presenter blit of a generated image into the acquired swapchain image.
	static void RecordOutput(vk::CommandBuffer command, vk::Image generated, vk::Extent2D extent,
	                         vk::Image swapchain_image, vk::Extent2D swapchain_extent) {
		Barrier(command, generated, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, 0,
		        VK_ACCESS_TRANSFER_READ_BIT);
		Barrier(command, swapchain_image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0,
		        VK_ACCESS_TRANSFER_WRITE_BIT);
		Blit(command, generated, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, extent, swapchain_image,
		     VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, swapchain_extent);
		Barrier(command, swapchain_image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
		        VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_MEMORY_READ_BIT);
		Barrier(command, generated, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL,
		        VK_ACCESS_TRANSFER_READ_BIT, 0);
	}

private:
	struct Shared {
		AHardwareBuffer* ahb    = nullptr;
		VkImage          image  = VK_NULL_HANDLE;
		VkDeviceMemory   memory = VK_NULL_HANDLE;
	};
	static constexpr VkFormat kFormat = VK_FORMAT_R16G16B16A16_SFLOAT; // lsfg-vk non-HDR format

	static void Barrier(vk::CommandBuffer command, VkImage image, VkImageLayout from, VkImageLayout to,
	                    VkAccessFlags src_access, VkAccessFlags dst_access) {
		VkImageMemoryBarrier barrier {};
		barrier.sType               = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
		barrier.srcAccessMask       = src_access;
		barrier.dstAccessMask       = dst_access;
		barrier.oldLayout           = from;
		barrier.newLayout           = to;
		barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
		barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
		barrier.image               = image;
		barrier.subresourceRange    = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
		command.pipelineBarrier(vk::PipelineStageFlagBits::eAllCommands, vk::PipelineStageFlagBits::eAllCommands, {}, 0,
		                        nullptr, 0, nullptr, 1, reinterpret_cast<const vk::ImageMemoryBarrier*>(&barrier));
	}
	static void Blit(vk::CommandBuffer command, VkImage src, VkImageLayout src_layout, vk::Extent2D src_extent,
	                 VkImage dst, VkImageLayout dst_layout, vk::Extent2D dst_extent) {
		VkImageBlit blit {};
		blit.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
		blit.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
		blit.srcOffsets[1]  = {static_cast<int32_t>(src_extent.width), static_cast<int32_t>(src_extent.height), 1};
		blit.dstOffsets[1]  = {static_cast<int32_t>(dst_extent.width), static_cast<int32_t>(dst_extent.height), 1};
		command.blitImage(src, static_cast<vk::ImageLayout>(src_layout), dst, static_cast<vk::ImageLayout>(dst_layout), 1,
		                  reinterpret_cast<const vk::ImageBlit*>(&blit), vk::Filter::eLinear);
	}

	void Disable(const char* why) {
		if (!m_failed) std::fprintf(stderr, "NOVA_FRAMEGEN: off (%s)\n", why);
		m_failed = true;
	}

	bool Load() {
		if (m_init != nullptr) return true;
		void* lib = dlopen("libnovalsfg.so", RTLD_NOW | RTLD_LOCAL);
		if (lib == nullptr) {
			Disable(dlerror());
			return false;
		}
		m_init    = reinterpret_cast<decltype(m_init)>(dlsym(lib, "nova_lsfg_init"));
		m_create  = reinterpret_cast<decltype(m_create)>(dlsym(lib, "nova_lsfg_create"));
		m_present = reinterpret_cast<decltype(m_present)>(dlsym(lib, "nova_lsfg_present"));
		m_destroy = reinterpret_cast<decltype(m_destroy)>(dlsym(lib, "nova_lsfg_destroy"));
		if (m_init == nullptr || m_create == nullptr || m_present == nullptr || m_destroy == nullptr) {
			m_init = nullptr;
			Disable("libnovalsfg.so is incomplete");
			return false;
		}
		return true;
	}

	bool CreateShared(GraphicContext& g, Shared& out) {
		AHardwareBuffer_Desc desc {};
		desc.width  = m_extent.width;
		desc.height = m_extent.height;
		desc.layers = 1;
		desc.format = AHARDWAREBUFFER_FORMAT_R16G16B16A16_FLOAT;
		desc.usage  = AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE | AHARDWAREBUFFER_USAGE_GPU_COLOR_OUTPUT |
		             AHARDWAREBUFFER_USAGE_CPU_READ_OFTEN;
		if (AHardwareBuffer_allocate(&desc, &out.ahb) != 0 || out.ahb == nullptr) return false;
		VkExternalMemoryImageCreateInfo external {};
		external.sType       = VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO;
		external.handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_ANDROID_HARDWARE_BUFFER_BIT_ANDROID;
		VkImageCreateInfo image {};
		image.sType         = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
		image.pNext         = &external;
		image.imageType     = VK_IMAGE_TYPE_2D;
		image.format        = kFormat;
		image.extent        = {m_extent.width, m_extent.height, 1};
		image.mipLevels     = 1;
		image.arrayLayers   = 1;
		image.samples       = VK_SAMPLE_COUNT_1_BIT;
		image.tiling        = VK_IMAGE_TILING_OPTIMAL;
		// Nova only copies in and out; the frame-generation device imports the buffer with its own usage.
		image.usage         = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
		              VK_IMAGE_USAGE_TRANSFER_DST_BIT;
		image.sharingMode   = VK_SHARING_MODE_EXCLUSIVE;
		image.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
		const auto device   = static_cast<VkDevice>(g.device);
		const auto& d       = VULKAN_HPP_DEFAULT_DISPATCHER;
		if (d.vkCreateImage(device, &image, nullptr, &out.image) != VK_SUCCESS) return false;
		VkMemoryRequirements requirements {};
		d.vkGetImageMemoryRequirements(device, out.image, &requirements);
		const auto& props = g.physical_device_memory_properties;
		uint32_t    type  = UINT32_MAX;
		for (uint32_t i = 0; i < props.memoryTypeCount && type == UINT32_MAX; i++) {
			if ((requirements.memoryTypeBits & (1u << i)) &&
			    static_cast<bool>(props.memoryTypes[i].propertyFlags & vk::MemoryPropertyFlagBits::eDeviceLocal))
				type = i;
		}
		for (uint32_t i = 0; i < props.memoryTypeCount && type == UINT32_MAX; i++) {
			if (requirements.memoryTypeBits & (1u << i)) type = i;
		}
		if (type == UINT32_MAX) return false;
		VkMemoryDedicatedAllocateInfo dedicated {};
		dedicated.sType = VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO;
		dedicated.image = out.image;
		VkImportAndroidHardwareBufferInfoANDROID import_info {};
		import_info.sType  = VK_STRUCTURE_TYPE_IMPORT_ANDROID_HARDWARE_BUFFER_INFO_ANDROID;
		import_info.pNext  = &dedicated;
		import_info.buffer = out.ahb;
		VkMemoryAllocateInfo allocate {};
		allocate.sType           = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
		allocate.pNext           = &import_info;
		allocate.allocationSize  = requirements.size;
		allocate.memoryTypeIndex = type;
		if (d.vkAllocateMemory(device, &allocate, nullptr, &out.memory) != VK_SUCCESS) return false;
		return d.vkBindImageMemory(device, out.image, out.memory, 0) == VK_SUCCESS;
	}

	bool Ensure(GraphicContext& g, vk::Extent2D extent) {
		const auto work = WorkingSize(extent.width, extent.height);
		extent = vk::Extent2D {work.width, work.height};
		if (m_context >= 0 && extent.width == m_extent.width && extent.height == m_extent.height) return true;
		if (m_context >= 0) {
			// The game changed its output size: start over (rare; title start or mode change).
			m_destroy(m_context);
			m_context = -1;
			Release(g);
		}
		if (!Load()) return false;
		if (!m_initialized) {
			char        error[256] {};
			const auto& p      = g.GetPhysicalDeviceProperties();
			const auto  device = (static_cast<uint64_t>(p.vendorID) << 32u) | p.deviceID;
			auto*       gipa   = reinterpret_cast<void*>(VULKAN_HPP_DEFAULT_DISPATCHER.vkGetInstanceProcAddr);
			if (m_init(std::getenv("NOVA_LSFG_DLL"), gipa, device, Multiplier() - 1, FlowScale(), Performance() ? 1 : 0, 0,
			           error, sizeof(error)) != 0) {
				Disable(error);
				return false;
			}
			m_initialized = true;
		}
		m_extent = extent;
		m_frame  = 0;
		m_outputs.resize(static_cast<size_t>(Multiplier() - 1));
		for (auto* shared: {&m_inputs[0], &m_inputs[1]}) {
			if (!CreateShared(g, *shared)) {
				Disable("could not create a shared input image");
				return false;
			}
		}
		std::vector<AHardwareBuffer*> outputs;
		for (auto& out: m_outputs) {
			if (!CreateShared(g, out)) {
				Disable("could not create a shared output image");
				return false;
			}
			outputs.push_back(out.ahb);
		}
		char error[256] {};
		m_context = m_create(m_inputs[0].ahb, m_inputs[1].ahb, outputs.data(), static_cast<int>(outputs.size()),
		                     m_extent.width, m_extent.height, kFormat, error, sizeof(error));
		if (m_context < 0) {
			Disable(error);
			return false;
		}
		std::fprintf(stderr, "NOVA_FRAMEGEN: on %dx at %ux%u flow_scale=%.2f mode=%s\n", Multiplier(), m_extent.width,
		             m_extent.height, static_cast<double>(FlowScale()), Performance() ? "performance" : "quality");
		return true;
	}

	void Release(GraphicContext& g) {
		{
			Common::LockGuard lock(g.queue_mutex);
			(void)g.queue.waitIdle();
		}
		const auto  device = static_cast<VkDevice>(g.device);
		const auto& d      = VULKAN_HPP_DEFAULT_DISPATCHER;
		auto free_one = [&](Shared& s) {
			if (s.image != VK_NULL_HANDLE) d.vkDestroyImage(device, s.image, nullptr);
			if (s.memory != VK_NULL_HANDLE) d.vkFreeMemory(device, s.memory, nullptr);
			if (s.ahb != nullptr) AHardwareBuffer_release(s.ahb);
			s = {};
		};
		free_one(m_inputs[0]);
		free_one(m_inputs[1]);
		for (auto& out: m_outputs) free_one(out);
	}

	void Report() {
		const auto now = std::chrono::steady_clock::now();
		if (m_report_start == std::chrono::steady_clock::time_point {}) m_report_start = now;
		if (now - m_report_start < std::chrono::seconds(5)) return;
		const auto calls = m_report_calls == 0 ? 1 : m_report_calls;
		std::fprintf(stderr, "NOVA_FRAMEGEN: generated=%llu real=%llu generate_ms_avg=%.2f\n",
		             static_cast<unsigned long long>(m_generated), static_cast<unsigned long long>(m_report_calls),
		             static_cast<double>(m_generate_ns) / 1e6 / static_cast<double>(calls));
		m_generated = m_generate_ns = m_report_calls = 0;
		m_report_start = now;
	}

	int (*m_init)(const char*, void*, uint64_t, int, float, int, int, char*, size_t) = nullptr;
	int (*m_create)(AHardwareBuffer*, AHardwareBuffer*, AHardwareBuffer* const*, int, uint32_t, uint32_t, int, char*,
	                size_t) = nullptr;
	int (*m_present)(int, char*, size_t) = nullptr;
	void (*m_destroy)(int)               = nullptr;

	bool                                  m_failed      = false;
	bool                                  m_initialized = false;
	int                                   m_context     = -1;
	vk::Extent2D                          m_extent {};
	Shared                                m_inputs[2] {};
	std::vector<Shared>                   m_outputs;
	uint64_t                              m_frame        = 0;
	uint64_t                              m_generated    = 0;
	uint64_t                              m_generate_ns  = 0;
	uint64_t                              m_report_calls = 0;
	std::chrono::steady_clock::time_point m_report_start {};

	int64_t                               m_interval_ns = 0;
	std::chrono::steady_clock::time_point m_last_real {};
	std::chrono::steady_clock::time_point m_slot {};

public:
	// A real frame is ready: update the real-frame interval used to spread the generated frames.
	void CountReal() {
		++m_report_calls;
		const auto now = std::chrono::steady_clock::now();
		if (m_last_real != std::chrono::steady_clock::time_point {}) {
			auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(now - m_last_real).count();
			ns      = std::clamp<int64_t>(ns, 4'000'000, 100'000'000);
			m_interval_ns = m_interval_ns == 0 ? ns : (m_interval_ns * 7 + ns) / 8;
		}
		m_last_real = now;
		m_slot      = now;
	}
	// 0.9.60: desired display time (CLOCK_MONOTONIC ns) of the next present of this real frame,
	// 1/multiplier of the real-frame interval after the previous one. The compositor holds the
	// image until then (VK_GOOGLE_display_timing), so the flip thread - and the game waiting on
	// its flips - never sleeps; 0.9.58/59 slept here, which slowed the game itself (~12 -> ~8 FPS).
	// Returns 0 (show as soon as possible) without display timing or before the interval is known.
	[[nodiscard]] uint64_t NextSlotNs() {
		if (m_interval_ns == 0 || !DisplayTiming()) return 0;
		m_slot += std::chrono::nanoseconds(m_interval_ns / Multiplier());
		const auto now = std::chrono::steady_clock::now();
		if (m_slot <= now) {
			m_slot = now;
			return 0;
		}
		// Never ask for more than one capped real-frame interval ahead.
		if (m_slot > now + std::chrono::milliseconds(100)) m_slot = now + std::chrono::milliseconds(100);
		return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(m_slot.time_since_epoch()).count());
	}
};
#else
class State {
public:
	[[nodiscard]] bool Active() const { return false; }
	[[nodiscard]] vk::Extent2D Extent() const { return {}; }
	bool RecordInput(GraphicContext&, vk::CommandBuffer, vk::Image, vk::Extent2D) { return false; }
	std::vector<vk::Image> Generate() { return {}; }
	static void RecordOutput(vk::CommandBuffer, vk::Image, vk::Extent2D, vk::Image, vk::Extent2D) {}
	void CountReal() {}
	[[nodiscard]] uint64_t NextSlotNs() { return 0; }
};
#endif

} // namespace Libs::Graphics::NovaFramegen

