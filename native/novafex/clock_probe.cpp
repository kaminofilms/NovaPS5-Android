// SPDX-License-Identifier: GPL-2.0-or-later
#include "novafex.h"
#include <cstring>
#include <mutex>
#include <sys/mman.h>
namespace NovaFex {
bool ReadClockCounters(ClockCounters* out) {
    if(!out||!IsInitialized())return false;
    // Run on a dedicated host diagnostic worker, never nested inside a guest call.
    static const uint8_t code[]={0x53,0xf,0xae,0xe8,0xf,0x31,0x48,0xc1,0xe2,0x20,0x48,0x9,0xd0,0x48,0x89,0x7,0xf,0x1,0xf9,0x48,0xc1,0xe2,0x20,0x48,0x9,0xd0,0x48,0x89,0x47,0x8,0xb8,0x15,0x0,0x0,0x0,0x31,0xc9,0xf,0xa2,0x89,0x47,0x10,0x89,0x5f,0x14,0x89,0x4f,0x18,0x89,0x57,0x1c,0x5b,0xc3};
    static std::once_flag once;
    static uint64_t entry=0;
    std::call_once(once,[]{
        void* mem=mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        if(mem==MAP_FAILED)return;
        std::memcpy(mem,code,sizeof(code));
        RegisterGuestCodeRange(reinterpret_cast<uint64_t>(mem),4096);
        entry=reinterpret_cast<uint64_t>(mem);
    });
    if(!entry)return false;
    *out={};CallGuest(entry,reinterpret_cast<uint64_t>(out));return true;
}
}
