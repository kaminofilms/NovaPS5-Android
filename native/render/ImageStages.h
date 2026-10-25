// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <vulkan/vulkan_core.h>

namespace NovaRender {
// Image::Transit has access information, but no shader-stage visibility. Keep
// shader consumers conservative; fixed-function accesses have precise stages.
inline VkPipelineStageFlags2 ImageStages(VkAccessFlags2 access) {
    VkPipelineStageFlags2 stages = 0;
    const VkAccessFlags2 transfer = VK_ACCESS_2_TRANSFER_READ_BIT | VK_ACCESS_2_TRANSFER_WRITE_BIT;
    const VkAccessFlags2 color = VK_ACCESS_2_COLOR_ATTACHMENT_READ_BIT | VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT;
    const VkAccessFlags2 depth = VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_READ_BIT | VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;
    const VkAccessFlags2 shader = VK_ACCESS_2_SHADER_READ_BIT | VK_ACCESS_2_SHADER_WRITE_BIT |
        VK_ACCESS_2_SHADER_SAMPLED_READ_BIT | VK_ACCESS_2_SHADER_STORAGE_READ_BIT | VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT;
    const VkAccessFlags2 host = VK_ACCESS_2_HOST_READ_BIT | VK_ACCESS_2_HOST_WRITE_BIT;
    const VkAccessFlags2 input = VK_ACCESS_2_INPUT_ATTACHMENT_READ_BIT;
    const VkAccessFlags2 known = transfer | color | depth | shader | host | input;
    // Generic memory accesses, extension accesses, and unknown accesses must
    // never be narrowed using assumptions about a game's resource usage.
    if (!access || (access & ~known)) return VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT;
    if (access & transfer) stages |= VK_PIPELINE_STAGE_2_ALL_TRANSFER_BIT;
    if (access & color) stages |= VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT;
    if (access & depth) stages |= VK_PIPELINE_STAGE_2_EARLY_FRAGMENT_TESTS_BIT | VK_PIPELINE_STAGE_2_LATE_FRAGMENT_TESTS_BIT;
    if (access & shader) stages |= VK_PIPELINE_STAGE_2_ALL_GRAPHICS_BIT | VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT;
    if (access & host) stages |= VK_PIPELINE_STAGE_2_HOST_BIT;
    if (access & input) stages |= VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT;
    return stages;
}
}
