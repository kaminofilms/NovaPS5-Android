// Nova PS5: C interface of libnovalsfg.so (Lossless Scaling frame generation).
// SPDX-License-Identifier: MIT
//
// Wraps lsfg-vk 1.0.0 (MIT, PancakeTAS) with the Android AHardwareBuffer patches of
// lsfg-vk-android (MIT, FrankBarretta). The frame-generation shaders are extracted at
// run time from the user's own Lossless.dll; no Lossless Scaling code or data ships
// with Nova. Every function returns 0 / a valid id on success and writes a message to
// `error` (if not null) on failure; no C++ exception crosses this boundary.
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct AHardwareBuffer;

// Loads and translates the shaders, creates the frame-generation Vulkan device on the
// same driver as the caller (`get_instance_proc_addr`) and the physical device whose
// (vendorID << 32 | deviceID) is `device_id`. generations = multiplier - 1 (1..3).
int nova_lsfg_init(const char* dll_path, void* get_instance_proc_addr, uint64_t device_id,
                   int generations, float flow_scale, int performance, int hdr,
                   char* error, size_t error_size);

// Images are shared through AHardwareBuffers owned by the caller (R16G16B16A16_SFLOAT
// when hdr == 0, R8G8B8A8_UNORM when hdr == 1, as lsfg-vk). Returns an id >= 0 or -1.
int nova_lsfg_create(struct AHardwareBuffer* in0, struct AHardwareBuffer* in1,
                     struct AHardwareBuffer* const* outputs, int output_count,
                     uint32_t width, uint32_t height, int vk_format,
                     char* error, size_t error_size);

// Generates the intermediate frames between the two most recent inputs and waits for
// the frame-generation device to finish (CPU-synchronous; no shared semaphores).
int nova_lsfg_present(int id, char* error, size_t error_size);

void nova_lsfg_destroy(int id);

#ifdef __cplusplus
}
#endif
