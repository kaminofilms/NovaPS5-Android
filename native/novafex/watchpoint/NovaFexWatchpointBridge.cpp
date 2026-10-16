// SPDX-License-Identifier: MIT
#include "NovaFexTraceRing.hpp"
#include <unistd.h>

namespace NovaFexWatchpoint {
std::array<TrackedObject, MAX_TRACKED_OBJECTS> objects {};
std::atomic<uint32_t> enabled {0};
std::array<TraceSlot, TRACE_CAPACITY> slots {};
std::atomic<uint64_t> sequence {0}, dropped {0};
static_assert(std::atomic<uint32_t>::is_always_lock_free);
static_assert(std::atomic<uint64_t>::is_always_lock_free);

bool RegisterVerifiedObject(uint64_t base, uint64_t pointer, uint64_t length) noexcept {
  if (base < 0x10000 || base > UINT64_MAX - 0x48 ||
      pointer < 0x10000 || pointer > UINT64_MAX - 8 ||
      length < 0x10000 || length > UINT64_MAX - 8) return false;
  for (auto& slot : objects) {
    if (slot.state.load(std::memory_order_acquire) == 2 && slot.guest_base == base &&
        slot.host_pointer == pointer && slot.host_length == length) return true;
  }
  for (auto& slot : objects) {
    uint32_t empty = 0;
    if (!slot.state.compare_exchange_strong(empty, 1, std::memory_order_acquire, std::memory_order_relaxed)) continue;
    slot.guest_base = base;
    slot.host_pointer = pointer;
    slot.host_length = length;
    slot.state.store(2, std::memory_order_release);
    enabled.store(1, std::memory_order_release);
    return true;
  }
  return false;
}

Match MatchStore(uint64_t address, uint16_t width) noexcept {
  if (!enabled.load(std::memory_order_acquire) || !width || width > 8 || address > UINT64_MAX - width) return {};
  for (auto& slot : objects) {
    if (slot.state.load(std::memory_order_acquire) != 2) continue;
    uint8_t fields = 0;
    if (Overlap(address, width, slot.host_pointer, 8)) fields |= 1;
    if (Overlap(address, width, slot.host_length, 8)) fields |= 2;
    if (fields) {
      const uint64_t host = fields & 1 ? slot.host_pointer : slot.host_length;
      const uint64_t guest = slot.guest_base + (fields & 1 ? 0x38 : 0x40);
      // Reconstruct only from this verified field's host/guest correspondence.
      // Modular subtraction correctly covers stores starting before the field.
      return {slot.guest_base, guest + (address - host), fields};
    }
  }
  return {};
}

bool Capture(const StoreIntent& intent, const Match& match) noexcept {
  if (!match.base || !intent.width || intent.width > 8) return false;
  const uint64_t n = sequence.fetch_add(1, std::memory_order_relaxed);
  auto& slot = slots[n % TRACE_CAPACITY];
  uint8_t empty = 0;
  if (!slot.state.compare_exchange_strong(empty, 1, std::memory_order_acquire, std::memory_order_relaxed)) {
    dropped.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  slot.record = {n, match.base, intent, match.fields, true, false};
  slot.state.store(2, std::memory_order_release);
  return true;
}

bool TryReadTrace(size_t index, TraceRecord& out) noexcept {
  if (index >= TRACE_CAPACITY) return false;
  auto& slot = slots[index];
  uint8_t ready = 2;
  if (!slot.state.compare_exchange_strong(ready, 3, std::memory_order_acquire, std::memory_order_relaxed)) return false;
  out = slot.record;
  slot.state.store(0, std::memory_order_release);
  return true;
}

void BeforeStore(uint64_t address, uint64_t payload, uint64_t width, uint64_t rip) noexcept {
  if (width != 1 && width != 2 && width != 4 && width != 8) return;
  const auto match = MatchStore(address, static_cast<uint16_t>(width));
  if (!match.base) return;
  if (width < 8) payload &= (uint64_t {1} << (width * 8)) - 1;
  const StoreIntent intent {rip, match.address, payload, static_cast<uint32_t>(gettid()), static_cast<uint16_t>(width)};
  (void)Capture(intent, match);
}
}
