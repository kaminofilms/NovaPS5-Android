#!/usr/bin/env python3
"""Run the production BatchMap body with inaccessible guest entry/count addresses."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root=Path(sys.argv[1]); repo=Path(__file__).resolve().parents[1]
s=(root/'src/kernel/memory.cpp').read_text()
start=s.index('int KYTY_SYSV_ABI KernelBatchMap2(')
end=s.index('\nint KYTY_SYSV_ABI KernelBatchMap(',start)
body=s[start:end]
assert 'NOVA_BATCH_WRITEBACK' in body
assert 'GuestMemory::Write(guest_entry, &entry->start, sizeof(entry->start));' in body
shim=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <mutex>
#include <cinttypes>
#include <vector>
#include "novaLunaTrace.h"
#define KYTY_SYSV_ABI
#define PRINT_NAME() ((void)0)
#define LOGF(...) ((void)0)
constexpr int OK=0, KERNEL_ERROR_EINVAL=-22;
std::recursive_mutex g_memory_operation_mutex;
struct KernelBatchMapEntry { void* start; uint64_t offset,length; uint8_t protection,type; int16_t reserved; int32_t operation; };
static_assert(sizeof(KernelBatchMapEntry)==32 && offsetof(KernelBatchMapEntry,start)==0 &&
              offsetof(KernelBatchMapEntry,offset)==8 && offsetof(KernelBatchMapEntry,length)==16 &&
              offsetof(KernelBatchMapEntry,protection)==24 && offsetof(KernelBatchMapEntry,type)==25 &&
              offsetof(KernelBatchMapEntry,operation)==28);
constexpr uint64_t guest_base=0x907653010ull, guest_count=0x907650f78ull;
KernelBatchMapEntry backing[5]{}; int count=-1;
struct Write { uint64_t address,size; };
std::vector<Write> writes;
namespace GuestMemory {
void* Host(uint64_t address,uint64_t n) {
    if(address>=guest_base && address-guest_base<sizeof(backing)) {
        assert(n<=sizeof(backing)-(address-guest_base));
        return reinterpret_cast<char*>(backing)+(address-guest_base);
    }
    if(address==guest_count) { assert(n==sizeof(count));return &count; }
    return reinterpret_cast<void*>(address);
}
void Read(void* dst,uint64_t src,uint64_t n) { std::memcpy(dst,Host(src,n),n); }
void Write(uint64_t dst,const void* src,uint64_t n) { writes.push_back({dst,n});std::memcpy(Host(dst,n),src,n); }
}
template<class... T> void NovaMemTrace(T...) {}
int calls=0,fail_at=-1;
uint64_t seen_len=0,seen_offset=0;int seen_prot=0,seen_flags=0;
int MapDirectMemory(void** p,uint64_t len,int prot,int flags,int64_t offset,uint64_t,const char*) {
    assert(reinterpret_cast<uint64_t>(p)<guest_base || reinterpret_cast<uint64_t>(p)>=guest_base+sizeof(backing));
    seen_len=len;seen_offset=offset;seen_prot=prot;seen_flags=flags;
    if(calls++==fail_at) { *p=reinterpret_cast<void*>(0x800000003ull);return -12; }
    if(!(flags&16))*p=reinterpret_cast<void*>(0x906b260000ull);
    return OK;
}
int MapFlexibleMemory(void** p,uint64_t,int,int,const char*) {
    if(calls++==fail_at) { *p=nullptr;return -12; }
    *p=reinterpret_cast<void*>(0x906d060000ull);return OK;
}
int UnmapMemory(uint64_t,uint64_t) { ++calls;return OK; }
int ProtectMemory(void*,uint64_t,int) { ++calls;return OK; }
void Reset() {
    std::memset(backing,0,sizeof(backing));writes.clear();count=-1;calls=0;fail_at=-1;
    for(auto& b:backing) {b.start=reinterpret_cast<void*>(0x906a2b0000ull);b.offset=0x80e90000;b.length=0x85900000;b.protection=0xf2;b.type=0xc;b.reserved=0x1234;}
}
'''
cases=r'''
int main() {
    auto* guest=reinterpret_cast<KernelBatchMapEntry*>(guest_base);
    auto* processed=reinterpret_cast<int*>(guest_count);
    Reset();auto original=backing[0];
    assert(KernelBatchMap2(guest,1,processed,16)==OK && count==1);
    assert(std::memcmp(&original,&backing[0],sizeof(original))==0);
    assert(seen_len==0x85900000 && seen_offset==0x80e90000 && seen_prot==0xf2 && seen_flags==16);
    assert(writes.size()==2 && writes[0].address==guest_base && writes[0].size==8 && writes[1].address==guest_count && writes[1].size==4);
    Reset();original=backing[0];
    assert(KernelBatchMap2(guest,1,processed,0)==OK && count==1);
    assert(backing[0].start==reinterpret_cast<void*>(0x906b260000ull));
    assert(std::memcmp(reinterpret_cast<char*>(&backing[0])+8,reinterpret_cast<char*>(&original)+8,24)==0);
    Reset();backing[0].operation=3;
    assert(KernelBatchMap2(guest,1,processed,0)==OK && count==1);
    assert(backing[0].start==reinterpret_cast<void*>(0x906d060000ull));
    Reset();fail_at=0;original=backing[0];
    assert(KernelBatchMap2(guest,1,processed,0)==-12 && count==0);
    assert(std::memcmp(&backing[0],&original,sizeof(original))==0 && writes.size()==1 && writes[0].address==guest_count);
    Reset();fail_at=1;backing[1].operation=3;auto second=backing[1];
    assert(KernelBatchMap2(guest,2,processed,0)==-12 && count==1);
    assert(backing[0].start==reinterpret_cast<void*>(0x906b260000ull));
    assert(std::memcmp(&backing[1],&second,sizeof(second))==0);
    for(int op:{1,2,4}) {
        Reset();backing[0].operation=op;original=backing[0];
        assert(KernelBatchMap2(guest,1,processed,0)==OK && count==1);
        assert(std::memcmp(&backing[0],&original,sizeof(original))==0 && writes.size()==1);
    }
    Reset();backing[0].operation=99;
    assert(KernelBatchMap2(guest,1,processed,0)==KERNEL_ERROR_EINVAL && count==0 && calls==0);
    Reset();assert(KernelBatchMap2(guest,1,nullptr,0)==OK && writes.size()==1);
    Reset();assert(KernelBatchMap2(nullptr,1,processed,0)==KERNEL_ERROR_EINVAL && writes.empty());
    Reset();assert(KernelBatchMap2(guest,-1,processed,0)==KERNEL_ERROR_EINVAL && writes.empty());
    Reset();KernelBatchMapEntry native=backing[0];int native_count=-1;
    assert(KernelBatchMap2(&native,1,&native_count,0)==OK && native_count==1);
    assert(native.start==reinterpret_cast<void*>(0x906b260000ull));
}
'''
with tempfile.TemporaryDirectory() as d:
    source=Path(d)/'batch.cpp'; binary=Path(d)/'batch'
    source.write_text(shim+body+cases)
    subprocess.run(['g++','-std=c++20','-O2','-I'+str(repo/'tools/ci'),str(source),'-o',str(binary)],check=True)
    for enabled in ['0','1']:
        subprocess.run([str(binary)],env={**os.environ,'NOVA_LUNA_TRACE':enabled},capture_output=True,check=True)
print('NOVA_BATCH_WRITEBACK_TEST: exact Luna entry, guest pointers/counts, relocation, partial failure, field preservation and native ABI PASS')
