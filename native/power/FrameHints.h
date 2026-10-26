#pragma once
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <mutex>
#include <string_view>
#if defined(__ANDROID__)
#include <android/performance_hint.h>
#include <unistd.h>
#include "common/timing/Runtime.h"
namespace NovaPower {
struct Registry {std::mutex mutex;std::array<int32_t,8> tids{};std::atomic<uint64_t> generation{1};};
inline Registry& Threads(){static Registry r;return r;}
inline bool Enabled(){static const bool on=[] {const char* p=std::getenv("NOVA_ADPF");return p&&p[0]=='1';}();return on;}
class CriticalGuest {
 int32_t tid=0;
public:
 explicit CriticalGuest(std::string_view name){if(!Enabled()||(name!="SDLThread"&&!name.starts_with("UnityGfxDeviceW")))return;auto& r=Threads();std::lock_guard lock(r.mutex);for(auto& slot:r.tids)if(!slot){tid=gettid();slot=tid;r.generation.fetch_add(1,std::memory_order_release);break;}}
 ~CriticalGuest(){if(!tid)return;auto& r=Threads();std::lock_guard lock(r.mutex);for(auto& slot:r.tids)if(slot==tid){slot=0;r.generation.fetch_add(1,std::memory_order_release);break;}}
 CriticalGuest(const CriticalGuest&)=delete;CriticalGuest& operator=(const CriticalGuest&)=delete;
};
class FrameHints {
 using Clock=std::chrono::steady_clock;
 APerformanceHintSession* session=nullptr;uint64_t generation=0;int64_t target=0;
 Clock::time_point start{},retryAfter{};
 void close(){if(session)APerformanceHint_closeSession(session);session=nullptr;generation=0;target=0;}
 void ensure(Clock::time_point now,int64_t budget){auto& r=Threads();auto current=r.generation.load(std::memory_order_acquire);if(session&&current!=generation)close();
  if(!session&&now>=retryAfter){retryAfter=now+std::chrono::seconds(1);auto* manager=APerformanceHint_getManager();if(!manager)return;
   std::array<int32_t,9> ids{};size_t n=1;ids[0]=gettid();{std::lock_guard lock(r.mutex);current=r.generation.load(std::memory_order_relaxed);for(auto id:r.tids)if(id&&id!=ids[0])ids[n++]=id;}
   session=APerformanceHint_createSession(manager,ids.data(),n,budget);if(session){generation=current;target=budget;}}
  if(session&&target!=budget){if(APerformanceHint_updateTargetWorkDuration(session,budget)==0)target=budget;else close();}}
public:
 FrameHints()=default;~FrameHints(){close();}FrameHints(const FrameHints&)=delete;FrameHints& operator=(const FrameHints&)=delete;
 void Begin(){if(!Enabled())return;if(NovaRuntime::background.load(std::memory_order_relaxed)){Cancel();return;}if(start==Clock::time_point{})start=Clock::now();}
 void End(){if(!Enabled())return;if(NovaRuntime::background.load(std::memory_order_relaxed)){Cancel();return;}auto now=Clock::now();if(start==Clock::time_point{})return;auto duration=std::chrono::duration_cast<std::chrono::nanoseconds>(now-start).count();start={};if(duration<=0||duration>1000000000LL)return;int desired=60;if(const char* value=std::getenv("NOVA_FPS_CAP")){char* end=nullptr;long parsed=std::strtol(value,&end,10);if(end!=value&&*end==0&&parsed>0&&parsed<=240)desired=int(parsed);}int cap=NovaRuntime::OutputCap(desired);int64_t budget=1000000000LL/(cap>0?cap:60);ensure(now,budget);if(session&&APerformanceHint_reportActualWorkDuration(session,duration)!=0)close();}
 void Cancel(){start={};close();}
};
inline FrameHints& Current(){static thread_local FrameHints hints;return hints;}
}
#else
namespace NovaPower {struct CriticalGuest {explicit CriticalGuest(std::string_view){}};struct FrameHints {void Begin(){}void End(){}void Cancel(){}};inline FrameHints& Current(){static thread_local FrameHints h;return h;}}
#endif
