#!/usr/bin/env python3
"""0.9.57: execute the restored WAIT_REG_MEM give-up (production text).

Dead Cells: first stall on an address continues after 2000 ms, later stalls on
a remembered address after 100 ms (0.9.10 behaviour). Other titles never give
up unless NOVA_GPU_WAIT_GIVEUP=1; NOVA_GPU_WAIT_GIVEUP=0 disables it for Dead
Cells. Structure: the give-up runs after the diagnostic and before SuspendPm4.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

src = Path(sys.argv[1]) / 'src'
SAN = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('SANITIZE') == '1' else []
gr = (src / 'graphics/guest_gpu/graphicsRun.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


helpers = between(gr, 'bool NovaWaitGiveUp() {', 'uint64_t NovaGpuNowMs() {')
wait = between(gr, 'void CommandProcessor::WaitRegMem(', 'template void CommandProcessor::WaitRegMem<uint32_t>')
block = between(wait, '		if (NovaWaitGiveUp()) {', '\n\n#endif\n\t\tSuspendPm4();')
assert wait.index('NOVA_GPU_WAIT: queue(event') < wait.index('if (NovaWaitGiveUp()) {') < wait.rindex('SuspendPm4();')
assert block.count('return;') == 1
body = block.replace('return;', 'return true;')

code = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>
''' + helpers + r'''
std::atomic<uint64_t> g_nova_gpu_stall_since_ms {0};
const void* m_nova_wait_addr = nullptr;
bool Step(const void* addr, uint64_t waited) {
  m_nova_wait_addr = addr; g_nova_gpu_stall_since_ms.store(1);
''' + body + r'''
  return false;
}
int main(int, char** argv) {
  const bool on = std::strcmp(argv[1], "on") == 0;
  int a = 0, b = 0;
  assert(!Step(&a, 1999));
  assert(Step(&a, 2001) == on);
  if (on) { assert(m_nova_wait_addr == nullptr && g_nova_gpu_stall_since_ms.load() == 0); }
  assert(Step(&a, 101) == on);      // remembered address: 100 ms
  assert(!Step(&a, 99));
  assert(!Step(&b, 150));           // new address: still 2000 ms
  assert(Step(&b, 2500) == on);
  std::puts("NOVA_0957_WAIT: PASS");
}
'''
with tempfile.TemporaryDirectory() as t:
    p = Path(t) / 'w.cpp'; p.write_text(code); out = Path(t) / 'w'
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', *SAN,
                    str(p), '-o', str(out)], check=True)
    base = {k: v for k, v in os.environ.items() if not k.startswith('NOVA_')}
    for env, mode in [({'NOVA_CACHE_TITLE_ID': 'PPSA15552'}, 'on'),
                      ({'NOVA_CACHE_TITLE_ID': 'PPSA15552', 'NOVA_GPU_WAIT_GIVEUP': '0'}, 'off'),
                      ({'NOVA_CACHE_TITLE_ID': 'PPSA27841'}, 'off'),
                      ({'NOVA_CACHE_TITLE_ID': 'PPSA36257'}, 'off'),
                      ({}, 'off'),
                      ({'NOVA_CACHE_TITLE_ID': 'PPSA27841', 'NOVA_GPU_WAIT_GIVEUP': '1'}, 'on')]:
        subprocess.run([str(out), mode], env={**base, **env}, check=True, timeout=20)
print('NOVA_0957_REGRESSION: PASS')
