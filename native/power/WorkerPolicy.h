#pragma once
#include <algorithm>
#include <cstddef>
#include <span>
namespace NovaPower {
struct CoreRank {int id;long rank;};
// The caller supplies only CPUs currently permitted for this thread. Unknown
// or uniform topology produces no policy; CPU numbering is not a performance rank.
inline size_t SelectWorkers(std::span<CoreRank> cores){
 if(cores.size()<4)return 0;
 for(auto c:cores)if(c.id<0||c.rank<=0)return 0;
 std::sort(cores.begin(),cores.end(),[](auto a,auto b){return a.rank!=b.rank?a.rank<b.rank:a.id<b.id;});
 if(cores.front().rank==cores.back().rank)return 0;
 return std::min<size_t>(6,cores.size()-2);
}
}
