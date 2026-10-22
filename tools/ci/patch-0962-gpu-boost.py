#!/usr/bin/env python3
"""0.9.62: GPU-bound speedups for Ever Forward / Wonder Boy (both ~86-92 % GPU busy on 0.9.61).

  1. GPU turbo (NOVA_GPU_TURBO=1): disable KGSL power control so the Adreno runs at its
     maximum clock (IOCTL_KGSL_SETPROPERTY / KGSL_PROP_PWRCTRL = 0, the call libadrenotools'
     adrenotools_set_turbo makes). Re-asserted every second, as Eden's turbo mode does; the
     setting is device-global and outlives the process, so a launch without turbo clears it.
     A kernel call: works with Turnip and with the system driver.
  2. Variable-rate shading (NOVA_VRS=2): VK_KHR_fragment_shading_rate pipeline rate as dynamic
     state. Draws into 1-sample colour passes of at least 1280x720 that are not video-out
     (display) images are shaded per 2x2 pixel block; depth, coverage and edges stay full
     resolution. Final/display passes (HUD, text), depth-only passes, MSAA and small passes stay
     1x1. Used only when the driver reports pipelineFragmentShadingRate and a 2x2 rate for one
     sample; otherwise off with a log line. Shaders writing depth/stencil are clamped to 1x1 by
     the driver when fragmentShadingRateWithShaderDepthStencilWrites is false (Vulkan spec).

NOVA_VRS_REPORT: draws shaded 2x2 / 1x1 every 5 s.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]); src = root / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0962_GPU_BOOST: anchor changed {path.name}: {old[:80]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


# ---- 1. GPU turbo ----
na = src / 'novaAndroid.cpp'
edit(na, '''PFN_vkGetInstanceProcAddr NovaAndroidVulkanLoader(PFN_vkGetInstanceProcAddr fallback) {
	if (g_gipa != nullptr) {
		return g_gipa;
	}''', '''// Nova 0.9.62: GPU turbo. KGSL power control off = maximum Adreno clocks (what
// adrenotools_set_turbo does). Device-global: re-assert while running, clear when not wanted.
namespace {
struct NovaKgslProperty {
	unsigned int type;
	void*        value;
	size_t       sizebytes;
};
constexpr unsigned int kNovaKgslPropPwrctrl = 0xE;
#define NOVA_IOCTL_KGSL_SETPROPERTY _IOW(0x09, 0x32, NovaKgslProperty)
int NovaSetGpuTurbo(bool turbo) {
	uint32_t         enable = turbo ? 0u : 1u;
	NovaKgslProperty prop {kNovaKgslPropPwrctrl, &enable, sizeof(enable)};
	const int        fd = open("/dev/kgsl-3d0", O_RDWR | O_CLOEXEC);
	if (fd < 0) return -errno;
	const int result = ioctl(fd, NOVA_IOCTL_KGSL_SETPROPERTY, &prop) == 0 ? 0 : -errno;
	close(fd);
	return result;
}
void NovaStartGpuTurbo() {
	static bool started = false;
	if (started) return;
	started              = true;
	const char* value    = getenv("NOVA_GPU_TURBO");
	const bool  wanted   = value != nullptr && value[0] == '1';
	const int   result   = NovaSetGpuTurbo(wanted);
	std::fprintf(stderr, "NOVA_GPU_TURBO: %s (KGSL power control %s, result=%d)\\n", wanted ? "on" : "off",
	             wanted ? "disabled, maximum GPU clock" : "restored", result);
	if (!wanted || result != 0) return;
	std::thread([] {
		for (;;) {
			std::this_thread::sleep_for(std::chrono::seconds(1));
			(void)NovaSetGpuTurbo(true);
		}
	}).detach();
}
} // namespace

PFN_vkGetInstanceProcAddr NovaAndroidVulkanLoader(PFN_vkGetInstanceProcAddr fallback) {
	NovaStartGpuTurbo();
	if (g_gipa != nullptr) {
		return g_gipa;
	}''')
s = changes[na]
for inc in ['#include <sys/ioctl.h>', '#include <fcntl.h>', '#include <unistd.h>', '#include <cerrno>', '#include <thread>',
            '#include <chrono>', '#include <cstdio>', '#include <cstdlib>']:
    if inc not in s:
        s = s.replace('#include', inc + '\n#include', 1)
changes[na] = s

# ---- 2. variable-rate shading ----
gc = src / 'graphics/host_gpu/graphicContext.h'
edit(gc, '	bool graphics_pipeline_library_enabled = false;\n',
     '	bool graphics_pipeline_library_enabled = false;\n	bool nova_vrs_enabled = false; // 0.9.62: VK_KHR_fragment_shading_rate pipeline rate (dynamic)\n')

vw = src / 'graphics/presentation/window/vulkanWindow.cpp'
edit(vw, '''		if (HasExtension(available_extensions,VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME) &&
		    HasExtension(available_extensions,VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME)) {''', '''		// Nova 0.9.62: variable-rate shading for GPU-bound titles (NOVA_VRS=2).
		if (const char* vrs = std::getenv("NOVA_VRS"); vrs != nullptr && vrs[0] == '2' &&
		    HasExtension(available_extensions, VK_KHR_FRAGMENT_SHADING_RATE_EXTENSION_NAME)) {
			device_extensions.push_back(VK_KHR_FRAGMENT_SHADING_RATE_EXTENSION_NAME);
		}
		if (HasExtension(available_extensions,VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME) &&
		    HasExtension(available_extensions,VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME)) {''')
edit(vw, '''	vk::PhysicalDeviceGraphicsPipelineLibraryFeaturesEXT nova_gpl {};
	if (nova_gpl_extensions) { nova_gpl.pNext=supported_features2.pNext; supported_features2.pNext=&nova_gpl; }
	physical_device.getFeatures2(&supported_features2);''', '''	vk::PhysicalDeviceGraphicsPipelineLibraryFeaturesEXT nova_gpl {};
	if (nova_gpl_extensions) { nova_gpl.pNext=supported_features2.pNext; supported_features2.pNext=&nova_gpl; }
	const bool nova_vrs_extension = HasExtension(device_extensions, VK_KHR_FRAGMENT_SHADING_RATE_EXTENSION_NAME);
	vk::PhysicalDeviceFragmentShadingRateFeaturesKHR nova_vrs {};
	if (nova_vrs_extension) { nova_vrs.pNext=supported_features2.pNext; supported_features2.pNext=&nova_vrs; }
	physical_device.getFeatures2(&supported_features2);
	if (nova_vrs_extension) {
		// The 2x2 rate must be available for one sample.
		bool two_by_two = false;
		const auto& d   = VULKAN_HPP_DEFAULT_DISPATCHER;
		if (nova_vrs.pipelineFragmentShadingRate && d.vkGetPhysicalDeviceFragmentShadingRatesKHR != nullptr) {
			uint32_t count = 0;
			const auto pd  = static_cast<VkPhysicalDevice>(physical_device);
			d.vkGetPhysicalDeviceFragmentShadingRatesKHR(pd, &count, nullptr);
			std::vector<VkPhysicalDeviceFragmentShadingRateKHR> rates(count);
			for (auto& r: rates) r.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FRAGMENT_SHADING_RATE_KHR;
			d.vkGetPhysicalDeviceFragmentShadingRatesKHR(pd, &count, rates.data());
			for (const auto& r: rates)
				if (r.fragmentSize.width == 2 && r.fragmentSize.height == 2 && (r.sampleCounts & VK_SAMPLE_COUNT_1_BIT)) two_by_two = true;
		}
		graphics.nova_vrs_enabled = nova_vrs.pipelineFragmentShadingRate && two_by_two;
		std::fprintf(stderr, "NOVA_VRS: %s (pipelineFragmentShadingRate=%d 2x2=%d)\\n",
		             graphics.nova_vrs_enabled ? "2x2 shading for large scene passes" : "unavailable on this driver",
		             int(nova_vrs.pipelineFragmentShadingRate), int(two_by_two));
	} else if (const char* vrs = std::getenv("NOVA_VRS"); vrs != nullptr && vrs[0] == '2') {
		std::fprintf(stderr, "NOVA_VRS: unavailable (driver lacks VK_KHR_fragment_shading_rate)\\n");
	}''')
edit(vw, '''	if (graphics.graphics_pipeline_library_enabled) {
	    nova_gpl.graphicsPipelineLibrary=VK_TRUE; nova_gpl.pNext=const_cast<void*>(create_info.pNext); create_info.pNext=&nova_gpl;
	}''', '''	if (graphics.graphics_pipeline_library_enabled) {
	    nova_gpl.graphicsPipelineLibrary=VK_TRUE; nova_gpl.pNext=const_cast<void*>(create_info.pNext); create_info.pNext=&nova_gpl;
	}
	vk::PhysicalDeviceFragmentShadingRateFeaturesKHR nova_vrs_enable {};
	if (graphics.nova_vrs_enabled) {
		nova_vrs_enable.pipelineFragmentShadingRate = VK_TRUE;
		nova_vrs_enable.pNext = const_cast<void*>(create_info.pNext);
		create_info.pNext     = &nova_vrs_enable;
	}''')

sh = src / 'graphics/host_gpu/renderer/pipeline/shaders.cpp'
edit(sh, '''	if (graphics.attachment_feedback_loop_enabled) {
		dynamic_states.push_back(vk::DynamicState::eAttachmentFeedbackLoopEnableEXT);
	}
''', '''	if (graphics.attachment_feedback_loop_enabled) {
		dynamic_states.push_back(vk::DynamicState::eAttachmentFeedbackLoopEnableEXT);
	}
	if (graphics.nova_vrs_enabled) {
		dynamic_states.push_back(vk::DynamicState::eFragmentShadingRateKHR);
	}
''')

rd = src / 'graphics/host_gpu/renderer/renderDraw.cpp'
edit(rd, '''	dynamic_state.SetAttachmentFeedbackLoopAspects(feedback_aspects);
	dynamic_state.Commit(m_context.GetGraphics(), vk_buffer);''', '''	dynamic_state.SetAttachmentFeedbackLoopAspects(feedback_aspects);
	dynamic_state.Commit(m_context.GetGraphics(), vk_buffer);
	// Nova 0.9.62: per-draw shading rate (dynamic state, set on every draw because other
	// pipelines bound in between leave it undefined).
	if (m_context.GetGraphics().nova_vrs_enabled) {
		bool coarse = rendering.num_color_attachments != 0 && rendering.width * rendering.height >= 1280u * 720u &&
		              rendering.num_layers == 1;
		for (uint32_t i = 0; coarse && i < rendering.num_color_attachments; i++) {
			const auto* image = rendering.color_attachments[i].raster_owner;
			if (image == nullptr || image->usage.video_out || image->backing.samples != 1) coarse = false;
		}
		if (const auto* depth = rendering.depth_stencil_attachment.raster_owner;
		    coarse && depth != nullptr && depth->backing.samples != 1) {
			coarse = false;
		}
		const VkExtent2D size {coarse ? 2u : 1u, coarse ? 2u : 1u};
		const VkFragmentShadingRateCombinerOpKHR ops[2] {VK_FRAGMENT_SHADING_RATE_COMBINER_OP_KEEP_KHR,
		                                                 VK_FRAGMENT_SHADING_RATE_COMBINER_OP_KEEP_KHR};
		VULKAN_HPP_DEFAULT_DISPATCHER.vkCmdSetFragmentShadingRateKHR(static_cast<VkCommandBuffer>(vk_buffer), &size, ops);
		static thread_local uint64_t nova_vrs_coarse = 0, nova_vrs_full = 0;
		static thread_local auto     nova_vrs_start  = std::chrono::steady_clock::now();
		(coarse ? nova_vrs_coarse : nova_vrs_full)++;
		if (const auto now = std::chrono::steady_clock::now(); now - nova_vrs_start >= std::chrono::seconds(5)) {
			std::fprintf(stderr, "NOVA_VRS_REPORT: draws_2x2=%llu draws_1x1=%llu\\n", (unsigned long long)nova_vrs_coarse,
			             (unsigned long long)nova_vrs_full);
			nova_vrs_coarse = nova_vrs_full = 0;
			nova_vrs_start  = now;
		}
	}''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0962_GPU_BOOST: GPU turbo (NOVA_GPU_TURBO) and 2x2 variable-rate shading (NOVA_VRS=2)')

# ---- 3. real GPU time for timestamp writes (NOVA_REAL_GPU_TIME=1) ----
# yuzu's "Use Fast GPU Time" shows that games with dynamic resolution choose their render size
# from reported GPU time (it reports a fast GPU so they stay at full resolution). Nova's fast
# labels stamp GPU timestamps when the packet is read, i.e. a GPU that takes no time. With this
# option each timestamp is written again when the GPU has really finished that command buffer,
# so a game with dynamic resolution sees the real cost and can lower its own resolution.
gr = src / 'graphics/guest_gpu/graphicsRun.cpp'
s = gr.read_text()
old = '''			if (timestamp) data = static_cast<decltype(data)>(Sync::ReadReferenceClock());
			GuestMemory::Copy(dst_gpu_addr, &data, sizeof(data));
#if defined(KYTY_NOVA_FEX)
			NovaNoteGpuWrite(dst_gpu_addr, static_cast<uint64_t>(data),
			                 static_cast<uint32_t>(m_interrupt_event_id), 'E');
#endif'''
if s.count(old) != 1:
    raise SystemExit('NOVA_0962_GPU_BOOST: fast-label anchor changed')
s = s.replace(old, '''			if (timestamp) data = static_cast<decltype(data)>(Sync::ReadReferenceClock());
			GuestMemory::Copy(dst_gpu_addr, &data, sizeof(data));
			if (timestamp && NovaRealGpuTime()) NovaRestampAtCompletion(GetScheduler(), dst_gpu_addr, sizeof(data));
#if defined(KYTY_NOVA_FEX)
			NovaNoteGpuWrite(dst_gpu_addr, static_cast<uint64_t>(data),
			                 static_cast<uint32_t>(m_interrupt_event_id), 'E');
#endif''')
old = '''	const auto value = Sync::ReadReferenceClock();
	GuestMemory::Write(dst_address, &value, num_bytes);'''
if s.count(old) != 1:
    raise SystemExit('NOVA_0962_GPU_BOOST: reference-clock anchor changed')
s = s.replace(old, '''	const auto value = Sync::ReadReferenceClock();
	GuestMemory::Write(dst_address, &value, num_bytes);
	if (NovaRealGpuTime()) NovaRestampAtCompletion(GetScheduler(), reinterpret_cast<void*>(dst_address), num_bytes);''')
helper = '''// Nova 0.9.62: NOVA_REAL_GPU_TIME=1 - rewrite a GPU timestamp with the time the GPU finished it.
static bool NovaRealGpuTime() {
	static const bool enabled = [] {
		const char* v = std::getenv("NOVA_REAL_GPU_TIME");
		const bool  on = v != nullptr && v[0] == '1';
		std::fprintf(stderr, "NOVA_GPU_TIMESTAMPS: %s\\n",
		             on ? "real (written when the GPU finishes; games with dynamic resolution can react)"
		                : "at packet time (fast)");
		return on;
	}();
	return enabled;
}
static void NovaRestampAtCompletion(CommandScheduler& scheduler, void* dst, uint32_t size) {
	static std::atomic<uint64_t> restamped {0};
	if (restamped.fetch_add(1, std::memory_order_relaxed) == 0) std::fprintf(stderr, "NOVA_GPU_TIMESTAMPS: first real timestamp queued\\n");
	scheduler.DeferPriorityOperation([dst, size] {
		const uint64_t now = Sync::ReadReferenceClock();
		if (size == sizeof(uint32_t)) {
			const auto v32 = static_cast<uint32_t>(now);
			GuestMemory::Copy(dst, &v32, sizeof(v32));
		} else {
			GuestMemory::Copy(dst, &now, sizeof(now));
		}
	});
}

void CommandProcessor::WriteReferenceClock('''
if s.count('void CommandProcessor::WriteReferenceClock(') != 1:
    raise SystemExit('NOVA_0962_GPU_BOOST: WriteReferenceClock anchor changed')
s = s.replace('void CommandProcessor::WriteReferenceClock(', helper, 1)
for inc in ['#include <atomic>', '#include <cstdlib>', '#include <cstdio>']:
    if inc not in s:
        s = s.replace('#include', inc + '\n#include', 1)
gr.write_text(s)
print('NOVA_0962_GPU_BOOST: real GPU timestamps (NOVA_REAL_GPU_TIME=1)')
