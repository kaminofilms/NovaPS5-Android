#pragma once

#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#if defined(__linux__)
#include <unistd.h>
#else
#include <functional>
#include <thread>
#endif

namespace NovaRender {
inline bool EverProfile() {
    static const bool enabled = [] {
        const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
        return title && std::string_view(title) == "PPSA04703";
    }();
    return enabled;
}
enum class Cost : unsigned { Draw, Dispatch, Shader, Pipeline, Submit, Wait, Present, Snapshot,
    EopDrain, Readback, RingReuse, FaultReuse, Count };
struct Costs {
    using Clock = std::chrono::steady_clock;
    struct Entry { uint64_t calls = 0, ns = 0, max_ns = 0; };
    std::array<Entry, unsigned(Cost::Count)> entries {};
    Clock::time_point begin = Clock::now();
    unsigned depth = 0;
    void Finish(Cost cost, Clock::time_point start) {
        const auto end = Clock::now();
        const auto ns = uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
        auto& entry = entries[unsigned(cost)];
        ++entry.calls;
        entry.ns += ns;
        if (ns > entry.max_ns) entry.max_ns = ns;
        if (--depth != 0 || end - begin < std::chrono::seconds(5)) return;
#if defined(__linux__)
        const auto tid = uint64_t(gettid());
#else
        const auto tid = uint64_t(std::hash<std::thread::id>{}(std::this_thread::get_id()));
#endif
        constexpr const char* names[] = {"draw", "dispatch", "shader", "pipeline", "submit", "wait", "present", "snapshot",
            "eop_drain", "readback", "ring_reuse", "fault_reuse"};
        static_assert(std::size(names) == unsigned(Cost::Count));
        // Inclusive scopes overlap. Host wait duration is not GPU execution time.
        const auto wall = std::chrono::duration<double, std::milli>(end - begin).count();
        for (unsigned i = 0; i < entries.size(); ++i) {
            const auto& e = entries[i];
            if (e.calls) std::fprintf(stderr,
                "NOVA_RENDER_COST: tid=%llu window_ms=%.1f scope=%s calls=%llu inclusive_ms=%.3f max_ms=%.3f\n",
                (unsigned long long)tid, wall, names[i], (unsigned long long)e.calls,
                double(e.ns) / 1e6, double(e.max_ns) / 1e6);
        }
        entries = {};
        begin = end;
    }
};
inline thread_local Costs costs;
class Scope final {
public:
    explicit Scope(Cost value) : cost(value), start(Costs::Clock::now()) { ++costs.depth; }
    ~Scope() { costs.Finish(cost, start); }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
private:
    Cost cost;
    Costs::Clock::time_point start;
};
} // namespace NovaRender
