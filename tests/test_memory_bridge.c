/* Regression tests: an ARM39 ceiling and a Unix mapping hidden by VirtualQuery.
 * API simulation verifies reservation ownership/failure handling, not gameplay.
 */
#define NOVA_MEMORY_UNIT_TEST
#include "../runtime-compat/novamemory.c"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define GB (1024ull*1024*1024)
static unsigned allocations,failures,commits,frees;
static int commit_failure;
static const char* ceiling="0x0000007fffff0000";
static SIZE_T fake_query(LPCVOID addr,PMEMORY_BASIC_INFORMATION info,SIZE_T size) {
    if(size<sizeof(*info)) return 0;
    uint64_t start=(uint64_t)addr;
    set_interval(info,start,start>=extended_start?extended_end:128*GB,MEM_FREE);
    return sizeof(*info);
}
static PVOID fake_alloc(HANDLE p,PVOID address,SIZE_T size,ULONG type,ULONG prot,void* params,ULONG count) {
    (void)p;(void)prot;(void)params;(void)count;
    uint64_t start=(uint64_t)address;
    if(type&MEM_COMMIT) {++commits;return commit_failure?NULL:address;}
    ++allocations;
    if(start>=host_limit || size>host_limit-start ||
       (start<96*GB && start+size>80*GB)) {++failures;return NULL;}
    return address;
}
HMODULE GetModuleHandleA(const char* a){(void)a;return (void*)1;}
HMODULE LoadLibraryA(const char* a){return GetModuleHandleA(a);}
void* GetProcAddress(HMODULE m,const char* n){(void)m;return strcmp(n,"VirtualQuery")==0?(void*)fake_query:(void*)fake_alloc;}
DWORD GetEnvironmentVariableA(const char* n,char* buf,DWORD size){(void)n;size_t len=strlen(ceiling);if(len<size)memcpy(buf,ceiling,len+1);return len;}
BOOL WriteFile(HANDLE h,const void* b,DWORD n,DWORD* w,void* o){(void)h;(void)b;(void)o;*w=n;return 1;}
HANDLE GetStdHandle(DWORD n){(void)n;return (void*)1;}
HANDLE GetCurrentProcess(void){return (void*)-1;}
LONG InterlockedCompareExchange(volatile LONG* p,LONG v,LONG expected){return __sync_val_compare_and_swap(p,expected,v);}
LONG InterlockedExchange(volatile LONG* p,LONG v){return __sync_lock_test_and_set(p,v);}
void Sleep(DWORD n){(void)n;}
BOOL VirtualFree(PVOID p,SIZE_T s,DWORD t){(void)p;(void)s;(void)t;++frees;return 1;}
void SetLastError(DWORD n){(void)n;}
static void reset(void){pending=NULL;pending_size=guard_start=0;initialized=scan_finished=locked=0;host_limit=0;allocations=failures=commits=frees=0;commit_failure=0;}
int main(void){
    MEMORY_BASIC_INFORMATION info;
    /* Reproduce the device's system-band scan. Native VirtualQuery advertises
     * a free range beyond 64 GiB, but Kyty clips it before reserving. */
    reset();
    uint64_t system_start=0x180010000ull;
    assert(NovaVirtualQuery((void*)system_start,&info,sizeof(info))==sizeof(info));
    assert(info.State==MEM_FREE && (uint64_t)info.BaseAddress==system_start);
    uint64_t core_end=(uint64_t)info.BaseAddress+info.RegionSize;
    if(core_end>0x1000000000ull) core_end=0x1000000000ull;
    uint64_t core_size=core_end-system_start;
    assert(core_size==pending_size);
    unsigned system_allocations=allocations;
    assert(NovaVirtualAlloc2(GetCurrentProcess(),(void*)system_start,core_size,MEM_RESERVE|0x40000,PAGE_NOACCESS,NULL,0)==(void*)system_start);
    assert(allocations==system_allocations && !pending);
    reset();
    assert(NovaVirtualQuery((void*)(64*GB),&info,sizeof(info))==sizeof(info));
    assert(info.State==MEM_FREE && (uint64_t)info.BaseAddress==64*GB && info.RegionSize==16*GB);
    assert(allocations==3 && failures==2 && pending==(void*)(64*GB));
    unsigned before=allocations;
    assert(NovaVirtualAlloc2(GetCurrentProcess(),info.BaseAddress,info.RegionSize,MEM_RESERVE|0x40000,PAGE_NOACCESS,NULL,0)==info.BaseAddress);
    assert(allocations==before && !pending);
    assert(NovaVirtualQuery((void*)(80*GB),&info,sizeof(info)) && info.State==MEM_RESERVE && info.RegionSize==0x10000);
    /* Guard gaps keep Kyty's per-reservation ownership invariant intact. */
    uint64_t current=80*GB;
    while(current<128*GB){
        assert(NovaVirtualQuery((void*)current,&info,sizeof(info)));
        assert((uint64_t)info.BaseAddress==current && info.RegionSize>0);
        if(info.State==MEM_FREE && info.RegionSize>0x1000000){
            assert(current>=96*GB);
            assert(NovaVirtualAlloc2(GetCurrentProcess(),info.BaseAddress,info.RegionSize,MEM_RESERVE|0x40000,PAGE_NOACCESS,NULL,0)==info.BaseAddress);
        }
        current+=info.RegionSize;
    }
    assert(current==128*GB);
    assert(NovaVirtualQuery((void*)extended_start,&info,sizeof(info)) && info.State==MEM_RESERVE);
    assert(info.RegionSize==extended_end-extended_start && scan_finished);
    before=allocations;
    assert(NovaVirtualQuery((void*)(64*GB),&info,sizeof(info)) && allocations==before && !pending);
    /* Commit APIs and failed commits must remain unchanged. */
    assert(NovaVirtualAlloc2(GetCurrentProcess(),(void*)(64*GB),4096,MEM_COMMIT|MEM_RESERVE|0x4000,4,NULL,0)==(void*)(64*GB));
    commit_failure=1;
    assert(!NovaVirtualAlloc2(GetCurrentProcess(),(void*)(64*GB),4096,MEM_COMMIT|MEM_RESERVE|0x4000,4,NULL,0));
    assert(commits==2);
    reset();ceiling="invalid";
    assert(NovaVirtualQuery((void*)(64*GB),&info,sizeof(info)) && allocations==0 && !host_limit);
    puts("PASS: hidden mappings excluded, host ceiling honored, real placeholders handed off exactly once, commit failures retained, invalid configuration inactive");
}
