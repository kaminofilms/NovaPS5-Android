#!/usr/bin/env python3
"""Execute patched stack-query code with controlled range and guest-view adapters."""
from pathlib import Path
import subprocess
import sys
import tempfile

s = (Path(sys.argv[1])/'src/kernel/memory.cpp').read_text()
start = s.index('static int KYTY_SYSV_ABI KernelIsStackNovaT(void* addr, void** start, void** end);')
end = s.index('int KYTY_SYSV_ABI KernelAvailableFlexibleMemorySize', start)
code = s[start:end]
shim = r'''
#include <cstdint>
#include <cinttypes>
#include <mutex>
#include <cassert>
#define KYTY_SYSV_ABI
#define PRINT_NAME() ((void)0)
#define LOGF(...) ((void)0)
constexpr int KERNEL_ERROR_EACCES=-13, OK=0;
enum class VirtualRangeType { Stack, Heap };
struct VirtualRanges {
    struct Range { VirtualRangeType type; uint64_t start, size; };
    bool known=false; Range range{};
    bool Query(uint64_t, int, Range* out) { *out=range; return known; }
} ranges;
auto* g_virtual_ranges=&ranges;
std::recursive_mutex g_memory_operation_mutex;
template<class... T> void NovaMemTrace(T...) {}
void* guest_start=nullptr; void* guest_end=nullptr;
namespace GuestMemory {
template<class T> T* Ptr(T* p, uint64_t size) {
    assert(size==sizeof(void*));
    if(reinterpret_cast<uint64_t>(p)==0x9000000000ull) return reinterpret_cast<T*>(&guest_start);
    if(reinterpret_cast<uint64_t>(p)==0x9000000010ull) return reinterpret_cast<T*>(&guest_end);
    return p;
}
}
'''
tests = r'''
int main() {
    void* a=reinterpret_cast<void*>(3); void* b=reinterpret_cast<void*>(8);
    assert(KernelIsStack(nullptr,&a,&b)==KERNEL_ERROR_EACCES);
    assert(a==nullptr && b==nullptr);
    assert(KernelIsStack(nullptr,nullptr,nullptr)==KERNEL_ERROR_EACCES);
    ranges.known=true; ranges.range={VirtualRangeType::Heap,0x1000,0x4000};
    a=reinterpret_cast<void*>(3); b=reinterpret_cast<void*>(8);
    assert(KernelIsStack(nullptr,&a,&b)==OK && a==nullptr && b==nullptr);
    ranges.range.type=VirtualRangeType::Stack;
    assert(KernelIsStack(nullptr,&a,&b)==OK);
    assert(reinterpret_cast<uint64_t>(a)==0x1000 && reinterpret_cast<uint64_t>(b)==0x5000);
    auto** ga=reinterpret_cast<void**>(0x9000000000ull);
    auto** gb=reinterpret_cast<void**>(0x9000000010ull);
    assert(KernelIsStack(nullptr,ga,gb)==OK);
    assert(reinterpret_cast<uint64_t>(guest_start)==0x1000 && reinterpret_cast<uint64_t>(guest_end)==0x5000);
    ranges.known=false;
    assert(KernelIsStack(nullptr,ga,gb)==KERNEL_ERROR_EACCES);
    assert(guest_start==nullptr && guest_end==nullptr);
}
'''
with tempfile.TemporaryDirectory() as d:
    source=Path(d)/'stack.cpp'; binary=Path(d)/'stack'
    source.write_text(shim+code+tests)
    subprocess.run(['g++','-std=c++20','-O2',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('NOVA_STACK_OUTPUTS: unknown, heap, stack, null and translated guest outputs PASS')
