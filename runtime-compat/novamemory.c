/* SPDX-License-Identifier: GPL-2.0-only
 * A narrow Wine bridge for Kyty df5b9b9's two imported memory functions.
 * Reserve placeholders before advertising a free interval to Kyty. Wine's
 * VirtualQuery does not expose every Unix/FEX mapping, and may advertise
 * addresses beyond the ARM64 host's VA ceiling. Never replace live mappings.
 * All commits, protections, mappings and frees retain the upstream API path.
 */
#ifdef NOVA_MEMORY_UNIT_TEST
#include "win_api_test.h"
#else
#include <windows.h>
#endif
#include <stdint.h>

typedef PVOID (WINAPI *Alloc2)(HANDLE, PVOID, SIZE_T, ULONG, ULONG, void*, ULONG);
static Alloc2 real_alloc;
static SIZE_T (WINAPI *real_query)(LPCVOID, PMEMORY_BASIC_INFORMATION, SIZE_T);
static uint64_t host_limit;
static PVOID pending;
static SIZE_T pending_size;
static uint64_t guard_start;
static volatile LONG locked;
static int initialized;
static int scan_finished;
static const uint64_t system_end = 0x1000000000ull;
static const uint64_t ordinary_end = 0xfc00000000ull;
static const uint64_t extended_start = 0x080000000000ull;
static const uint64_t extended_end = 0x088000000000ull;

BOOL WINAPI DllMainStartup(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)instance; (void)reason; (void)reserved;
    return TRUE;
}

