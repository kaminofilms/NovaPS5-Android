#pragma once
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#if defined(__ANDROID__)
#include <sys/system_properties.h>
#endif

namespace NovaRender {
enum class ReadbackCaller : unsigned { HandleFaultRead, HandleFaultWrite, ComputeLds,
    TextureMetadata, InvalidateMemory, GarbageCollection, Other, Count };
struct ReadbackContext {
    ReadbackCaller caller;
    uint64_t fault_addr;
    uint64_t fault_size;
    bool is_fault_origin;
};
inline bool ReadbackProfile() {
    static const bool enabled = [] {
#if defined(__ANDROID__)
        char property[PROP_VALUE_MAX] {};
        // Explicit diagnostic opt-in for titles whose installed ID is unknown.
        if (__system_property_get("debug.novaps5.readback", property) > 0 &&
            std::string_view(property) == "1") return true;
#endif
        const char* explicit_enable = std::getenv("NOVA_READBACK_TELEMETRY");
        const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
        return (explicit_enable && std::string_view(explicit_enable) == "1") ||
               (title && std::string_view(title) == "PPSA04703");
    }();
    return enabled;
}
// Compare lengths by subtraction; even a span ending at 2^64 is well-defined.
inline bool ReadbackIntersects(uint64_t a, uint64_t n, uint64_t b, uint64_t m) noexcept {
    return n && m && (a <= b ? b - a < n : a - b < m);
}
inline bool ReadbackContains(uint64_t a, uint64_t n, uint64_t b, uint64_t m) noexcept {
    return m && b >= a && b - a < n && m <= n - (b - a);
}
struct ReadbackClassification {
    uint64_t copied_bytes = 0, copy_ranges = 0, tracker_ranges = 0;
    bool overlap = false, promoted = false;
    void Tracker(uint64_t request_addr, uint64_t request_size,
                 uint64_t callback_addr, uint64_t callback_size) noexcept {
        ++tracker_ranges;
        // Actual original request and tracker callback, not request-vs-byte count.
        promoted |= !ReadbackContains(request_addr, request_size, callback_addr, callback_size);
    }
    void Copy(ReadbackContext context, uint64_t base, uint64_t offset, uint64_t size) noexcept {
        copied_bytes += size;
        ++copy_ranges;
        // Invalid coordinates are never turned into a wrapping guest address.
        if (offset <= UINT64_MAX - base && context.is_fault_origin)
            overlap |= ReadbackIntersects(context.fault_addr, context.fault_size, base + offset, size);
    }
};
enum class ReadbackField : unsigned { Calls, ZeroCopy, Bytes, Ranges, TrackerRanges,
    Overlap, Disjoint, Promotion, WaitNs, PriorityWaitNs, PublishNs, DeferredWaitNs, Count };
inline constexpr unsigned ReadbackCallers = unsigned(ReadbackCaller::Count);
inline constexpr unsigned ReadbackFields = unsigned(ReadbackField::Count);
inline std::array<std::array<std::atomic<uint64_t>, ReadbackFields>, ReadbackCallers> readback_totals {};
inline const auto readback_start = std::chrono::steady_clock::now();
inline void AddReadback(ReadbackCaller caller, ReadbackField field, uint64_t value) noexcept {
    if (unsigned(caller) < ReadbackCallers)
        readback_totals[unsigned(caller)][unsigned(field)].fetch_add(value, std::memory_order_relaxed);
}
inline void RecordReadback(ReadbackContext context, const ReadbackClassification& c) noexcept {
    AddReadback(context.caller, ReadbackField::Calls, 1);
    AddReadback(context.caller, ReadbackField::Bytes, c.copied_bytes);
    AddReadback(context.caller, ReadbackField::Ranges, c.copy_ranges);
    AddReadback(context.caller, ReadbackField::TrackerRanges, c.tracker_ranges);
    AddReadback(context.caller, ReadbackField::Overlap, c.overlap);
    AddReadback(context.caller, ReadbackField::Disjoint,
                context.is_fault_origin && context.fault_size && !c.overlap);
    AddReadback(context.caller, ReadbackField::Promotion, c.promoted);
}
struct ReadbackTicket {
    ReadbackCaller caller = ReadbackCaller::Other;
    bool enabled = false;
};
class ReadbackTimer {
    using Clock = std::chrono::steady_clock;
    ReadbackTicket ticket;
    ReadbackField field;
    Clock::time_point start {};
public:
    ReadbackTimer(ReadbackTicket t, ReadbackField f) : ticket(t), field(f) {
        if (ticket.enabled) start = Clock::now();
    }
    ~ReadbackTimer() {
        if (ticket.enabled) AddReadback(ticket.caller, field,
            uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count()));
    }
};
// Cumulative snapshots avoid exchange/reset races losing independent fields.
// The dumper is serialized without affecting producers. Fields near a sampling
// boundary can straddle adjacent windows; they are not a transactional tuple.
inline void DumpReadbackCounters() noexcept {
    if (!ReadbackProfile()) return;
    static std::atomic_flag dumping = ATOMIC_FLAG_INIT;
    if (dumping.test_and_set(std::memory_order_acquire)) return;
    using Clock = std::chrono::steady_clock;
    static auto begin = readback_start;
    static std::array<std::array<uint64_t, ReadbackFields>, ReadbackCallers> previous {};
    const auto end = Clock::now();
    if (end - begin < std::chrono::seconds(5)) {
        dumping.clear(std::memory_order_release); return;
    }
    const auto wall = std::chrono::duration<double, std::milli>(end - begin).count();
    constexpr const char* names[] = {"HandleFaultRead", "HandleFaultWrite", "ComputeLds",
        "TextureMetadata", "InvalidateMemory", "GarbageCollection", "Other"};
    for (unsigned i = 0; i < ReadbackCallers; ++i) {
        std::array<uint64_t, ReadbackFields> delta {};
        bool any = false;
        for (unsigned j = 0; j < ReadbackFields; ++j) {
            const auto current = readback_totals[i][j].load(std::memory_order_relaxed);
            delta[j] = current - previous[i][j]; previous[i][j] = current;
            any |= delta[j] != 0;
        }
        if (!any) continue;
        auto v = [&](ReadbackField f) { return static_cast<unsigned long long>(delta[unsigned(f)]); };
        std::fprintf(stderr, "NOVA_RENDER_COST: readback_caller=%s window_ms=%.1f calls=%llu zero_copy=%llu copied_bytes=%llu copy_ranges=%llu tracker_ranges=%llu direct_overlap=%llu address_disjoint=%llu page_promotion_candidates=%llu wait_ms=%.3f priority_wait_ms=%.3f publish_ms=%.3f deferred_gpu_wait_ms=%.3f\n",
            names[i], wall, v(ReadbackField::Calls), v(ReadbackField::ZeroCopy), v(ReadbackField::Bytes),
            v(ReadbackField::Ranges), v(ReadbackField::TrackerRanges), v(ReadbackField::Overlap),
            v(ReadbackField::Disjoint), v(ReadbackField::Promotion), double(v(ReadbackField::WaitNs))/1e6,
            double(v(ReadbackField::PriorityWaitNs))/1e6, double(v(ReadbackField::PublishNs))/1e6,
            double(v(ReadbackField::DeferredWaitNs))/1e6);
    }
    begin = end;
    dumping.clear(std::memory_order_release);
}
} // namespace NovaRender
