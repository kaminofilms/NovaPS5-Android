// SPDX-License-Identifier: MIT
#include "../native/novafex/watchpoint/NovaFexTraceRing.hpp"
#include "../native/novafex/watchpoint/NovaFexLunaProfile.hpp"
#include <map>
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
  assert(RetireVerifiedObject(0x9000000000));
  assert(!MatchStore(0x200038, 8).base);
  assert(!RetireVerifiedObject(0x9000000000));
  // Retired immutable slots never silently track a reused allocation.
  assert(RegisterVerifiedObject(0x9000000000, 0x200038, 0x200040));
  assert(MatchStore(0x200038, 8).base == 0x9000000000);
  std::map<uint64_t, uint8_t> image;
  constexpr uint64_t module_base = 0x900000000;
  const auto put = [&](uint64_t rva, const auto& bytes) {
    for (size_t i = 0; i < bytes.size(); ++i) image[module_base + rva + i] = bytes[i];
  };
  put(0xf2fc80, kLuna_constructor); put(0xf2f9bc, kLuna_class_registration);
  put(0x6663e2e, kLuna_class_name); put(0x67ba62c, kLuna_property_name);
  put(0x6f107d8, kLuna_property_layout); put(0xf3b5b0, kLuna_destructor);
  const auto read = [&](uint64_t address, void* out, size_t count) {
    for (size_t i = 0; i < count; ++i) {
      const auto at = image.find(address + i);
      if (at == image.end()) return false;
      static_cast<uint8_t*>(out)[i] = at->second;
    }
    return true;
  };
  assert(VerifyLunaProfile(module_base, 0x7000000, read));
  assert(!VerifyLunaProfile(module_base, 0x100, read));
  assert(!VerifyLunaProfile(UINT64_MAX - 8, 0x7000000, read));
  image[module_base + 0x6f107d8 + 20] ^= 1;
  assert(!VerifyLunaProfile(module_base, 0x7000000, read));
  std::puts("NOVA_WATCHPOINT_HOST: ALL PASS");
}
