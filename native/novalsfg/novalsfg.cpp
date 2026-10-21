// Nova PS5: libnovalsfg.so, see novalsfg.h.
// SPDX-License-Identifier: MIT
// Shader table and extraction follow lsfg-vk 1.0.0 src/extract/extract.cpp (MIT).
#include "novalsfg.h"

#include <volk.h>
#include <vulkan/vulkan_core.h>

#include <lsfg_3_1.hpp>
#include <lsfg_3_1p.hpp>
#include <pe-parse/parse.h>

#include "extract/trans.hpp"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <exception>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#if defined(__ANDROID__)
#include <android/hardware_buffer.h>
#include <android/log.h>
#endif

namespace {

PFN_vkGetInstanceProcAddr g_gipa        = nullptr;
bool                      g_performance = false;
bool                      g_initialized = false;
std::mutex                g_mutex;

const std::unordered_map<std::string, uint32_t> kShaderResource = {{
    {"mipmaps", 255},    {"alpha[0]", 267},   {"alpha[1]", 268},   {"alpha[2]", 269},
    {"alpha[3]", 270},   {"beta[0]", 275},    {"beta[1]", 276},    {"beta[2]", 277},
    {"beta[3]", 278},    {"beta[4]", 279},    {"gamma[0]", 257},   {"gamma[1]", 259},
    {"gamma[2]", 260},   {"gamma[3]", 261},   {"gamma[4]", 262},   {"delta[0]", 257},
    {"delta[1]", 263},   {"delta[2]", 264},   {"delta[3]", 265},   {"delta[4]", 266},
    {"delta[5]", 258},   {"delta[6]", 271},   {"delta[7]", 272},   {"delta[8]", 273},
    {"delta[9]", 274},   {"generate", 256},   {"p_mipmaps", 255},  {"p_alpha[0]", 290},
    {"p_alpha[1]", 291}, {"p_alpha[2]", 292}, {"p_alpha[3]", 293}, {"p_beta[0]", 298},
    {"p_beta[1]", 299},  {"p_beta[2]", 300},  {"p_beta[3]", 301},  {"p_beta[4]", 302},
    {"p_gamma[0]", 280}, {"p_gamma[1]", 282}, {"p_gamma[2]", 283}, {"p_gamma[3]", 284},
    {"p_gamma[4]", 285}, {"p_delta[0]", 280}, {"p_delta[1]", 286}, {"p_delta[2]", 287},
    {"p_delta[3]", 288}, {"p_delta[4]", 289}, {"p_delta[5]", 281}, {"p_delta[6]", 294},
    {"p_delta[7]", 295}, {"p_delta[8]", 296}, {"p_delta[9]", 297}, {"p_generate", 256},
}};

std::unordered_map<uint32_t, std::vector<uint8_t>>& Resources() {
	static std::unordered_map<uint32_t, std::vector<uint8_t>> resources;
	return resources;
}

int OnResource(void*, const peparse::resource& res) {
	if (res.type != peparse::RT_RCDATA || res.buf == nullptr || res.buf->bufLen <= 0) return 0;
	std::vector<uint8_t> data(res.buf->bufLen);
	std::copy_n(res.buf->buf, res.buf->bufLen, data.data());
	Resources()[res.name] = std::move(data);
	return 0;
}

void Fail(char* error, size_t size, const std::string& text) {
	std::fprintf(stderr, "NOVA_FRAMEGEN: %s\n", text.c_str());
	if (error != nullptr && size != 0) {
		std::snprintf(error, size, "%s", text.c_str());
	}
}

} // namespace

// Used by the patched framegen Instance (tools/ci/build-android-lsfg.sh): create the
// frame-generation instance on the caller's driver (e.g. Turnip loaded by adrenotools)
// instead of the system Vulkan loader.
PFN_vkGetInstanceProcAddr NovaLsfgGetInstanceProcAddr() {
	return g_gipa;
}

