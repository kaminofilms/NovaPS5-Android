// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <ctime>

namespace NovaFex::Timing {
enum class Domain : unsigned { Idle, GuestRuntime, HostCall };
struct Stamp { uint64_t wall = 0, cpu = 0; bool valid = false; };
inline Stamp Now() noexcept {
    timespec wall{}, cpu{};
    if (clock_gettime(CLOCK_MONOTONIC, &wall) ||
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu)) return {};
    return {uint64_t(wall.tv_sec) * 1000000000u + uint64_t(wall.tv_nsec),
            uint64_t(cpu.tv_sec) * 1000000000u + uint64_t(cpu.tv_nsec), true};
}
inline bool Enabled() noexcept {
    static const bool enabled = [] {
        const char* value = std::getenv("NOVA_FEX_PROFILE");
        return value && value[0] == '1' && value[1] == '\0';
    }();
    return enabled;
}
struct Totals {
    std::array<std::atomic<uint64_t>, 3> wall{}, cpu{};
    std::atomic<uint64_t> invalid{0};
};
inline Totals totals;
// Owner-thread state only. Totals include completed exclusive slices, never a
// live interval: a blocked native call is published on its next boundary.
struct State {
    Domain domain = Domain::Idle;
    Stamp start{};
    Domain Enter(Domain next, Stamp stamp) noexcept {
        const auto previous = domain;
        if (previous != Domain::Idle && start.valid && stamp.valid &&
            stamp.wall >= start.wall && stamp.cpu >= start.cpu) {
            const auto index = static_cast<unsigned>(previous);
            totals.wall[index].fetch_add(stamp.wall - start.wall, std::memory_order_relaxed);
            totals.cpu[index].fetch_add(stamp.cpu - start.cpu, std::memory_order_relaxed);
        } else if (previous != Domain::Idle) {
            totals.invalid.fetch_add(1, std::memory_order_relaxed);
        }
        domain = next;
        start = stamp;
        return previous;
    }
};
inline thread_local State state;
class Scope {
    bool enabled;
    Domain previous = Domain::Idle;
public:
    explicit Scope(Domain domain) noexcept : enabled(Enabled()) {
        if (enabled) previous = state.Enter(domain, Now());
    }
    ~Scope() { if (enabled) state.Enter(previous, Now()); }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
};
struct Snapshot {
    uint64_t guest_wall = 0, guest_cpu = 0, host_wall = 0, host_cpu = 0, invalid = 0;
};
inline Snapshot Read() noexcept {
    return {totals.wall[1].load(std::memory_order_relaxed),
            totals.cpu[1].load(std::memory_order_relaxed),
            totals.wall[2].load(std::memory_order_relaxed),
            totals.cpu[2].load(std::memory_order_relaxed),
            totals.invalid.load(std::memory_order_relaxed)};
}
inline uint64_t OffCpu(uint64_t wall, uint64_t cpu) noexcept {
    return wall > cpu ? wall - cpu : 0;
}
} // namespace NovaFex::Timing
