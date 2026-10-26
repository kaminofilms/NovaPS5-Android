// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#if defined(__linux__)
#include <sys/syscall.h>
#include <unistd.h>
#endif
#if defined(KYTY_NOVA_FEX)
#include <novafex.h>
#endif

namespace NovaAudio {
enum class PushResult { Other, Ok, NotReady, Invalid };
struct GateSample {
    uint64_t caller=0, wall=0, cpu=0, waitWall=0, waits=0, requestedUs=0;
    bool blocking=false;
    PushResult result=PushResult::Other;
};
struct GateBucket {
    uint64_t caller=0, calls=0, blocking=0, wall=0, cpu=0, waitWall=0, waits=0, requestedUs=0;
    std::array<uint64_t,4> results{};
    void Add(const GateSample& s) {
        ++calls; blocking+=s.blocking; wall+=s.wall; cpu+=s.cpu;
        waitWall+=s.waitWall; waits+=s.waits; requestedUs+=s.requestedUs;
        ++results[static_cast<unsigned>(s.result)];
    }
};
struct GateTotals {
    std::array<GateBucket,8> buckets{};
    GateBucket overflow{};
    uint64_t start=0;
    void Add(const GateSample& sample,uint64_t begin) {
        if(!start)start=begin;
        for(auto& b:buckets)if(b.calls&&b.caller==sample.caller){b.Add(sample);return;}
        for(auto& b:buckets)if(!b.calls){b.caller=sample.caller;b.Add(sample);return;}
        overflow.Add(sample);
    }
    void Report(uint64_t now,long tid) {
        if(!start||now<start||now-start<5000000000ull)return;
        auto print=[&](const GateBucket& b,bool mixed){
            if(!b.calls)return;
            std::fprintf(stderr,"NOVA_AUDIO2_GATE: tid=%ld window_ms=%.1f caller_rip=0x%llx mixed=%d calls=%llu blocking=%llu ok=%llu not_ready=%llu invalid=%llu other=%llu native_cpu_ms=%.3f native_wall_ms=%.3f grain_waits=%llu grain_wait_ms=%.3f requested_wait_ms=%.3f\n",
                tid,double(now-start)/1e6,static_cast<unsigned long long>(b.caller),mixed,
                static_cast<unsigned long long>(b.calls),static_cast<unsigned long long>(b.blocking),
                static_cast<unsigned long long>(b.results[1]),static_cast<unsigned long long>(b.results[2]),
                static_cast<unsigned long long>(b.results[3]),static_cast<unsigned long long>(b.results[0]),
                double(b.cpu)/1e6,double(b.wall)/1e6,static_cast<unsigned long long>(b.waits),
                double(b.waitWall)/1e6,double(b.requestedUs)/1e3);
        };
        for(const auto& b:buckets)print(b,false);
        print(overflow,true);
        *this={};
    }
};
inline uint64_t GateClock(clockid_t clock) {
    timespec t{};
    return clock_gettime(clock,&t)==0?uint64_t(t.tv_sec)*1000000000ull+uint64_t(t.tv_nsec):0;
}
class GuestGateCostScope {
    GateSample sample;
    uint64_t begin=0,cpuBegin=0,waitBegin=0;
    bool valid=false;
public:
    explicit GuestGateCostScope(bool blocking) {
        static const bool enabled=[]{const char* v=std::getenv("NOVA_CRI_ATTRIBUTION");return v&&v[0]=='1'&&v[1]==0;}();
        if(!enabled)return;
        begin=GateClock(CLOCK_MONOTONIC);cpuBegin=GateClock(CLOCK_THREAD_CPUTIME_ID);
        valid=begin&&cpuBegin;
        if(!valid)return;
        sample.blocking=blocking;
#if defined(KYTY_NOVA_FEX)
        NovaFex::GuestCallContext context{};
        if(NovaFex::GetGuestCallContext(&context))sample.caller=context.rip;
#endif
    }
    GuestGateCostScope(const GuestGateCostScope&)=delete;
    GuestGateCostScope& operator=(const GuestGateCostScope&)=delete;
    void BeginWait(uint32_t us) {
        if(!valid||waitBegin)return;
        waitBegin=GateClock(CLOCK_MONOTONIC);
        sample.requestedUs+=us;
    }
    void EndWait() {
        if(!valid||!waitBegin)return;
        const auto now=GateClock(CLOCK_MONOTONIC);
        if(now>=waitBegin){sample.waitWall+=now-waitBegin;++sample.waits;}
        waitBegin=0;
    }
    int Finish(int result,PushResult category) {sample.result=category;return result;}
    ~GuestGateCostScope() {
        if(!valid)return;
        EndWait();
        const auto cpuEnd=GateClock(CLOCK_THREAD_CPUTIME_ID),end=GateClock(CLOCK_MONOTONIC);
        if(!cpuEnd||!end||cpuEnd<cpuBegin||end<begin)return;
        sample.wall=end-begin;sample.cpu=cpuEnd-cpuBegin;
        static thread_local GateTotals totals;
        totals.Add(sample,begin);
        if(end-totals.start>=5000000000ull){
#if defined(__linux__)
            totals.Report(end,syscall(SYS_gettid));
#else
            totals.Report(end,0);
#endif
        }
    }
};
} // namespace NovaAudio
