#pragma once
#include <vulkan/vulkan.h>
namespace NovaRender {
inline bool CanOmitDepthStore(uint32_t apiVersion,bool scaled,VkImageAspectFlags writes,bool depthClear,bool stencilClear){
 return apiVersion>=VK_API_VERSION_1_3&&!scaled&&writes==0&&!depthClear&&!stencilClear;
}
}
