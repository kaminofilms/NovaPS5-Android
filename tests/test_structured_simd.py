#!/usr/bin/env python3
"""Run production ARM64 instruction decoding on a host with a synthetic signal frame.
This supplements, and does not replace, native ARM64 signal-return tests.
"""
import pathlib, subprocess, tempfile
root = pathlib.Path(__file__).resolve().parents[1]
s = (root/'native/novafex/novafex.cpp').read_text()
start = s.index('uint64_t ReadX(ucontext_t*')
end = s.index('} // namespace', start)
program = r'''
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <atomic>
#include <signal.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>
#define ucontext_t TestContext
struct _aarch64_ctx { uint32_t magic, size; };
constexpr uint32_t FPSIMD_MAGIC = 0x46508001;
struct alignas(16) fpsimd_context { _aarch64_ctx head; uint32_t fpsr, fpcr; __uint128_t vregs[32]; };
struct TestContext { struct { uint64_t regs[31], sp, pc; alignas(16) uint8_t __reserved[4096]; } uc_mcontext; };
namespace FEXCore::Nova { bool GuestVAEnabled = true; constexpr uint64_t kGuestVALowLimit = 1ull << 39; }
namespace NovaFex {
uint64_t table[1<<17]{};
uint64_t TranslateGuestVA(uint64_t p) { return p + table[(p>>30)&((1<<17)-1)]; }
void MapGuestVASlot(uint64_t p, uint64_t h) { table[p>>30] = h-p; }
void UnmapGuestVASlot(uint64_t p) { table[p>>30] = 0; }
''' + s[start:end] + r'''
bool HandleHostFault(int, siginfo_t* info, void* uc) { return EmulateHighAccess(static_cast<TestContext*>(uc), reinterpret_cast<uint64_t>(info->si_addr)); }
}
int failures=0;
void Check(const char* n, bool ok) { printf("%s: %s\n", n, ok ? "PASS":"FAIL"); failures += !ok; }
int main() {
''' + (root/'native/novafex/test/structured_simd.inc').read_text() + '\nreturn failures ? 1 : 0; }\n'
with tempfile.TemporaryDirectory() as d:
    source = pathlib.Path(d)/'test.cpp'; binary = pathlib.Path(d)/'test'
    source.write_text(program)
    subprocess.run(['g++','-std=c++20','-O2','-Wall','-Wextra',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
