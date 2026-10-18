#include "video_platform.hpp"
#include <atomic>
#include <mutex>
#include <stdexcept>
namespace NovaAnyPS5 {
namespace {
VideoPlatform configured{};
std::mutex configureMutex;
std::atomic<const VideoPlatform*> current{nullptr};
}
void ConfigureVideoPlatform(const VideoPlatform& platform) {
    if (!platform.window || !platform.refreshRate || !platform.framePresented || !platform.requestExit ||
        !platform.appAttribute3 || !platform.processTime || !platform.processTimeCounter)
        throw std::invalid_argument("AnyPS5 native video platform is incomplete");
    std::lock_guard lock(configureMutex);
    if (current.load(std::memory_order_acquire)) throw std::logic_error("AnyPS5 native video platform is already configured");
    configured = platform;
    current.store(&configured, std::memory_order_release);
}
const VideoPlatform& Video() {
    const auto* platform = current.load(std::memory_order_acquire);
    if (!platform) throw std::logic_error("AnyPS5 native video platform is not configured");
    return *platform;
}
}

extern "C" std::uint32_t GetAppAttribute3_nid_no_patch() { return NovaAnyPS5::Video().appAttribute3(); }
