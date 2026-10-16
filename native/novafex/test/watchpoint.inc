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
}
