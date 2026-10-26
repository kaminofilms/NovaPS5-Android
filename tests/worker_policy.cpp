#include "native/power/WorkerPolicy.h"
#include <cassert>
#include <vector>
int main(){
 std::vector<NovaPower::CoreRank> c{{7,800},{3,400},{0,400},{4,800},{1,400},{2,400},{6,400},{5,400}};
 auto n=NovaPower::SelectWorkers(c);assert(n==6);for(size_t i=0;i<n;i++)assert(c[i].id!=4&&c[i].id!=7);
 std::vector<NovaPower::CoreRank> same{{0,100},{1,100},{2,100},{3,100}};assert(NovaPower::SelectWorkers(same)==0);
 same[0].rank=0;assert(NovaPower::SelectWorkers(same)==0);
 std::vector<NovaPower::CoreRank> small{{2,100},{7,200}};assert(NovaPower::SelectWorkers(small)==0);
 std::vector<NovaPower::CoreRank> limited{{3,400},{4,400},{7,800},{9,800}};assert(NovaPower::SelectWorkers(limited)==2);assert(limited[0].id==3&&limited[1].id==4);
}
