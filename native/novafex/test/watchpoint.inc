// Actual guest x86 stores executed by FEX on the ARM64 runner. Invoke this
// process with FEX_TSOENABLED=0 to exercise scalar StoreMem specifically.
if (getenv("NOVA_WATCHPOINT_SCALAR_TEST")) {
  alignas(16) static uint8_t object[0x80] {};
  const auto base = reinterpret_cast<uint64_t>(object);
  Check("verified watchpoint registration", NovaFex::RegisterVerifiedCheckpointObject(base));
  const auto scalar = code.Emit({0x40,0x88,0x77,0x38, 0x66,0x89,0x77,0x39,
                                0x89,0x77,0x3c, 0x48,0x89,0x77,0x40,
                                0x31,0xc0, 0x48,0x89,0x47,0x38, 0x48,0x89,0xf0,0xc3});
  const uint64_t payload = 0x1122334442c80000;
  Check("scalar source register preserved", NovaFex::CallGuest(scalar, base, payload) == payload);
  const unsigned offsets[] {0,4,8,11,17};
  const unsigned widths[] {1,2,4,8,8};
  const unsigned fields[] {0x38,0x39,0x3c,0x40,0x38};
  bool exact = true;
  unsigned found = 0;
  NovaFexWatchpoint::TraceRecord record;
  for (size_t i = 0; i < NovaFexWatchpoint::TRACE_CAPACITY; ++i) {
    if (!NovaFex::ReadWatchpointTrace(i, &record)) continue;
    if (found >= 5) { exact = false; continue; }
    const uint64_t mask = widths[found] == 8 ? UINT64_MAX : (uint64_t{1} << (widths[found] * 8)) - 1;
    exact &= record.intent.guest_rip == scalar + offsets[found] &&
             record.intent.guest_address == base + fields[found] &&
             record.intent.width == widths[found] &&
             record.intent.payload == (found == 4 ? 0 : payload & mask) &&
             record.attempted && !record.completed;
    ++found;
  }
  uint64_t value = 0;
  std::memcpy(&value, object + 0x40, 8);
  Check("scalar RIP address payload", exact && found == 5 && value == payload);
  std::memcpy(&value, object + 0x38, 8);
  Check("scalar zero source store", value == 0);
  // cmp; mov [rdi+0x40],rsi; sete al; movzx eax,al; ret.
  const auto flags = code.Emit({0x48,0x39,0xf6,0x48,0x89,0x77,0x40,0x0f,0x94,0xc0,0x0f,0xb6,0xc0,0xc3});
  Check("scalar condition flags preserved", NovaFex::CallGuest(flags, base, payload) == 1);
  while (NovaFex::ReadWatchpointTrace(5, &record)) {}
  // Live SIMD source must survive the C++ callback as well as GPR operands.
  const auto simd_live = code.Emit({0x66,0x48,0x0f,0x6e,0xc6,0x48,0x89,0x77,0x40,
                                   0x66,0x48,0x0f,0x7e,0xc0,0xc3});
  Check("scalar live SIMD preserved", NovaFex::CallGuest(simd_live, base, payload) == payload);
  for (size_t i = 0; i < NovaFexWatchpoint::TRACE_CAPACITY; ++i) NovaFex::ReadWatchpointTrace(i, &record);
  // Differential guest addressing: scaled full-width index, negative
  // displacement, sign-extended 32-bit index and zero-extended 32-bit index.
  const auto indexed = code.Emit({0x89,0x54,0xb7,0x38,0xc3});
  const auto negative = code.Emit({0x89,0x57,0xff,0xc3});
  const auto signed_index = code.Emit({0x48,0x63,0xf6,0x89,0x54,0xb7,0x38,0xc3});
  const auto unsigned_index = code.Emit({0x89,0xf6,0x89,0x54,0xb7,0x38,0xc3});
  bool addresses = true;
  for (unsigned n = 0; n < 32; ++n) {
    const uint64_t index = n * 13;
    NovaFex::CallGuest(indexed, base - index * 4, index, payload + n);
    NovaFex::CallGuest(negative, base + 0x39, 0, payload + n);
    NovaFex::CallGuest(signed_index, base + 4, UINT64_C(0xffffffff), payload + n);
    NovaFex::CallGuest(unsigned_index, base - 4, UINT64_C(0x123400000001), payload + n);
    unsigned records = 0;
    for (size_t i = 0; i < NovaFexWatchpoint::TRACE_CAPACITY; ++i) {
      if (!NovaFex::ReadWatchpointTrace(i, &record)) continue;
      addresses &= record.intent.guest_address == base + 0x38 && record.intent.width == 4 &&
                   record.intent.payload == static_cast<uint32_t>(payload + n);
      ++records;
    }
    addresses &= records == 4;
  }
  Check("scalar addressing differential", addresses);
}
