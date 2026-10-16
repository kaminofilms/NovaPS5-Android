// SPDX-License-Identifier: MIT
#include "../native/novafex/watchpoint/NovaFexTraceRing.hpp"
#include <cassert>
#include <thread>
#include <vector>
#include <cstdio>
using namespace NovaFexWatchpoint;
int main() {
  assert(!enabled.load());
  BeforeStore(0x200038, 0x42c80000, 4, 0x900123456);
  assert(sequence.load() == 0);
  assert(!RegisterVerifiedObject(0, 0x200038, 0x200040));
  assert(!RegisterVerifiedObject(UINT64_MAX - 4, 0x200038, 0x200040));
  assert(RegisterVerifiedObject(0x9000000000, 0x200038, 0x200040));
  assert(!MatchStore(0x200030, 8).base);
  auto m = MatchStore(0x200037, 2);
  assert(m.address == 0x9000000037 && m.fields == 1);
  m = MatchStore(0x20003f, 2);
  assert(m.address == 0x900000003f && m.fields == 3);
  assert(!MatchStore(UINT64_MAX - 3, 8).base);
  assert(!MatchStore(0x200048, 1).base);
  BeforeStore(0x200040, 0x1234567842c80000, 4, 0x900123456);
  TraceRecord r;
  assert(TryReadTrace(0, r));
  assert(r.intent.guest_rip == 0x900123456 && r.intent.guest_address == 0x9000000040);
  assert(r.intent.payload == 0x42c80000 && r.intent.width == 4 && r.intent.host_thread_id);
  assert(r.attempted && !r.completed && r.fields == 2);
  assert(!TryReadTrace(0, r));
  // Separated field mappings must preserve the verified guest correspondence.
  assert(RegisterVerifiedObject(0x9100000000, 0x300ff8, 0x500000));
  assert(MatchStore(0x500000, 8).address == 0x9100000040);
  std::vector<std::thread> threads;
  for (unsigned t = 0; t < 8; ++t) threads.emplace_back([] {
    for (unsigned n = 0; n < 300; ++n) BeforeStore(0x200038, n, 8, 0x912345678);
  });
  for (auto& t : threads) t.join();
  unsigned count = 0;
  for (size_t i = 0; i < TRACE_CAPACITY; ++i) if (TryReadTrace(i, r)) {
    assert(r.intent.guest_rip == 0x912345678 && r.attempted && !r.completed);
    ++count;
  }
  assert(count == TRACE_CAPACITY && dropped.load() > 0);
  assert(sequence.load() == 2401);
  std::puts("NOVA_WATCHPOINT_HOST: ALL PASS");
}
