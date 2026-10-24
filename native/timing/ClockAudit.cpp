// SPDX-License-Identifier: GPL-2.0-or-later
#include "common/timing/Diagnostics.h"
#include "common/timing/Runtime.h"
#include "common/novaFex.h"
#include "common/timer.h"
#include "graphics/host_gpu/renderer/sync.h"
#include "kernel/pthread.h"
#include <chrono>
#include <cstdio>
#include <thread>
#include <condition_variable>
#include <mutex>
namespace {
using Clock=std::chrono::steady_clock;
uint64_t Ns(){return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();}
struct Sample {uint64_t wall=0,tsc=0,freq=0,ptc=0,ptcFreq=0,us=0,gpu=0,host=0,hostFreq=0;NovaFex::ClockCounters guest{};};
Sample Capture(){Sample s;auto begin=Ns();if(!NovaFex::ReadClockCounters(&s.guest))return s;
 s.tsc=Libs::LibKernel::KernelReadTsc();s.freq=Libs::LibKernel::KernelGetTscFrequency();
 s.ptc=Libs::LibKernel::KernelGetProcessTimeCounter();s.ptcFreq=Libs::LibKernel::KernelGetProcessTimeCounterFrequency();
 s.us=Libs::LibKernel::KernelGetProcessTime();s.gpu=Libs::Graphics::Sync::ReadReferenceClock();
 s.host=Common::Timer::QueryPerformanceCounter();s.hostFreq=Common::Timer::QueryPerformanceFrequency();
 auto end=Ns();if(end-begin<=20000000)s.wall=begin+(end-begin)/2;return s;
}
}
void NovaAndroidClockAudit(){
#if defined(KYTY_NOVA_FEX)
 static std::jthread worker([](std::stop_token stop){
  Sample previous;unsigned samples=0;uint64_t epoch=0;
  for(unsigned tries=0;tries<36&&samples<13&&!stop.stop_requested();++tries){
   if(!NovaRuntime::background.load()){
    auto current=Capture();auto generation=NovaRuntime::epoch.load();
    if(current.wall){
     if(previous.wall&&generation==epoch){auto ns=current.wall-previous.wall;
      auto ratio=[&](uint64_t a,uint64_t b,uint64_t hz){return NovaTiming::Ratio(a,b,hz,ns);};
      double cpuidHz=current.guest.eax?double(current.guest.ecx)*current.guest.ebx/current.guest.eax:0;
      std::fprintf(stderr,"NOVA_CLOCK_RATIO: wall_ms=%.1f rdtsc=%.6f rdtscp=%.6f hle_tsc=%.6f ptc=%.6f process_us=%.6f gpu_ref_cpu_100mhz=%.6f host_counter=%.6f hle_hz=%llu cpuid15_hz=%.0f sample=%u\n",
       ns/1e6,ratio(previous.guest.rdtsc,current.guest.rdtsc,current.freq),ratio(previous.guest.rdtscp,current.guest.rdtscp,current.freq),
       ratio(previous.tsc,current.tsc,current.freq),ratio(previous.ptc,current.ptc,current.ptcFreq),ratio(previous.us,current.us,1000000),
       ratio(previous.gpu,current.gpu,100000000),ratio(previous.host,current.host,current.hostFreq),(unsigned long long)current.freq,cpuidHz,samples);
     }
     previous=current;epoch=generation;++samples;
    }
   }
   std::mutex mutex;std::condition_variable_any wake;std::unique_lock lock(mutex);
   wake.wait_for(lock,stop,std::chrono::seconds(5),[]{return false;});
  }
 });
 (void)worker;
#endif
}
