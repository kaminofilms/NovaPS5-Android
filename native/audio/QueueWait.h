// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <cstdint>
namespace NovaAudio {
// SDL reports queued input bytes. Sleep only while above the existing target;
// cap each sleep at 5 ms so close/error/signal handling remains responsive.
inline uint32_t QueueWaitMicros(int queued, uint32_t target, uint32_t frameBytes, uint32_t rate) {
    if (queued<=0 || uint64_t(queued)<=target) return 0;
    if (!frameBytes || !rate) return 1000; // retain the old bounded wait on invalid metadata
    const uint64_t excess=uint64_t(queued)-target;
    const uint64_t us=excess*1000000ull/(uint64_t(frameBytes)*rate);
    return uint32_t(std::clamp<uint64_t>(us,1000,5000));
}
}
