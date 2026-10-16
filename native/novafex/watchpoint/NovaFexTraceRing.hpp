// SPDX-License-Identifier: MIT
#pragma once
#include "NovaFexWatchpoint.safe.hpp"
namespace NovaFexWatchpoint {
constexpr size_t TRACE_CAPACITY = 1024;
struct TraceRecord {
  uint64_t sequence {}, matched_base {};
  StoreIntent intent {};
  uint8_t fields {};
  bool attempted {true};
  bool completed {false};
};
struct TraceSlot {
  std::atomic<uint8_t> state {0}; // free, writing, ready, reading
  TraceRecord record {};
};
extern std::array<TraceSlot, TRACE_CAPACITY> slots;
extern std::atomic<uint64_t> sequence, dropped;
bool Capture(const StoreIntent& intent, const Match& match) noexcept;
bool TryReadTrace(size_t index, TraceRecord& out) noexcept;
}
