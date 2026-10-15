#!/usr/bin/env python3
"""Verify trace-only source invariance, fail-closed anchors and mapping return behavior."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

repo=Path(__file__).resolve().parents[1]
root=Path(sys.argv[1])
def untrace(text):
    return re.sub(r'/\* NOVA_LUNA_BEGIN \*/.*?/\* NOVA_LUNA_END \*/', '', text, flags=re.S)
def normalized(text):
    return ''.join(text.split())

with tempfile.TemporaryDirectory() as d:
    stage=Path(d)/'tree'
    paths=['src/kernel/memory.cpp','src/libs/libAmpr.cpp']
    originals={p:untrace((root/p).read_text()) for p in paths}
    for p,s in originals.items():
        (stage/p).parent.mkdir(parents=True,exist_ok=True)
        (stage/p).write_text(s)
    (stage/'src/common').mkdir(parents=True)
    command=[sys.executable,str(repo/'tools/ci/patch-0934-luna-correlation.py'),str(stage)]
    subprocess.run(command,check=True)
    for p,s in originals.items():
        assert normalized(untrace((stage/p).read_text()))==normalized(s),p
    before={p:(stage/p).read_bytes() for p in paths}
    assert subprocess.run(command,capture_output=True).returncode!=0
    assert all((stage/p).read_bytes()==s for p,s in before.items())
    memory=(stage/paths[0]).read_text()
    start=memory.index('int KYTY_SYSV_ABI KernelBatchMap2(')
    end=memory.index('\nint KYTY_SYSV_ABI KernelBatchMap(',start)
    body=memory[start:end]
    shim=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <cinttypes>
#include "novaLunaTrace.h"
#define KYTY_SYSV_ABI
#define PRINT_NAME() ((void)0)
#define LOGF(...) ((void)0)
constexpr int OK=0, KERNEL_ERROR_EINVAL=-22;
std::recursive_mutex g_memory_operation_mutex;
struct KernelBatchMapEntry {
    void* start; uint64_t offset,length; uint8_t protection,type; uint16_t reserved; int operation;
};
static_assert(sizeof(KernelBatchMapEntry)==32);
namespace GuestMemory { inline void Read(void* dst,uint64_t src,uint64_t n) { std::memcpy(dst,reinterpret_cast<void*>(src),n); } }
template<class... T> void NovaMemTrace(T...) {}
int calls=0, fail_at=-1;
int Status() { return calls++==fail_at ? -12 : OK; }
int MapDirectMemory(void** p,uint64_t,int,int,int64_t,uint64_t,const char*) {
    int r=Status(); if(!r)*p=reinterpret_cast<void*>(0x800004000ull); return r;
}
int MapFlexibleMemory(void** p,uint64_t,int,int,const char*) {
    int r=Status(); if(!r)*p=reinterpret_cast<void*>(0x9000000000ull); return r;
}
int UnmapMemory(uint64_t,uint64_t) { return Status(); }
int ProtectMemory(void*,uint64_t,int) { return Status(); }
'''
    cases=r'''
int main() {
    KernelBatchMapEntry entries[5]{};
    for(int i=0;i<5;i++) { entries[i].length=0x4000; entries[i].operation=i; }
    int processed=-1;
    assert(KernelBatchMap2(entries,5,&processed,16)==OK && processed==5 && calls==5);
    assert(reinterpret_cast<uint64_t>(entries[0].start)==0x800004000ull);
    assert(reinterpret_cast<uint64_t>(entries[3].start)==0x9000000000ull);
    calls=0;fail_at=1;processed=-1;
    assert(KernelBatchMap2(entries,5,&processed,16)==-12 && processed==1 && calls==2);
    calls=0;fail_at=-1;entries[0].operation=99;processed=-1;
    assert(KernelBatchMap2(entries,5,&processed,16)==KERNEL_ERROR_EINVAL && processed==0 && calls==0);
    assert(KernelBatchMap2(nullptr,1,&processed,16)==KERNEL_ERROR_EINVAL);
    assert(KernelBatchMap2(entries,-1,&processed,16)==KERNEL_ERROR_EINVAL);
    for(unsigned i=0;i<1000;i++)NovaLunaTrace::Print(NovaLunaTrace::Kind::Event,"test");
}
'''
    source=Path(d)/'batch.cpp';binary=Path(d)/'batch'
    source.write_text(shim+body+cases)
    subprocess.run(['g++','-std=c++20','-O2','-I'+str(stage/'src/common'),str(source),'-o',str(binary)],check=True)
    for enabled in ['0','1']:
        result=subprocess.run([str(binary)],env={**os.environ,'NOVA_LUNA_TRACE':enabled},capture_output=True,check=True,text=True)
        lines=result.stderr.splitlines()
        assert (len(lines)>0)==(enabled=='1')
        if enabled=='1':
            event=[line for line in lines if 'kind=2 ' in line]
            assert len(event)==129 and 'suppressed' in event[-1]
    # Drift in the second file must not leave the first file partially patched.
    for p,s in originals.items():(stage/p).write_text(s)
    (stage/paths[1]).write_text(originals[paths[1]].replace('#include "common/abi.h"','// changed anchor'))
    before={p:(stage/p).read_bytes() for p in paths}
    assert subprocess.run(command,capture_output=True).returncode!=0
    assert all((stage/p).read_bytes()==s for p,s in before.items())
print('NOVA_LUNA_TRACE_TEST: source invariance, mapping/error semantics, opt-out, log bounds and atomic anchor failure PASS')
