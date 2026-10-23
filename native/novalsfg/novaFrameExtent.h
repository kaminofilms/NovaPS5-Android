// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <cstdint>
namespace Libs::Graphics::NovaFramegen {
struct WorkSize { uint32_t width, height; };
// Bound optical-flow work and shared-image storage independently of game rendering.
constexpr WorkSize WorkingSize(uint32_t width, uint32_t height) {
    if (!width || !height) return {width, height};
    if (width <= 1920 && height <= 1080) return {width, height};
    if (uint64_t(width) * 1080 >= uint64_t(height) * 1920)
        return {1920, std::max(1u, uint32_t(uint64_t(height) * 1920 / width))};
    return {std::max(1u, uint32_t(uint64_t(width) * 1080 / height)), 1080};
}
}
