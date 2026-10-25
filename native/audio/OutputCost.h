// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#if defined(__linux__)
#include <unistd.h>
#include <sys/syscall.h>
#endif
namespace NovaAudio {
inline long OutputThreadId(){
#if defined(__linux__)
 return syscall(SYS_gettid);
#else
 return 0;
#endif
}
inline uint64_t ClockNs(clockid_t clock) {
    timespec t{};
    return clock_gettime(clock,&t)==0?uint64_t(t.tv_sec)*1000000000ull+uint64_t(t.tv_nsec):0;
}
struct OutputTotals {
    uint64_t startWall=0,startCpu=0,calls=0,insideCpu=0,insideWall=0;
    void Add(uint64_t wallBegin,uint64_t cpuBegin,uint64_t wallEnd,uint64_t cpuEnd) {
        if(!wallBegin||!cpuBegin||wallEnd<wallBegin||cpuEnd<cpuBegin)return;
        if(!startWall){startWall=wallBegin;startCpu=cpuBegin;}
        ++calls;insideCpu+=cpuEnd-cpuBegin;insideWall+=wallEnd-wallBegin;
    }
    uint64_t OutsideCpu(uint64_t cpuEnd)const {
        const auto total=cpuEnd>=startCpu?cpuEnd-startCpu:0;
        return total>insideCpu?total-insideCpu:0;
    }
};
class OutputScope {
    uint64_t wall=0,cpu=0;
public:
    OutputScope(){
        static const bool enabled=[] {const char* v=std::getenv("NOVA_AUDIO_PROFILE");return v&&v[0]=='1';}();
        if(enabled){wall=ClockNs(CLOCK_MONOTONIC);cpu=ClockNs(CLOCK_THREAD_CPUTIME_ID);}
    }
    ~OutputScope(){
        if(!wall||!cpu)return;
        const auto endCpu=ClockNs(CLOCK_THREAD_CPUTIME_ID),endWall=ClockNs(CLOCK_MONOTONIC);
        if(!endCpu||endCpu<cpu||endWall<wall)return;
        static thread_local OutputTotals totals;
        totals.Add(wall,cpu,endWall,endCpu);
        if(endWall>=totals.startWall && endWall-totals.startWall>=5000000000ull){
            std::fprintf(stderr,"NOVA_AUDIO_COST: tid=%ld window_ms=%.1f calls=%llu output_cpu_ms=%.3f other_thread_cpu_ms=%.3f output_wall_ms=%.3f; other includes guest mixing/decoding and other native calls\n",
                OutputThreadId(),double(endWall-totals.startWall)/1e6,(unsigned long long)totals.calls,
                double(totals.insideCpu)/1e6,double(totals.OutsideCpu(endCpu))/1e6,double(totals.insideWall)/1e6);
            totals={};
        }
    }
};
}
