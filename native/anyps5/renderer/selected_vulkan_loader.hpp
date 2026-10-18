#pragma once
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <memory>
namespace NovaAnyPS5 {
void ConfigureSelectedVulkan(PFN_vkGetInstanceProcAddr instanceProc, std::shared_ptr<void> lifetime);
void* LoadSelectedVulkan(const char* requestedName);
void* SelectedVulkanSymbol(void* lease, const char* name);
void ReleaseSelectedVulkan(void* lease);
const char* SelectedVulkanError();
}
