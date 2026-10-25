// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
#include <limits>
namespace NovaTiming {
// One event per wake. Missed deadlines are discarded, never replayed.
// Units belong to the caller's monotonic clock; no guest clock is modified.
class Deadline {
 uint64_t due_=0,period_=0,epoch_=0,start_=0;bool initialized_=false;
 static uint64_t add(uint64_t a,uint64_t b){return b>UINT64_MAX-a?UINT64_MAX:a+b;}
public:
 uint64_t Wait(uint64_t now,uint64_t period,uint64_t epoch=0){
  if(!period)period=1;
  if(!initialized_||period!=period_||epoch!=epoch_){due_=now;period_=period;epoch_=epoch;initialized_=true;}
  if(due_>now)return due_-now;
  start_=now;
  return 0;
 }
 // Budget from the actual start, not from completion. An overrun has already
 // consumed its interval: permit the next iteration without an extra full sleep.
 // Rebase at every real start so missed ticks never become a catch-up burst.
 void Finish(uint64_t now){auto next=add(start_,period_);due_=now>next?now:next;}
 void Reset(){initialized_=false;}
};
}

