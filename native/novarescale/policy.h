#pragma once

// Nova's independent render-target scaling policy. No renderer or Android dependencies.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <atomic>
#include <chrono>
#include <cstdio>

namespace NovaRescale {
inline constexpr uint32_t Revision = 64;
inline constexpr uint32_t MaxBindings = 32;
inline constexpr uint32_t SpecBase = 400;
inline constexpr uint32_t WordsPerBinding = 4; // guest width/height, host width/height
inline constexpr uint32_t StageWords = MaxBindings * WordsPerBinding;
using StageData = uint32_t[StageWords];
struct PipelineData {
    StageData stages[4] {};
};

constexpr uint32_t ParsePermille(const char* text) {
    if (text == nullptr || *text == '\0') return 1000;
    uint32_t value = 0;
    for (const char* p = text; *p; ++p) {
        if (*p < '0' || *p > '9' || value > 1000) return 1000;
        value = value * 10 + uint32_t(*p - '0');
    }
    return value >= 250 && value <= 1000 ? value : 1000;
}

inline uint32_t Permille() {
    static const uint32_t value = ParsePermille(std::getenv("NOVA_RESCALE_PERMILLE"));
    return value;
}
inline bool Enabled() { return Permille() < 1000; }

inline void Note(bool allocation, const char* reason) {
    static std::atomic<uint64_t> allocations{0}, fallbacks{0};
    const auto n = (allocation ? allocations : fallbacks).fetch_add(1, std::memory_order_relaxed)+1;
    if (n<=8 || n%128==0)
        std::fprintf(stderr,"NOVA_RESCALE: scaled_images=%llu fallbacks=%llu reason=%s permille=%u\n",
            (unsigned long long)allocations.load(std::memory_order_relaxed),
            (unsigned long long)fallbacks.load(std::memory_order_relaxed),reason,Permille());
}

constexpr uint32_t Dimension(uint32_t guest, uint32_t permille) {
    return uint32_t((uint64_t(guest) * permille + 999) / 1000);
}

struct Candidate {
    uint32_t width, height, depth, layers, levels, samples;
    bool target, block_compressed, storage, cpu_upload;
};

constexpr bool Eligible(const Candidate& c, uint32_t permille) {
    return permille >= 250 && permille < 1000 && c.target && !c.block_compressed &&
           !c.storage && !c.cpu_upload && c.width >= 1280 && c.height >= 720 &&
           c.depth == 1 && c.layers == 1 && c.levels == 1 && c.samples == 1;
}

// A pass must use the same host/guest ratio in every bound attachment. Compare
// rational ratios, not floating-point approximations (ceil rounding can differ).
constexpr bool Compatible(uint32_t aw, uint32_t ah, uint32_t agw, uint32_t agh,
                          uint32_t bw, uint32_t bh, uint32_t bgw, uint32_t bgh) {
    return agw && agh && bgw && bgh &&
           uint64_t(aw) * bgw == uint64_t(bw) * agw &&
           uint64_t(ah) * bgh == uint64_t(bh) * agh;
}

inline PipelineData& Pending() {
    static thread_local PipelineData data {};
    return data;
}
} // namespace NovaRescale
