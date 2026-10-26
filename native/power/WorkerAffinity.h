#pragma once
#include "WorkerPolicy.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#if defined(__ANDROID__)
#include <sched.h>
namespace NovaPower {
inline long CpuProperty(int cpu,const char* property){char path[192];std::snprintf(path,sizeof(path),"/sys/devices/system/cpu/cpu%d/%s",cpu,property);FILE* f=std::fopen(path,"r");if(!f)return 0;long value=0;int result=std::fscanf(f,"%ld",&value);std::fclose(f);return result==1&&value>0?value:0;}
inline void ApplyWorkerAffinity(std::string_view name){
 static const bool enabled=[] {const char* p=std::getenv("NOVA_WORKER_AFFINITY");return p&&p[0]=='1';}();
 if(!enabled||(!name.starts_with("Job.Worker")&&!name.starts_with("Background Job.")))return;
 cpu_set_t allowed;if(sched_getaffinity(0,sizeof(allowed),&allowed)!=0)return;
 std::array<CoreRank,CPU_SETSIZE> cores{};size_t count=0;
 for(int i=0;i<CPU_SETSIZE;++i)if(CPU_ISSET(i,&allowed))cores[count++]={i,0};
 auto rank=[&](const char* p){for(size_t i=0;i<count;++i)cores[i].rank=CpuProperty(cores[i].id,p);return SelectWorkers(std::span(cores).first(count));};
 size_t workers=rank("cpu_capacity");if(!workers)workers=rank("cpufreq/cpuinfo_max_freq");if(!workers)return;
 cpu_set_t selected;CPU_ZERO(&selected);for(size_t i=0;i<workers;++i)CPU_SET(cores[i].id,&selected);
 int result=sched_setaffinity(0,sizeof(selected),&selected);
 std::fprintf(stderr,"NOVA_WORKER_AFFINITY: worker=%.*s allowed=%zu selected=%zu result=%d\n",int(name.size()),name.data(),count,workers,result);
}
}
#else
namespace NovaPower {inline void ApplyWorkerAffinity(std::string_view){}}
#endif
