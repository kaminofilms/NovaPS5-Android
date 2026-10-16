#pragma once
#include <array>
#include <cstddef>
#include <iterator>
#include <cstdint>
#include <cstring>
#include <map>
#include <optional>

namespace NovaRender {
// Owned exclusively by the serialized guest GPU thread. These are immutable
// bytes that were actually recorded for upload, never predicted GPU results.
class EopLabels {
public:
    struct Entry {
        uint64_t address, size, tick;
        std::array<uint8_t, 8> bytes {};
    };
    static constexpr size_t Capacity = 4096;
    void Invalidate(uint64_t address, uint64_t size) {
        if (!size || entries.empty()) return;
        if (size > UINT64_MAX - address) { entries.clear(); return; }
        const auto end = address + size;
        auto it = entries.lower_bound(address);
        if (it != entries.begin()) {
            auto before = std::prev(it);
            if (address - before->first < before->second.size) it = before;
        }
        while (it != entries.end() && it->first < end) it = entries.erase(it);
    }
    void Record(uint64_t address, const void* data, uint64_t size, uint64_t tick) {
        if (!address || !data || (size != 4 && size != 8) || size > UINT64_MAX-address || !tick) return;
        Invalidate(address, size);
        // Eviction only loses the fast path; normal coherent readback remains.
        if (entries.size() >= Capacity) entries.clear();
        Entry e {address, size, tick, {}};
        std::memcpy(e.bytes.data(), data, size);
        entries.emplace(address, e);
    }
    std::optional<Entry> Find(uint64_t address, uint64_t size) const {
        if (!size || size > 8 || size > UINT64_MAX-address) return {};
        auto it = entries.upper_bound(address);
        if (it == entries.begin()) return {};
        const auto& e = std::prev(it)->second;
        const auto offset = address-e.address;
        if (offset >= e.size || size > e.size-offset) return {};
        return e; // Never retain map iterators across scheduler calls.
    }
    size_t Size() const { return entries.size(); }
private:
    std::map<uint64_t, Entry> entries;
};
} // namespace NovaRender
