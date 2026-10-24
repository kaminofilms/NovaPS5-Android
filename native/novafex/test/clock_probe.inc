// Run only on the actual ARM64 FEX test runner, not a mock host-clock substitute.
#if defined(__aarch64__)
    {
        NovaFex::ClockCounters warm{},a{},b{};
        Check("translated clock warm-up",NovaFex::ReadClockCounters(&warm));
        const auto start=std::chrono::steady_clock::now();
        Check("translated clock sample A",NovaFex::ReadClockCounters(&a));
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        Check("translated clock sample B",NovaFex::ReadClockCounters(&b));
        const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        uint64_t hz=0;asm volatile("mrs %0,cntfrq_el0":"=r"(hz));
        const double tscRatio=seconds>0?double(b.rdtsc-a.rdtsc)/double(hz)/seconds:0;
        const double tscpRatio=seconds>0?double(b.rdtscp-a.rdtscp)/double(hz)/seconds:0;
        const double cpuidHz=b.eax?double(b.ecx)*b.ebx/b.eax:0;
        Check("CPUID 15 reports unscaled generic timer",hz>0&&cpuidHz==double(hz));
        Check("translated RDTSC wall-time ratio",b.rdtsc>a.rdtsc&&tscRatio>.8&&tscRatio<1.2);
        Check("translated RDTSCP wall-time ratio",b.rdtscp>a.rdtscp&&tscpRatio>.8&&tscpRatio<1.2);
    }
#endif
