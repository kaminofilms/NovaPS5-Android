// Execute the production fault handler with an architecturally shaped saved context.
{
    constexpr uint64_t slot = 0x9000000000ull, span = 1ull << 30;
    auto* first = static_cast<uint8_t*>(mmap(nullptr, span, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0));
    auto* second = static_cast<uint8_t*>(mmap(nullptr, span, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0));
    Check("SIMD reserve slots", first != MAP_FAILED && second != MAP_FAILED);
    if (first != MAP_FAILED && second != MAP_FAILED) {
        mprotect(first + span - 4096, 4096, PROT_READ | PROT_WRITE);
        mprotect(second, 4096, PROT_READ | PROT_WRITE);
        NovaFex::MapGuestVASlot(slot, reinterpret_cast<uint64_t>(first));
        NovaFex::MapGuestVASlot(slot + span, reinterpret_cast<uint64_t>(second));
        for (unsigned q = 0; q < 2; ++q) for (unsigned sz = 0; sz < 4; ++sz) {
            if (!q && sz == 3) continue;
            for (unsigned mode = 0; mode < 3; ++mode) {
                ucontext_t uc {};
                auto* fp = reinterpret_cast<fpsimd_context*>(uc.uc_mcontext.__reserved);
                fp->head.magic = FPSIMD_MAGIC; fp->head.size = sizeof(*fp);
                auto* a = reinterpret_cast<uint8_t*>(&fp->vregs[31]);
                auto* b = reinterpret_cast<uint8_t*>(&fp->vregs[0]);
                for (unsigned i = 0; i < 16; ++i) { a[i] = i + 1; b[i] = 0x80 + i; }
                uint8_t preserved[sizeof(fp->vregs)]; std::memcpy(preserved, fp->vregs, sizeof(preserved));
                const unsigned width = q ? 16 : 8, bytes = width * 2, element = 1u << sz;
                uint32_t instruction = 0x0c008000u | (q << 30) | (sz << 10) | (2 << 5) | 31;
                if (mode) instruction |= (1 << 23) | ((mode == 1 ? 31u : 3u) << 16);
                const uint64_t address = slot + span - 7;
                uc.uc_mcontext.regs[2] = address; uc.uc_mcontext.regs[3] = 47;
                uc.uc_mcontext.regs[8] = 0xabcdef;
                uc.uc_mcontext.pc = reinterpret_cast<uint64_t>(&instruction);
                siginfo_t info {}; info.si_addr = reinterpret_cast<void*>(address);
                bool ok = NovaFex::HandleHostFault(SIGSEGV, &info, &uc);
                for (unsigned i = 0; i < bytes; ++i) {
                    unsigned lane = i / (2 * element), reg = (i / element) % 2, byte = i % element;
                    uint8_t expected = (reg ? 0x80 : 1) + lane * element + byte;
                    uint8_t actual = i < 7 ? first[span - 7 + i] : second[i - 7];
                    ok &= actual == expected;
                }
                ok &= uc.uc_mcontext.regs[2] == address + (mode == 0 ? 0 : mode == 1 ? bytes : 47);
                ok &= uc.uc_mcontext.regs[8] == 0xabcdef;
                ok &= uc.uc_mcontext.pc == reinterpret_cast<uint64_t>(&instruction) + 4;
                ok &= std::memcmp(preserved, fp->vregs, sizeof(preserved)) == 0;
                Check("ST2 bytes/writeback/wrap", ok);
                instruction |= 1u << 22; // LD2, same arrangement and addressing mode.
                uc.uc_mcontext.pc = reinterpret_cast<uint64_t>(&instruction);
                uc.uc_mcontext.regs[2] = address;
                std::memset(a, 0xee, 16); std::memset(b, 0xee, 16);
                bool loaded = NovaFex::HandleHostFault(SIGSEGV, &info, &uc);
                for (unsigned i=0; i<16; ++i) {
                    loaded &= a[i] == (i < width ? i+1 : 0);
                    loaded &= b[i] == (i < width ? 0x80+i : 0);
                }
                Check("LD2 saved vector state", loaded);
            }
        }
#if defined(__aarch64__)
        // Actual fault and sigreturn: the kernel restores the emulated base writeback.
        alignas(16) uint32_t pattern[8] = {1,2,3,4,11,12,13,14};
        uint64_t target = slot + span - 16;
        asm volatile("ldp q0, q1, [%1]\n\tst2 {v0.4s, v1.4s}, [%0], #32"
                     : "+r"(target) : "r"(pattern) : "v0", "v1", "memory");
        uint32_t expected[8] = {1,11,2,12,3,13,4,14};
        Check("ST2 real signal return", target == slot + span + 16 &&
              std::memcmp(first + span - 16, expected, 16) == 0 &&
              std::memcmp(second, reinterpret_cast<uint8_t*>(expected)+16, 16) == 0);
#endif
        // Unmapped second slot: preserve destination, PC and base even with post-index.
        NovaFex::UnmapGuestVASlot(slot + span);
        std::memset(first + span - 16, 0x5a, 16);
        ucontext_t uc {};
        auto* fp = reinterpret_cast<fpsimd_context*>(uc.uc_mcontext.__reserved);
        fp->head.magic = FPSIMD_MAGIC; fp->head.size = sizeof(*fp);
        uint32_t instruction = 0x4c9f8040u;
        uc.uc_mcontext.pc = reinterpret_cast<uint64_t>(&instruction);
        uc.uc_mcontext.regs[2] = slot + span - 16;
        siginfo_t info {}; info.si_addr = reinterpret_cast<void*>(uc.uc_mcontext.regs[2]);
        bool rejected = !NovaFex::HandleHostFault(SIGSEGV, &info, &uc);
        for (unsigned i=0; i<16; ++i) rejected &= first[span-16+i] == 0x5a;
        Check("ST2 unmapped no mutation", rejected && uc.uc_mcontext.pc == reinterpret_cast<uint64_t>(&instruction) && uc.uc_mcontext.regs[2] == slot + span - 16);
        NovaFex::UnmapGuestVASlot(slot);
        munmap(first, span); munmap(second, span);
    }
}
