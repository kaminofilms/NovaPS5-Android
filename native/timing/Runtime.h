// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <atomic>
#include <cstdint>
namespace NovaRuntime {
// Updated from supported Android APIs; consumed at presentation boundaries.
inline std::atomic<int> workload{0};
inline std::atomic<uint64_t> gameFrames{0},presentedFrames{0},generatedFrames{0},vblanks{0};
inline std::atomic<bool> background{false};
inline std::atomic<uint64_t> epoch{0};
inline bool FramegenAllowed(){return workload.load(std::memory_order_relaxed)==0&&!background.load(std::memory_order_relaxed);}
inline int OutputCap(int user){int level=workload.load(std::memory_order_relaxed);int thermal=level>=2?30:(level==1?60:0);return !thermal?user:(!user?thermal:(user<thermal?user:thermal));}
inline void Set(int level,bool paused){
 workload.store(level<0?0:(level>2?2:level),std::memory_order_relaxed);
 if(background.exchange(paused,std::memory_order_relaxed)!=paused)epoch.fetch_add(1,std::memory_order_relaxed);
}
}
