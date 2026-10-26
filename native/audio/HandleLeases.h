#pragma once
#include <map>
#include <memory>
#include <mutex>
namespace NovaAudio {
using CloseHandle=void(*)(int);
class HandleLease {
 int handle;CloseHandle close;
public:
 HandleLease(int h,CloseHandle c):handle(h),close(c){}
 ~HandleLease(){close(handle);}
 HandleLease(const HandleLease&)=delete;HandleLease& operator=(const HandleLease&)=delete;
};
class HandleLeases {
 std::mutex mutex;
 std::map<int,std::shared_ptr<HandleLease>> live;
public:
 // Acquire under the caller's port-registry lock, before removal can retire it.
 std::shared_ptr<HandleLease> Acquire(int handle,CloseHandle close){
  if(handle<=0)return {};
  std::lock_guard lock(mutex);auto& lease=live[handle];
  if(!lease)lease=std::make_shared<HandleLease>(handle,close);
  return lease;
 }
 // Remove under this lock; destroy only AFTER unlocking. Remaining snapshots
 // delay the actual native close. Their PCM storage is independently owned.
 void Retire(int handle,CloseHandle close){
  if(handle<=0)return;
  std::shared_ptr<HandleLease> lease;
  {std::lock_guard lock(mutex);auto it=live.find(handle);if(it!=live.end()){lease=std::move(it->second);live.erase(it);}}
  if(!lease)close(handle);
 }
};
}
