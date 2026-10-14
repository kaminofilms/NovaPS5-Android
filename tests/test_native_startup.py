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

# Regression (ccleste PPSA59322: MapDirect failed 0x80020016 addr=0x400004000 len=0x200000
# flags=0x10): MAP_FIXED direct maps use the guest page alignment for every title on the
# FEX build, not only behind a per-title environment switch.
memory = (root / "src/kernel/memory.cpp").read_text()
fixed_block = memory[memory.index("NovaValidDirectFixedAddress(in_addr") - 900:memory.index("NovaValidDirectFixedAddress(in_addr")]
assert "page_placement = true;" in fixed_block, "fixed direct maps must not require the alignment hint"
assert "NOVA_FIXED_DIRECT_PAGE_ALIGNMENT" not in memory, "fixed placement must not depend on a title profile"
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

# 0.9.6 regressions: translated guest VA (above 2^39) and the GPU.
#  - Super Meat Boy 3D (PPSA31162) died in VideoOutRegisterBuffers2 with "invalid data image
#    range: address=0x0000013fc0000000 size=0x0000000001fe0000": its 768 GiB arena is placed at
#    2^39 and ends at 1.25 TiB, beyond the GPU's 1 TiB domain. The Nova domain is [0, 1.5 TiB).
#  - Emulator code must read/write such memory through the translated host address (split at
#    slot boundaries), and GPU-tracked faults on a slot's host window map back to the guest.
regions = (root / "src/graphics/host_gpu/regionDefinitions.h").read_text()
nova_branch = regions[regions.index("#if defined(__aarch64__)") + len("#if defined(__aarch64__)"):regions.index("#else", regions.index("#if defined(__aarch64__)"))]
guest_range = function(regions, "struct GuestRange {") + ";"
reverse = function(memory, "static uint64_t NovaHostToGuestVA(")
assert "NovaHostToGuestVA(fault_vaddr)" in function(memory, "bool HandleGpuFault("), "GPU faults must map slot windows back to guest addresses"
for name, needle in (("graphicsRun.cpp", "HostCommands(draw_commands)"), ("graphicsRun.cpp", "HostCommands(commands)")):
    assert needle in (root / "src/graphics/guest_gpu" / name).read_text(), needle
assert "guest_base      = shader_addr" in (root / "src/graphics/shader/shader.cpp").read_text(), "shader Base() must stay the guest address"
assert "SA_NODEFER" in (root / "src/common/hostException.cpp").read_text(), "nested GPU-tracking faults inside emulated accesses"
# 0.9.8: host operations on translated guest ranges are split per 1 GiB slot (Meat Boy's
# sceKernelBatchMap 0xa07fee0000+0x1c0000 crossed a slot and failed with ENOMEM), and RELEASE_MEM
# INT_SEL 3 raises the end-of-pipe interrupt like shadPS4 (Luna's AGC interrupt thread never woke).
space = (root / "src/kernel/memoryAddressSpace.inc").read_text()
map_backing = function(space, "bool MapBacking(")
assert "ForEachHostUnit" in map_backing and "UnmapBackingUnit" in map_backing, "MapBacking must split per slot and roll back"
for name in ("Protect(", "ProtectTransient(", "UnmapBacking(", "Commit(", "ReleaseCommitted("):
    assert "ForEachHostUnit" in function(space, "bool " + name), name
