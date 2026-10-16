// Reproduce Luna libc+0x3fe8, including a mapped unrelated host neighbor.
{
    constexpr uint64_t slot = uint64_t{1} << 30;
    constexpr uint64_t guest_a = 0x9800000000ull, guest_b = guest_a + slot;
    const size_t page = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    auto* a = static_cast<uint8_t*>(mmap(nullptr, slot + page, PROT_NONE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0));
    auto* b = static_cast<uint8_t*>(mmap(nullptr, slot, PROT_NONE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0));
    if (a == MAP_FAILED || b == MAP_FAILED) return 1;
    if (mprotect(a + slot - page, page * 2, PROT_READ | PROT_WRITE) ||
        mprotect(b, page, PROT_READ | PROT_WRITE)) return 1;
    NovaFex::MapGuestVASlot(guest_a, reinterpret_cast<uint64_t>(a));
    NovaFex::MapGuestVASlot(guest_b, reinterpret_cast<uint64_t>(b));
    for (size_t i = 0; i < page; ++i) {
        a[slot - page + i] = static_cast<uint8_t>(i * 17 + 3);
        a[slot + i] = 0xcc; // readable, but not the next guest slot
        b[i] = static_cast<uint8_t>(i * 19 + 7);
    }
    // vmovdqu xmm7,[rsi+0x70]; vmovdqu [rdi],xmm7; setz al; movzx eax,al; ret
    const uint64_t load = code.Emit({0xc5,0xfa,0x6f,0x7e,0x70,0xc5,0xfa,0x7f,0x3f,
                                     0x0f,0x94,0xc0,0x0f,0xb6,0xc0,0xc3});
    // Set ZF before the tested load; the split path must not change it.
    const uint64_t flagged = code.Emit({0x31,0xc0,0x48,0xb8,
        static_cast<uint8_t>(load),static_cast<uint8_t>(load>>8),static_cast<uint8_t>(load>>16),
        static_cast<uint8_t>(load>>24),static_cast<uint8_t>(load>>32),static_cast<uint8_t>(load>>40),
        static_cast<uint8_t>(load>>48),static_cast<uint8_t>(load>>56),0xff,0xe0});
    alignas(16) uint8_t output[16], expected[16];
    bool exact = true;
    for (unsigned remaining = 0; remaining <= 32; ++remaining) {
        const uint64_t address = guest_b - remaining;
        for (unsigned i = 0; i < 16; ++i)
            expected[i] = *reinterpret_cast<uint8_t*>(NovaFex::TranslateGuestVA(address + i));
        std::memset(output, 0xa5, sizeof(output));
        const auto flags = NovaFex::CallGuest(flagged, reinterpret_cast<uint64_t>(output), address - 0x70);
        exact &= flags == 1 && std::memcmp(output, expected, 16) == 0;
    }
    Check("128-bit cross-slot load", exact, "(all 15 splits; poisoned host neighbor; ZF)");
    const char* fault_mode = getenv("NOVA_CROSS_SLOT_FAULT_TEST");
    if (fault_mode) {
        std::memset(output, 0xa5, sizeof(output));
        g_cross_slot_output = output;
        if (std::strcmp(fault_mode, "unmapped") == 0) {
            NovaFex::UnmapGuestVASlot(guest_b);
            g_cross_slot_fault_address = guest_b;
        } else {
            if (mprotect(b, page, PROT_NONE)) return 1;
            g_cross_slot_fault_address = reinterpret_cast<uint64_t>(b);
        }
        std::printf("NOVA_CROSS_SLOT_EXPECT_RIP: 0x%llx\n", static_cast<unsigned long long>(load));
        std::fflush(stdout);
        g_cross_slot_fault = 1;
        NovaFex::CallGuest(flagged, reinterpret_cast<uint64_t>(output), guest_b - 13 - 0x70);
        return 1; // a successful read here would suppress a genuine fault
    }
    NovaFex::UnmapGuestVASlot(guest_a);
    NovaFex::UnmapGuestVASlot(guest_b);
    munmap(a, slot + page);
    munmap(b, slot);
}
