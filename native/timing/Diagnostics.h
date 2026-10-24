// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cmath>
namespace NovaTiming {
inline double Ratio(uint64_t before,uint64_t after,uint64_t frequency,uint64_t wallNs){
 return !frequency||!wallNs||after<before?NAN:double(after-before)*1e9/double(frequency)/double(wallNs);
}
// Constant storage. Called only on the serialized real-flip completion path.
struct FrameWindow {
 std::array<uint64_t,256> intervals{};uint64_t last=0,count=0,total=0,maximum=0;size_t stored=0;
 void Add(uint64_t now){if(last&&now>=last){auto delta=now-last;intervals[count%intervals.size()]=delta;stored=std::min(stored+1,intervals.size());++count;total+=delta;maximum=std::max(maximum,delta);}last=now;}
 uint64_t Percentile(unsigned pct)const{if(!stored)return 0;auto sorted=intervals;std::sort(sorted.begin(),sorted.begin()+stored);return sorted[(stored-1)*std::min(pct,100u)/100];}
 void Reset(){last=0;count=total=maximum=0;stored=0;}
};
}
