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

        // LD1/ST1 two-vector form: contiguous registers, unlike interleaved LD2/ST2.
        // Include the exact failing 0x4c40a021 family, Q=0/Q=1, vector 31->0
        // wraparound, all element sizes, and register/immediate/no writeback.
        for (unsigned q=0; q<2; ++q) for (unsigned sz=0; sz<4; ++sz) {
            for (unsigned mode=0; mode<3; ++mode) {
                ucontext_t uc {};
                auto* fp = reinterpret_cast<fpsimd_context*>(uc.uc_mcontext.__reserved);
                fp->head.magic = FPSIMD_MAGIC; fp->head.size = sizeof(*fp);
                auto* a = reinterpret_cast<uint8_t*>(&fp->vregs[31]);
                auto* b = reinterpret_cast<uint8_t*>(&fp->vregs[0]);
                for (unsigned i=0; i<16; ++i) { a[i]=i+1; b[i]=0x80+i; }
                const unsigned width = q ? 16u : 8u, bytes = 2u*width;
                uint32_t instruction = 0x0c00a000u | (q<<30) | (sz<<10) | (2<<5) | 31u;
                if (mode) instruction |= (1u<<23) | ((mode==1 ? 31u : 3u)<<16);
                const uint64_t address = slot + span - 7;
                uc.uc_mcontext.regs[2]=address; uc.uc_mcontext.regs[3]=53;
                uc.uc_mcontext.pc=reinterpret_cast<uint64_t>(&instruction);
                siginfo_t info {}; info.si_addr = reinterpret_cast<void*>(address);
                bool ok = NovaFex::HandleHostFault(SIGSEGV,&info,&uc);
                for (unsigned i=0; i<bytes; ++i) {
                    const uint8_t actual = i<7 ? first[span-7+i] : second[i-7];
                    const uint8_t expected = i<width ? uint8_t(1+i) : uint8_t(0x80+i-width);
                    ok &= actual == expected;
                }
                ok &= uc.uc_mcontext.regs[2] == address+(mode==0 ? 0 : mode==1 ? bytes : 53);
                ok &= uc.uc_mcontext.pc == reinterpret_cast<uint64_t>(&instruction)+4;
                Check("ST1 contiguous/writeback/wrap",ok);
                instruction |= 1u<<22;
                uc.uc_mcontext.pc=reinterpret_cast<uint64_t>(&instruction);
                uc.uc_mcontext.regs[2]=address;
                std::memset(a,0xee,16); std::memset(b,0xee,16);
                bool loaded=NovaFex::HandleHostFault(SIGSEGV,&info,&uc);
                for (unsigned i=0; i<16; ++i) {
                    loaded &= a[i] == (i<width ? uint8_t(1+i) : 0);
                    loaded &= b[i] == (i<width ? uint8_t(0x80+i) : 0);
                }
                loaded &= uc.uc_mcontext.regs[2] == address+(mode==0 ? 0 : mode==1 ? bytes : 53);
                loaded &= uc.uc_mcontext.pc == reinterpret_cast<uint64_t>(&instruction)+4;
                Check("LD1 contiguous/load/writeback",loaded);
            }
        }
        {
            // Exact crashing instruction from the 0.9.22 phone log.
            ucontext_t uc {};
            auto* fp = reinterpret_cast<fpsimd_context*>(uc.uc_mcontext.__reserved);
            fp->head.magic=FPSIMD_MAGIC; fp->head.size=sizeof(*fp);
            uint32_t instruction=0x4c40a021u;
            const uint64_t address = slot + span - 7;
            uc.uc_mcontext.regs[1]=address;
            uc.uc_mcontext.pc=reinterpret_cast<uint64_t>(&instruction);
            for (unsigned i=0; i<32; ++i) {
                (i<7 ? first[span-7+i] : second[i-7]) = uint8_t(i+11);
            }
            siginfo_t info {}; info.si_addr=reinterpret_cast<void*>(address);
            bool ok=NovaFex::HandleHostFault(SIGSEGV,&info,&uc);
            auto* a=reinterpret_cast<uint8_t*>(&fp->vregs[1]);
            auto* b=reinterpret_cast<uint8_t*>(&fp->vregs[2]);
            for (unsigned i=0; i<16; ++i) {
                ok &= a[i]==uint8_t(i+11);
                ok &= b[i]==uint8_t(i+27);
            }
            ok &= uc.uc_mcontext.regs[1]==address;
            ok &= uc.uc_mcontext.pc==reinterpret_cast<uint64_t>(&instruction)+4;
            Check("LD1 exact 4c40a021 device fault",ok);
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

        {
            // A cross-slot LD1 must not mutate either register or PC if its
            // second page has no backing, including a register-list wrap.
            ucontext_t missing {};
            auto* fp = reinterpret_cast<fpsimd_context*>(missing.uc_mcontext.__reserved);
            fp->head.magic = FPSIMD_MAGIC; fp->head.size=sizeof(*fp);
            std::memset(fp->vregs,0x6a,sizeof(fp->vregs));
            uint32_t ld1 = 0x4c40a05fu; // LD1 {v31.16b,v0.16b},[x2]
            const uint64_t address = slot+span-16;
            missing.uc_mcontext.regs[2]=address;
            missing.uc_mcontext.pc=reinterpret_cast<uint64_t>(&ld1);
            siginfo_t info {}; info.si_addr=reinterpret_cast<void*>(address);
            bool rejected = !NovaFex::HandleHostFault(SIGSEGV,&info,&missing);
            auto* bytes=reinterpret_cast<const uint8_t*>(fp->vregs);
            for (unsigned i=0; i<sizeof(fp->vregs); ++i) rejected &= bytes[i]==0x6a;
            rejected &= missing.uc_mcontext.pc==reinterpret_cast<uint64_t>(&ld1);
            rejected &= missing.uc_mcontext.regs[2]==address;
            Check("LD1 unmapped page no vector mutation",rejected);
        }
        NovaFex::UnmapGuestVASlot(slot);
        munmap(first, span); munmap(second, span);
    }
}
