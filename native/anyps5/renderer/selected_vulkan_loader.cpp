#include "selected_vulkan_loader.hpp"
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <string>
namespace NovaAnyPS5 {
namespace {
struct Driver {
    PFN_vkGetInstanceProcAddr instanceProc;
    std::shared_ptr<void> lifetime;
};
std::mutex driverMutex;
std::shared_ptr<const Driver> selected;
thread_local std::string lastError;
}
void ConfigureSelectedVulkan(PFN_vkGetInstanceProcAddr instanceProc, std::shared_ptr<void> lifetime) {
    if (!instanceProc || !lifetime) throw std::invalid_argument("AnyPS5 requires the selected Vulkan driver and its lifetime owner");
    auto driver = std::make_shared<const Driver>(Driver{instanceProc, std::move(lifetime)});
    std::lock_guard lock(driverMutex);
    selected = std::move(driver);
}
void* LoadSelectedVulkan(const char* requestedName) {
    if (!requestedName || (std::strcmp(requestedName, "libvulkan.so.1") && std::strcmp(requestedName, "libvulkan.so") && std::strcmp(requestedName, "vulkan-1.dll"))) {
        lastError = "AnyPS5 requested an unsupported loader library";
        return nullptr;
    }
    std::lock_guard lock(driverMutex);
    if (!selected) {
        lastError = "Nova has not supplied its selected Vulkan driver to AnyPS5";
        return nullptr;
    }
    return new std::shared_ptr<const Driver>(selected);
}
void* SelectedVulkanSymbol(void* lease, const char* name) {
    if (!lease || !name || std::strcmp(name, "vkGetInstanceProcAddr")) {
        lastError = "AnyPS5 requested an unsupported Vulkan loader symbol";
        return nullptr;
    }
    return reinterpret_cast<void*>((*static_cast<std::shared_ptr<const Driver>*>(lease))->instanceProc);
}
void ReleaseSelectedVulkan(void* lease) {
    delete static_cast<std::shared_ptr<const Driver>*>(lease);
}
const char* SelectedVulkanError() {
    return lastError.c_str();
}
}