extern "C" __attribute__((visibility("default"))) int nova_lsfg_init(
    const char* dll_path, void* get_instance_proc_addr, uint64_t device_id, int generations,
    float flow_scale, int performance, int hdr, char* error, size_t error_size) {
	std::lock_guard lock(g_mutex);
	if (g_initialized) return 0;
	if (dll_path == nullptr || get_instance_proc_addr == nullptr || generations < 1 || generations > 3 ||
	    !(flow_scale >= 0.25f && flow_scale <= 1.0f)) {
		Fail(error, error_size, "invalid frame-generation parameters");
		return -1;
	}
	try {
		Resources().clear();
		peparse::parsed_pe* dll = peparse::ParsePEFromFile(dll_path);
		if (dll == nullptr) {
			Fail(error, error_size, std::string("cannot read Lossless.dll at ") + dll_path);
			return -1;
		}
		peparse::IterRsrc(dll, OnResource, nullptr);
		peparse::DestructParsedPE(dll);
		for (const auto& [name, index]: kShaderResource) {
			if (Resources().find(index) == Resources().end()) {
				Fail(error, error_size, "shader " + name + " missing; is Lossless Scaling up to date?");
				return -1;
			}
		}
		g_gipa        = reinterpret_cast<PFN_vkGetInstanceProcAddr>(get_instance_proc_addr);
		g_performance = performance != 0;
		auto loader   = [](const std::string& name) {
            const auto hit = kShaderResource.find(name);
            if (hit == kShaderResource.end()) throw std::runtime_error("unknown shader " + name);
            return Extract::translateShader(Resources().at(hit->second));
		};
		if (g_performance) {
			LSFG_3_1P::initialize(device_id, hdr != 0, 1.0f / flow_scale, static_cast<uint64_t>(generations), loader);
		} else {
			LSFG_3_1::initialize(device_id, hdr != 0, 1.0f / flow_scale, static_cast<uint64_t>(generations), loader);
		}
		g_initialized = true;
		std::fprintf(stderr, "NOVA_FRAMEGEN: initialized (generations=%d flow_scale=%.2f mode=%s)\n", generations,
		             static_cast<double>(flow_scale), g_performance ? "performance" : "quality");
		return 0;
	} catch (const std::exception& e) {
		Fail(error, error_size, std::string("initialization failed: ") + e.what());
		return -1;
	}
}

extern "C" __attribute__((visibility("default"))) int nova_lsfg_create(
    AHardwareBuffer* in0, AHardwareBuffer* in1, AHardwareBuffer* const* outputs, int output_count,
    uint32_t width, uint32_t height, int vk_format, char* error, size_t error_size) {
	std::lock_guard lock(g_mutex);
	if (!g_initialized || in0 == nullptr || in1 == nullptr || outputs == nullptr || output_count < 1) {
		Fail(error, error_size, "frame generation is not initialized");
		return -1;
	}
#if defined(__ANDROID__)
	try {
		std::vector<AHardwareBuffer*> out(outputs, outputs + output_count);
		const VkExtent2D extent {width, height};
		const auto format = static_cast<VkFormat>(vk_format);
		return g_performance ? LSFG_3_1P::createContextFromAHB(in0, in1, out, extent, format)
		                     : LSFG_3_1::createContextFromAHB(in0, in1, out, extent, format);
	} catch (const std::exception& e) {
		Fail(error, error_size, std::string("context creation failed: ") + e.what());
		return -1;
	}
#else
	(void)width;
	(void)height;
	(void)vk_format;
	Fail(error, error_size, "AHardwareBuffer sharing requires Android");
	return -1;
#endif
}

extern "C" __attribute__((visibility("default"))) int nova_lsfg_present(int id, char* error, size_t error_size) {
	std::lock_guard lock(g_mutex);
	if (!g_initialized || id < 0) {
		Fail(error, error_size, "invalid frame-generation context");
		return -1;
	}
	try {
		const std::vector<int> no_semaphores;
		if (g_performance) {
			LSFG_3_1P::presentContext(id, -1, no_semaphores);
#if defined(__ANDROID__)
			LSFG_3_1P::waitIdle();
#endif
		} else {
			LSFG_3_1::presentContext(id, -1, no_semaphores);
#if defined(__ANDROID__)
			LSFG_3_1::waitIdle();
#endif
		}
		return 0;
	} catch (const std::exception& e) {
		Fail(error, error_size, std::string("generation failed: ") + e.what());
		return -1;
	}
}

extern "C" __attribute__((visibility("default"))) void nova_lsfg_destroy(int id) {
	std::lock_guard lock(g_mutex);
	if (!g_initialized || id < 0) return;
	try {
		if (g_performance) {
			LSFG_3_1P::deleteContext(id);
		} else {
			LSFG_3_1::deleteContext(id);
		}
	} catch (const std::exception&) {
	}
}
