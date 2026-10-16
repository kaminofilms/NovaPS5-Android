// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace NovaFexWatchpoint {
constexpr size_t MAX_TRACKED_OBJECTS = 16;
// Caller verifies object identity and both backing field addresses. Slots are
// immutable for the process lifetime: no unsafe reclamation or speculative reads.
struct TrackedObject {
  std::atomic<uint32_t> state {0}; // 0 empty, 1 publishing, 2 active, 3 retired
  uint64_t guest_base {}, host_pointer {}, host_length {};
};
struct StoreIntent {
  uint64_t guest_rip {}, guest_address {}, payload {};
  uint32_t host_thread_id {};
  uint16_t width {};
};
struct Match { uint64_t base {}, address {}; uint8_t fields {}; };
extern std::array<TrackedObject, MAX_TRACKED_OBJECTS> objects;
extern std::atomic<uint32_t> enabled;
extern std::atomic<uint64_t> luna_constructor_rip, luna_destructor_rip, luna_vtable;
void LunaBoundary(uint64_t object, uint64_t vtable, uint64_t event) noexcept;
bool RetireVerifiedObject(uint64_t object) noexcept;
inline bool Overlap(uint64_t a, uint64_t n, uint64_t b, uint64_t m) noexcept {
  return n && m && a <= UINT64_MAX - n && b <= UINT64_MAX - m && a < b + m && b < a + n;
}
bool RegisterVerifiedObject(uint64_t guest_base, uint64_t host_pointer, uint64_t host_length) noexcept;
Match MatchStore(uint64_t host_address, uint16_t width) noexcept;
// Pre-store capture only. A record never asserts completion, including on fault.
void BeforeStore(uint64_t host_address, uint64_t payload, uint64_t width, uint64_t guest_rip) noexcept;
}
