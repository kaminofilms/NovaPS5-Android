#pragma once
#include "prx/libSceAgcDriver/Execution/include/Presentation.hpp"
#include <android/native_window.h>
namespace NovaAnyPS5 {
class __attribute__((visibility("default"))) AndroidWindow final {
public:
    AndroidWindow(ANativeWindow* window, PFN_vkGetInstanceProcAddr instanceProc);
    ~AndroidWindow();
    AndroidWindow(const AndroidWindow&) = delete;
    AndroidWindow& operator=(const AndroidWindow&) = delete;
    AgcDriver::PresentationWindow Descriptor();
private:
    static VkSurfaceKHR CreateSurface(void* context, VkInstance instance);
    static void DrawableSize(void* context, std::uint32_t* width, std::uint32_t* height);
    ANativeWindow* window;
    PFN_vkGetInstanceProcAddr instanceProc;
};
}
