#include "android_window.hpp"
#include <vulkan/vulkan_android.h>
#include <array>
#include <stdexcept>
namespace NovaAnyPS5 {
AndroidWindow::AndroidWindow(ANativeWindow* window, PFN_vkGetInstanceProcAddr instanceProc)
    : window(window), instanceProc(instanceProc) {
    if (!window || !instanceProc) throw std::invalid_argument("AnyPS5 Android window requires a native window and selected Vulkan driver");
    ANativeWindow_acquire(window);
}
AndroidWindow::~AndroidWindow() {
    ANativeWindow_release(window);
}
AgcDriver::PresentationWindow AndroidWindow::Descriptor() {
    static constexpr std::array<const char*, 2> extensions{
        VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_ANDROID_SURFACE_EXTENSION_NAME};
    std::uint32_t width = 0, height = 0;
    DrawableSize(this, &width, &height);
    return {this, extensions, CreateSurface, DrawableSize, width, height, {}};
}
VkSurfaceKHR AndroidWindow::CreateSurface(void* context, VkInstance instance) {
    auto& self = *static_cast<AndroidWindow*>(context);
    const auto create = reinterpret_cast<PFN_vkCreateAndroidSurfaceKHR>(self.instanceProc(instance, "vkCreateAndroidSurfaceKHR"));
    if (!create) throw std::runtime_error("Selected Vulkan driver has no Android surface entry point");
    VkAndroidSurfaceCreateInfoKHR info{VK_STRUCTURE_TYPE_ANDROID_SURFACE_CREATE_INFO_KHR};
    info.window = self.window;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    if (create(instance, &info, nullptr, &surface) != VK_SUCCESS)
        throw std::runtime_error("AnyPS5 Android surface creation failed");
    return surface;
}
void AndroidWindow::DrawableSize(void* context, std::uint32_t* width, std::uint32_t* height) {
    auto& self = *static_cast<AndroidWindow*>(context);
    const auto w = ANativeWindow_getWidth(self.window);
    const auto h = ANativeWindow_getHeight(self.window);
    *width = w > 0 ? static_cast<std::uint32_t>(w) : 0;
    *height = h > 0 ? static_cast<std::uint32_t>(h) : 0;
}
}
