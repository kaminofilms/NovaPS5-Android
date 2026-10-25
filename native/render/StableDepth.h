// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <vulkan/vulkan_core.h>
namespace NovaRender {
// An unsampled attachment may retain a writable layout while a draw disables
// depth/stencil writes in its pipeline. Do not apply this to sampled/bound
// resources, partial views, or separately tracked subresources.
inline VkImageLayout StableDepthLayout(VkImageLayout current,VkImageLayout requested,
    VkImageAspectFlags aspects,bool sampled,bool bound,bool whole) {
    if(sampled||bound||!whole)return requested;
    const auto ds=VK_IMAGE_ASPECT_DEPTH_BIT|VK_IMAGE_ASPECT_STENCIL_BIT;
    if(aspects==ds && current==VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL &&
       (requested==VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL ||
        requested==VK_IMAGE_LAYOUT_DEPTH_STENCIL_READ_ONLY_OPTIMAL ||
        requested==VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_STENCIL_READ_ONLY_OPTIMAL ||
        requested==VK_IMAGE_LAYOUT_DEPTH_READ_ONLY_STENCIL_ATTACHMENT_OPTIMAL))return current;
    if(aspects==VK_IMAGE_ASPECT_DEPTH_BIT && current==VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_OPTIMAL &&
       (requested==VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_OPTIMAL || requested==VK_IMAGE_LAYOUT_DEPTH_READ_ONLY_OPTIMAL))return current;
    if(aspects==VK_IMAGE_ASPECT_STENCIL_BIT && current==VK_IMAGE_LAYOUT_STENCIL_ATTACHMENT_OPTIMAL &&
       (requested==VK_IMAGE_LAYOUT_STENCIL_ATTACHMENT_OPTIMAL || requested==VK_IMAGE_LAYOUT_STENCIL_READ_ONLY_OPTIMAL))return current;
    return requested;
}
}
