// Synthetic sparse module containing the verified profile spans, never the game.
if (getenv("NOVA_WATCHPOINT_LUNA_TEST")) {
  using namespace NovaFexWatchpoint;
  constexpr size_t module_size = 0x7000000;
  auto* module = static_cast<uint8_t*>(mmap(nullptr, module_size, PROT_READ | PROT_WRITE,
                                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
  if (module == MAP_FAILED) return 1;
  const uint64_t base = reinterpret_cast<uint64_t>(module);
  const auto place = [&](size_t offset, const auto& bytes) { std::memcpy(module + offset, bytes.data(), bytes.size()); };
  place(0xf2fc80, kLuna_constructor);
  place(0xf2f9bc, kLuna_class_registration);
  place(0x6663e2e, kLuna_class_name);
  place(0x67ba62c, kLuna_property_name);
  place(0x6f107d8, kLuna_property_layout);
  place(0xf3b5b0, kLuna_destructor);
  module[0x37cdc80] = 0xc3; // fixture-only base constructor stub
  const uint8_t unwind[] {0x48,0x83,0xc4,0x08,0x5b,0x41,0x5e,0x41,0x5f,0x5d,0xc3};
  std::memcpy(module + 0xf3b5c7, unwind, sizeof(unwind)); // fixture-only destructor tail
  NovaFex::RegisterGuestCodeRange(base, module_size);
  module[0x6663e2e] ^= 1;
  Check("Luna wrong signature rejected", !NovaFex::ConfigureLunaWatchpointProfile(base, module_size));
  module[0x6663e2e] ^= 1;
  Check("Luna valid profile accepted", NovaFex::ConfigureLunaWatchpointProfile(base, module_size));
  alignas(16) uint8_t object[0x148];
  std::memset(object, 0xa5, sizeof(object));
  const uint64_t object_address = reinterpret_cast<uint64_t>(object);
  uint64_t initializer = object_address;
  Check("Luna no speculative object", !NovaFex::IsVerifiedCheckpointObject(object_address));
  NovaFex::CallGuest(base + 0xf2fc80, reinterpret_cast<uint64_t>(&initializer));
  Check("Luna automatic typed registration", NovaFex::IsVerifiedCheckpointObject(object_address));
  bool zeroed = true;
  for (size_t i = 0x38; i < 0x48; ++i) zeroed &= object[i] == 0;
  Check("Luna original SIMD initializer", zeroed);
  uint64_t vtable = 0;
  std::memcpy(&vtable, object, 8);
  Check("Luna original vtable store", vtable == base + kLunaVTableRVA);
  const auto store = code.Emit({0x48,0x89,0x77,0x38,0xc3});
  NovaFex::CallGuest(store, object_address, 0x42c80000);
  TraceRecord record;
  const bool traced = NovaFex::ReadWatchpointTrace(0, &record);
  const bool scalar_mode = getenv("FEX_TSOENABLED") && std::strcmp(getenv("FEX_TSOENABLED"), "0") == 0;
  Check("Luna respects scalar TSO scope", scalar_mode ?
    (traced && record.intent.guest_address == object_address + 0x38 && record.intent.guest_rip == store &&
     record.intent.payload == 0x42c80000 && !record.completed) : !traced);
  NovaFex::CallGuest(base + 0xf3b5b0, object_address);
  Check("Luna automatic object retirement", !NovaFex::IsVerifiedCheckpointObject(object_address));
  NovaFex::CallGuest(store, object_address, 7);
  bool after_retirement = false;
  for (size_t i = 0; i < TRACE_CAPACITY; ++i) after_retirement |= NovaFex::ReadWatchpointTrace(i, &record);
  Check("Luna retired object excluded", !after_retirement);
  return g_failures ? 1 : 0;
}