release_mem = function((root / "src/graphics/guest_gpu/command_processor/pm4Handlers.cpp").read_text(), "KYTY_CP_OP_PARSER(CpOpReleaseMem)")
assert "interrupt_selector == 0x03" in release_mem and "interrupt_selector = 0x02" in release_mem, "RELEASE_MEM INT_SEL 3 must interrupt"
ampr = (root / "src/libs/libAmpr.cpp").read_text()
assert "atomic_ref(*reinterpret_cast<uint64_t*>" not in ampr, "AMPR waits must read guest memory through its host address"
nova_fex = (root / "src/common/novaFex.h").read_text()
nova_guest = nova_fex[nova_fex.index("namespace NovaGuest {"):nova_fex.index("} // namespace NovaGuest") + len("} // namespace NovaGuest")]
program2 = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
namespace LibKernel::Memory {
constexpr uint64_t kExtendedMemoryBase = 0x080000000000ull;
constexpr uint64_t kExtendedMemorySize = 512ull * 1024 * 1024 * 1024;
}
''' + nova_branch + guest_range + r'''
// Mock FEX translation: guest [0x803ffff000, 0x8040000000) -> a, [0x8040000000, 0x8040001000) -> b.
static uint8_t a[0x1000], b[0x1000];
namespace NovaFex {
inline uint64_t TranslateGuestVA(uint64_t g) {
    if (g >= 0x803ffff000ull && g < 0x8040000000ull) return reinterpret_cast<uint64_t>(a) + (g - 0x803ffff000ull);
    if (g >= 0x8040000000ull && g < 0x8040001000ull) return reinterpret_cast<uint64_t>(b) + (g - 0x8040000000ull);
    return g;
}
}
''' + nova_guest + r'''
#define KYTY_NOVA_FEX 1
#define KYTY_COMMON_NOVA_FEX_H_ 1
#include "common/guestMemory.h"
static constexpr uint32_t kNovaSlotRecords = 4;
static std::atomic<uint64_t> g_nova_slot_host[kNovaSlotRecords];
static std::atomic<uint64_t> g_nova_slot_guest[kNovaSlotRecords];
static std::atomic<uint32_t> g_nova_slot_count {0};
''' + reverse + r'''
int main() {
    assert((GuestRange {0x13fc0000000ull, 0x1fe0000ull}.Valid()));          // Meat Boy video out buffer
    assert((GuestRange {0x8000000000ull + 0xc000000000ull - 0x4000, 0x4000}.Valid()));
    assert(!(GuestRange {LOWER_ADDRESS_SIZE, 0x4000}.Valid()));
    assert(!(GuestRange {LOWER_ADDRESS_SIZE - 0x4000, 0x8000}.Valid()));
    assert(!(GuestRange {LibKernel::Memory::kExtendedMemoryBase, 0x4000}.Valid()));
    assert(LOWER_ADDRESS_SIZE + GPU_EXTENDED_SIZE == (1ull << 40) + LibKernel::Memory::kExtendedMemorySize);
    for (int i = 0; i < 0x1000; i++) { a[i] = uint8_t(i); b[i] = uint8_t(0x80 + i); }
    // One slot: translated pointer. Across a slot boundary: the guest address (fault emulation).
    assert(GuestMemory::Ptr<uint8_t>(0x803ffff100ull, 16) == a + 0x100);
    assert(GuestMemory::Ptr<uint8_t>(0x803ffffff8ull, 16) == reinterpret_cast<uint8_t*>(0x803ffffff8ull));
    assert(GuestMemory::Ptr<uint8_t>(0x1234ull, 16) == reinterpret_cast<uint8_t*>(0x1234ull));
    uint8_t out[0x20];
    GuestMemory::Read(out, 0x803ffffff0ull, sizeof(out));
    for (int i = 0; i < 16; i++) assert(out[i] == uint8_t(0xff0 + i) && out[16 + i] == uint8_t(0x80 + i));
    GuestMemory::Fill32(0x803ffffff8ull, 0xa5a5a5a5u, 16);
    assert(a[0xff8] == 0xa5 && a[0xfff] == 0xa5 && b[0] == 0xa5 && b[7] == 0xa5 && b[8] == 0x88);
    uint8_t host[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    GuestMemory::Write(0x803ffffffcull, host, 8);
    assert(a[0xffc] == 1 && a[0xfff] == 4 && b[0] == 5 && b[3] == 8);
    // Reverse lookup of slot windows for GPU faults.
    g_nova_slot_host[0] = 0x1004000000ull; g_nova_slot_guest[0] = 0x13c0000000ull; g_nova_slot_count = 1;
    assert(NovaHostToGuestVA(0x1004000000ull + 0x3fc0123) == 0x13c0000000ull + 0x3fc0123);
    assert(NovaHostToGuestVA(0x1004000000ull + (1ull << 30)) == 0);
    assert(NovaHostToGuestVA(0x1000) == 0);
    puts("NOVA_STARTUP_TEST: ALL PASS (GPU domain covers translated arenas, guest-memory helpers, slot reverse lookup)");
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = pathlib.Path(directory)/"test2.cpp"
    binary = pathlib.Path(directory)/"test2"
    source.write_text(program2)
    subprocess.run(["c++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root/"src"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
