#!/usr/bin/env python3
"""Host regression tests against the applied Kyty source, without building an APK.

Usage: python3 tests/test_native_startup.py /path/to/patched/kyty
The x86 host executes the actual relocated guest wrapper to check foreign-pointer
dispatch survives slot redirection. Application-heap callbacks use a mock FEX bridge
to check that native ARM64 paths dispatch through it, including signed error returns.
This does not verify Android integration or title boot.
"""
import pathlib
import platform
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1])
if platform.machine() not in ("x86_64", "AMD64"):
    raise SystemExit("These executable x86 relocation tests require an x86_64 host")

def function(source, marker):
    begin = source.index(marker)
    brace = source.index("{", begin)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[begin:end]

heap = (root / "src/libs/novaHeap.cpp").read_text()
linker = (root / "src/loader/runtimeLinker.cpp").read_text()
helpers = "\n".join(function(heap, marker) for marker in (
    "int ModRmLen(", "int RelocateInsn(", "uint64_t BuildOriginalTrampoline(",
    "uint64_t AllocatorDispatchSlot(", "bool RewriteDispatchSlot("))
callbacks = "\n".join(function(linker, marker) for marker in (
    "void* RuntimeLinker::ApplicationHeapMemalign(", "void* RuntimeLinker::ApplicationHeapMalloc("))
program = r'''
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
#include "kernel/novaMemoryCompatibility.h"
#define KYTY_NOVA_FEX 1
namespace Common { struct LockGuard { explicit LockGuard(int&) {} }; }
namespace NovaFex {
uint64_t last_target, a0, a1, a2, result;
uint64_t CallGuest(uint64_t target, uint64_t x, uint64_t y=0, uint64_t z=0) {
    last_target=target; a0=x; a1=y; a2=z;
    if (target==0x22222 && result==0) *reinterpret_cast<void**>(x)=reinterpret_cast<void*>(0xabcdef00);
    return result;
}
}
class RuntimeLinker {
public:
    int m_mutex=0;
    using Alloc=void*(*)(uint64_t);
    using Align=int(*)(void**,uint64_t,uint64_t);
    Alloc m_application_heap_malloc=nullptr;
    Align m_application_heap_posix_memalign=nullptr;
    void* ApplicationHeapMalloc(uint64_t);
    void* ApplicationHeapMemalign(uint64_t,uint64_t);
};
''' + helpers + "\n" + callbacks + r'''
extern "C" uint64_t original(uint64_t n) { return n+3; }
extern "C" uint64_t replacement(uint64_t n) { return n+99; }
int main() {
    using Libs::LibKernel::Memory::NovaValidDirectFixedAddress;
    assert(!NovaValidDirectFixedAddress(0x400004000,0x200000,0x200000,false));
    assert(NovaValidDirectFixedAddress(0x400004000,0x200000,0x200000,true));
    assert(NovaValidDirectFixedAddress(0x400200000,0x200000,0x200000,false));
    assert(!NovaValidDirectFixedAddress(0,0x4000,0x4000,true));
    assert(!NovaValidDirectFixedAddress(0x400004001,0x4000,0x4000,true));
    assert(!NovaValidDirectFixedAddress(0xffffffffffffc000,0x8000,0,true));
    assert(!NovaValidDirectFixedAddress(0x4000,0,0,true));
    auto* page=static_cast<uint8_t*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
    assert(page!=MAP_FAILED);
    uint8_t wrapper[]={0x55,0x48,0x89,0xe5,0xff,0x15,0,0,0,0,0x5d,0xc3,0x90,0x90};
    int32_t rel=512-10;
    std::memcpy(wrapper+6,&rel,4);
    std::memcpy(page,wrapper,sizeof(wrapper));
    uint64_t before=reinterpret_cast<uint64_t>(&original);
    std::memcpy(page+512,&before,8);
    uint64_t entry=reinterpret_cast<uint64_t>(page);
    assert(AllocatorDispatchSlot(entry)==entry+512);
    auto* slot=page+512;
    uint64_t trampoline=BuildOriginalTrampoline(entry,14);
    assert(trampoline!=0);
    assert(mprotect(reinterpret_cast<void*>(trampoline&~uint64_t(4095)),4096,PROT_READ|PROT_EXEC)==0);
    using Fn=uint64_t(*)(uint64_t);
    assert(reinterpret_cast<Fn>(entry)(7)==10);
    assert(RewriteDispatchSlot(reinterpret_cast<uint64_t>(slot),reinterpret_cast<uint64_t>(&replacement)));
    assert(reinterpret_cast<Fn>(entry)(7)==106);
    assert(reinterpret_cast<Fn>(trampoline)(7)==10);
    assert(!RewriteDispatchSlot(reinterpret_cast<uint64_t>(slot)+1,before));
    assert(mprotect(page,4096,PROT_READ)==0);
    assert(!RewriteDispatchSlot(reinterpret_cast<uint64_t>(slot),before));
    uint64_t current=0; std::memcpy(&current,slot,8);
    assert(current==reinterpret_cast<uint64_t>(&replacement));
    assert(munmap(page,4096)==0);
    RuntimeLinker rt;
    assert(rt.ApplicationHeapMalloc(123)==nullptr);
    rt.m_application_heap_malloc=reinterpret_cast<RuntimeLinker::Alloc>(0x11111);
    NovaFex::result=0x98765400;
    assert(rt.ApplicationHeapMalloc(123)==reinterpret_cast<void*>(0x98765400));
    assert(NovaFex::last_target==0x11111 && NovaFex::a0==123);
    rt.m_application_heap_posix_memalign=reinterpret_cast<RuntimeLinker::Align>(0x22222);
    NovaFex::result=0;
    assert(rt.ApplicationHeapMemalign(64,321)==reinterpret_cast<void*>(0xabcdef00));
    assert(NovaFex::last_target==0x22222 && NovaFex::a1==64 && NovaFex::a2==321);
    NovaFex::result=static_cast<uint64_t>(-12);
    assert(rt.ApplicationHeapMemalign(64,321)==nullptr);
    puts("NOVA_STARTUP_TEST: ALL PASS (fixed-placement validation, allocator slot and original trampoline, FEX callbacks)");
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = pathlib.Path(directory)/"test.cpp"
    binary = pathlib.Path(directory)/"test"
    source.write_text(program)
    subprocess.run(["c++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root/"src"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