static void log_line(const char* text) {
    DWORD size=0, written;
    while(text[size]) ++size;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text, size, &written, NULL);
}
static void initialize(void) {
    if (initialized) return;
    HMODULE kernel = GetModuleHandleA("kernelbase.dll");
    if (!kernel) kernel = GetModuleHandleA("kernel32.dll");
    real_query = (void*)GetProcAddress(kernel, "VirtualQuery");
    real_alloc = (void*)GetProcAddress(kernel, "VirtualAlloc2");
    if (!real_alloc) {
        HMODULE api = LoadLibraryA("api-ms-win-core-memory-l1-1-6.dll");
        if (api) real_alloc = (void*)GetProcAddress(api, "VirtualAlloc2");
    }
    char value[32];
    DWORD n = GetEnvironmentVariableA("NOVA_HOST_VA_LIMIT", value, sizeof(value));
    if (n > 2 && n < sizeof(value) && value[0]=='0' && value[1]=='x') {
        uint64_t parsed = 0;
        int valid = 1;
        for (DWORD i=2; i<n; ++i) {
            unsigned char c=value[i]; unsigned digit;
            if(c>='0'&&c<='9') digit=c-'0';
            else if(c>='a'&&c<='f') digit=c-'a'+10;
            else {valid=0; break;}
            if(parsed > UINT64_MAX/16) {valid=0; break;}
            parsed=parsed*16+digit;
        }
        if(valid && parsed >= 0x200000000ull && parsed <= 0x7fffffff0000ull && !(parsed&0xffff))
            host_limit=parsed;
    }
    initialized=1;
    if (host_limit && real_query && real_alloc)
        log_line("NOVA_MEMORY: host VA ceiling applied; probing real Wine placeholders\n");
}
static void lock(void) { while(InterlockedCompareExchange(&locked,1,0)) Sleep(0); }
static void unlock(void) { InterlockedExchange(&locked,0); }
static int guest_band(uint64_t address) {
    return (address>=0x40000 && address<ordinary_end) ||
           (address>=extended_start && address<extended_end);
}
static void set_interval(PMEMORY_BASIC_INFORMATION info, uint64_t base, uint64_t end, DWORD state) {
    info->BaseAddress=(void*)base;
    info->AllocationBase=state==MEM_FREE ? NULL : (void*)base;
    info->AllocationProtect=state==MEM_FREE ? 0 : PAGE_NOACCESS;
    info->RegionSize=end-base;
    info->State=state; info->Protect=PAGE_NOACCESS; info->Type=0;
}
__declspec(dllexport) SIZE_T WINAPI NovaVirtualQuery(LPCVOID address, PMEMORY_BASIC_INFORMATION info, SIZE_T size) {
    lock(); initialize();
    if (!real_query) {unlock(); SetLastError(ERROR_PROC_NOT_FOUND); return 0;}
    SIZE_T result=real_query(address,info,size);
    uint64_t start=(uint64_t)address;
    if (!result || size<sizeof(*info) || !host_limit || !real_alloc || scan_finished || !guest_band(start)) {unlock(); return result;}
    /* Core's initial scan consumes each cached interval synchronously. A later
     * query cannot inherit an unconsumed reservation. */
    if(pending) {VirtualFree(pending,0,MEM_RELEASE); pending=NULL; pending_size=0;}
    /* Kyty scans its system and user bands separately and clips each query to
     * that band's end before calling VirtualAlloc2. The cached placeholder must
     * already have those same bounds, or its full reservation will conflict
     * with Kyty's shorter request (observed at 0x180010000 on the device). */
    uint64_t band_end=start<system_end ? system_end :
                      (start<ordinary_end ? ordinary_end : extended_end);
    if (start>=host_limit) {
        set_interval(info,start,band_end,MEM_RESERVE);
        log_line("NOVA_MEMORY: excluded guest range above host VA ceiling\n");
        if(start>=extended_start) scan_finished=1;
        unlock(); return result;
    }
    /* Kyty's Owns() expects an allocation inside one m_owned interval. Keep
     * adaptively split reservations separate, including its coalescing free
     * list. This 64 KiB unavailable gap never replaces or commits host memory. */
    if(guard_start && start==guard_start) {
        uint64_t end=start+0x10000;
        if(end>band_end) end=band_end;
        set_interval(info,start,end,MEM_RESERVE);
        guard_start=0;
        unlock(); return result;
    }
    if (info->State!=MEM_FREE) {unlock(); return result;}
    uint64_t end=(uint64_t)info->BaseAddress+info->RegionSize;
    if(end>band_end) end=band_end;
    if(end>host_limit) end=host_limit;
    start=(start+0xffff)&~0xffffull; end&=~0xffffull;
    if(end<=start) {unlock(); return result;}
    uint64_t length=end-start;
    if(length<=0x1000000) {set_interval(info,start,end,MEM_FREE); unlock(); return result;}
    uint64_t candidate=length;
    while(candidate>0x1000000) {
        void* ptr=real_alloc(GetCurrentProcess(),(void*)start,candidate,
                            MEM_RESERVE|0x40000 /* placeholder */,PAGE_NOACCESS,NULL,0);
        if(ptr==(void*)start) {
            pending=ptr; pending_size=candidate;
            set_interval(info,start,start+candidate,MEM_FREE);
            if(candidate!=length) log_line("NOVA_MEMORY: reserved a smaller available guest interval\n");
            unlock(); return result;
        }
        if(ptr) VirtualFree(ptr,0,MEM_RELEASE);
        candidate=(candidate/2)&~0xffffull;
    }
    /* This prefix really cannot be reserved. Leave it out of Kyty's allocator;
     * do not suppress a failed allocation or invent usable memory. */
    uint64_t blocked=0x1000000;
    if(blocked>length) blocked=length;
    set_interval(info,start,start+blocked,MEM_RESERVE);
    unlock(); return result;
}
__declspec(dllexport) PVOID WINAPI NovaVirtualAlloc2(HANDLE process,PVOID address,SIZE_T size,ULONG type,ULONG protect,void* parameters,ULONG count) {
    lock(); initialize();
    if(pending==address && pending && pending_size==size && process==GetCurrentProcess() &&
       type==(MEM_RESERVE|0x40000) && protect==PAGE_NOACCESS && !parameters && !count) {
        PVOID ret=pending; guard_start=(uint64_t)pending+pending_size;
        pending=NULL; pending_size=0; unlock(); return ret;
    }
    Alloc2 fn=real_alloc; unlock();
    if(!fn) {SetLastError(ERROR_PROC_NOT_FOUND); return NULL;}
    return fn(process,address,size,type,protect,parameters,count);
}
