#pragma once
#include "video_platform.hpp"
#include <stdexcept>
class DisplayWindow {
public:
    void Ensure(std::uint32_t sourceWidth, std::uint32_t sourceHeight) {
        if (!sourceWidth || !sourceHeight) throw std::invalid_argument("AnyPS5 source extent is zero");
        const auto target = NovaAnyPS5::Video().window();
        if (!target.context || !target.createSurface || !target.getDrawableSize)
            throw std::runtime_error("Nova Android presentation window is unavailable");
        attached = true;
    }
    void Destroy() noexcept { attached = false; }
    void* Handle() const { return attached ? NovaAnyPS5::Video().window().context : nullptr; }
    void DrawableSize(std::uint32_t& width, std::uint32_t& height) const {
        const auto target = NovaAnyPS5::Video().window();
        target.getDrawableSize(target.context, &width, &height);
    }
private:
    bool attached = false;
};
