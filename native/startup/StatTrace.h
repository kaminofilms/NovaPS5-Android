// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <functional>
#include <cstdint>
namespace NovaStartup {
class StatTrace {
 struct Entry{bool active;uint64_t begin,call,thread;int stage;char guest[256],host[256];};
 static inline std::array<Entry,32> entries{};
 static inline std::mutex mutex;
 size_t slot=entries.size();
 static uint64_t Now(){return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
public:
 StatTrace(bool enabled,uint64_t call,const char* guest){
  if(!enabled)return;
  std::lock_guard lock(mutex);
  for(size_t i=0;i<entries.size();i++)if(!entries[i].active){slot=i;auto&e=entries[i];e={};e.active=true;e.call=call;e.begin=Now();e.thread=std::hash<std::thread::id>{}(std::this_thread::get_id());e.stage=1;std::snprintf(e.guest,sizeof(e.guest),"%s",guest);break;}
 }
 ~StatTrace(){if(slot<entries.size()){std::lock_guard lock(mutex);entries[slot].active=false;}}
 StatTrace(const StatTrace&)=delete;StatTrace& operator=(const StatTrace&)=delete;
 void Native(const char* host){if(slot==entries.size())return;std::lock_guard lock(mutex);auto&e=entries[slot];e.stage=2;std::snprintf(e.host,sizeof(e.host),"%s",host);}
 static void Report(FILE* output=stderr,uint64_t minimumUs=50000){
  std::unique_lock lock(mutex,std::try_to_lock);if(!lock.owns_lock()){std::fprintf(output,"NOVA_STAT_PENDING: snapshot busy\n");return;}
  const auto now=Now();for(const auto&e:entries)if(e.active&&now-e.begin>=minimumUs)
   std::fprintf(output,"NOVA_STAT_PENDING: call=%llu thread=%llx us=%llu stage=%s guest=%s host=%s\n",(unsigned long long)e.call,(unsigned long long)e.thread,(unsigned long long)(now-e.begin),e.stage==1?"resolve":"metadata",e.guest,e.host);
 }
};
}
