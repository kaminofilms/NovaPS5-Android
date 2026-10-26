from pathlib import Path
import subprocess,tempfile,os
repo=Path(__file__).resolve().parents[1]
service='''#pragma once
#include <cstdint>
#include <cstddef>
struct APerformanceHintManager{};struct APerformanceHintSession{};
inline APerformanceHintManager manager;inline APerformanceHintSession session;
inline int created=0,closed=0,reports=0,updated=0;inline size_t threads=0;inline int64_t target=0;
inline APerformanceHintManager* APerformanceHint_getManager(){return &manager;}
inline APerformanceHintSession* APerformanceHint_createSession(APerformanceHintManager*,const int32_t*,size_t n,int64_t t){++created;threads=n;target=t;return &session;}
inline void APerformanceHint_closeSession(APerformanceHintSession*){++closed;}
inline int APerformanceHint_updateTargetWorkDuration(APerformanceHintSession*,int64_t t){++updated;target=t;return 0;}
inline int APerformanceHint_reportActualWorkDuration(APerformanceHintSession*,int64_t t){if(t<=0)return 1;++reports;return 0;}
'''
runtime='''#pragma once
#include <atomic>
namespace NovaRuntime {inline std::atomic<bool> background{false};inline int cap=60;inline int OutputCap(int){return cap;}}
'''
source='''#include "native/power/FrameHints.h"
#include <cassert>
#include <thread>
#include <latch>
int main(){setenv("NOVA_ADPF","1",1);
 std::thread mainGuest([]{
  NovaPower::RegisterMainGuest();
  {auto& r=NovaPower::Threads();std::lock_guard lock(r.mutex);unsigned n=0;for(auto id:r.tids)if(id){++n;assert(id==gettid());}assert(n==1);}
  pthread_exit(nullptr); // TLS registration must clean up even without stack return.
 });mainGuest.join();for(auto id:NovaPower::Threads().tids)assert(!id);
 {NovaPower::CriticalGuest audio("CRI Audio Output");for(auto id:NovaPower::Threads().tids)assert(!id);}
 std::latch ready(1),finish(1);std::thread guest([&]{NovaPower::CriticalGuest g("UnityGfxDeviceW");ready.count_down();finish.wait();});ready.wait();
 {NovaPower::FrameHints h;h.Begin();std::this_thread::sleep_for(std::chrono::milliseconds(1));h.End();assert(created==1&&threads==2&&reports==1&&target==16666666);
 NovaRuntime::cap=30;h.Begin();std::this_thread::sleep_for(std::chrono::milliseconds(1));h.End();assert(updated==1&&target==33333333);
 NovaRuntime::background=true;h.Begin();h.End();assert(closed==1&&reports==2);h.Cancel();assert(closed==1);}
 finish.count_down();guest.join();for(auto id:NovaPower::Threads().tids)assert(!id);
}
'''
with tempfile.TemporaryDirectory() as d:
 d=Path(d);(d/'android').mkdir();(d/'common/timing').mkdir(parents=True)
 (d/'android/performance_hint.h').write_text(service);(d/'common/timing/Runtime.h').write_text(runtime);(d/'test.cpp').write_text(source)
 subprocess.run(['c++','-std=c++20','-pthread','-D__ANDROID__','-fsanitize=address,undefined','-I'+str(d),'-I'+str(repo),str(d/'test.cpp'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual hint implementation with simulated Android service: TIDs, initial guest TLS/pthread_exit cleanup, CRI exclusion, budget update, pause, teardown')
