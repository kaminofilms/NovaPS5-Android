#include "Deadline.h"
#include "Diagnostics.h"
#include "Runtime.h"
#include <cassert>
#include <cmath>
#include <iostream>
int main(){
 for(uint64_t hz:{30,60,120}){
  uint64_t period=1000000000/hz;
  for(int scenario=0;scenario<4;scenario++){
   NovaTiming::Deadline d;uint64_t now=0,last=0,epoch=0;
   for(int i=0;i<1000;i++){
    if(scenario==3&&i==100){now+=9000000000ull;++epoch;}
    auto wait=d.Wait(now,period,epoch);now+=wait;assert(d.Wait(now,period,epoch)==0);
    if(i>0&&!(scenario==3&&i==100))assert(now-last>=period-1000);
    last=now;
    uint64_t work=(scenario==1&&i==100)||(scenario==2&&i%7==0)?500000000:1000;
    now+=work;d.Finish(now);
   }
  }
 }
 // When frame work exceeds 16.67 ms, its budget is already consumed.
 for(uint64_t work:{16666667ull,20000000ull,100000000ull}){
  NovaTiming::Deadline overrun;uint64_t now=0;
  for(int i=0;i<100;i++){
   assert(overrun.Wait(now,16666667)==0);now+=work;overrun.Finish(now);
  }
 }
 NovaTiming::Deadline late;assert(late.Wait(0,10)==0);late.Finish(1);
 assert(late.Wait(13,10)==0);late.Finish(14);assert(late.Wait(14,10)==9);
 NovaTiming::Deadline d;assert(d.Wait(50,10)==0);d.Finish(50);assert(d.Wait(51,10)==9);d.Reset();assert(d.Wait(500,10)==0);
 assert(std::abs(NovaTiming::Ratio(10,19200010,19200000,1000000000)-1)<1e-9);
 assert(std::isnan(NovaTiming::Ratio(2,1,19200000,1000000000)));
 assert(std::abs(NovaTiming::Ratio(0,100000000,100000000,1000000000)-1)<1e-9);
 NovaTiming::FrameWindow w;for(uint64_t i=1;i<=301;i++)w.Add(i*16666667);assert(w.count==300&&w.stored==256&&w.Percentile(99)==16666667);w.Reset();assert(w.count==0&&w.stored==0);
 NovaRuntime::Set(0,false);assert(NovaRuntime::OutputCap(120)==120&&NovaRuntime::FramegenAllowed());
 NovaRuntime::Set(1,false);assert(NovaRuntime::OutputCap(120)==60&&!NovaRuntime::FramegenAllowed());
 NovaRuntime::Set(2,false);assert(NovaRuntime::OutputCap(0)==30&&NovaRuntime::OutputCap(30)==30);auto e=NovaRuntime::epoch.load();NovaRuntime::Set(0,true);assert(NovaRuntime::epoch.load()==e+1&&!NovaRuntime::FramegenAllowed());NovaRuntime::Set(0,false);assert(NovaRuntime::FramegenAllowed());
 std::cout<<"PASS 30/60/120 Hz, long/repeated stalls, pause/resume, ratios, frame windows, workload caps\n";
}

