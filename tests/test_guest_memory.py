#!/usr/bin/env python3
"""Exercise the actual memory wrappers with noncontiguous guest slot backing."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
program = r'''
#include "novafex.h"
#include <cassert>
#include <cstring>
#include <cstdint>
#include <array>
constexpr uint64_t slot = 0x8fc0000000ull, span = 1ull << 30;
std::array<unsigned char, 4096> head{}, tail{}, next{};
namespace NovaFex {
bool GuestVAEnabled() { return true; }
uint64_t TranslateGuestVA(uint64_t a) {
    if (a >= slot && a < slot + 4096) return reinterpret_cast<uint64_t>(head.data()) + a - slot;
    if (a >= slot + span - 4096 && a < slot + span) return reinterpret_cast<uint64_t>(tail.data()) + a - (slot + span - 4096);
    if (a >= slot + span && a < slot + span + 4096) return reinterpret_cast<uint64_t>(next.data()) + a - (slot + span);
    return a;
}
}
int main() {
    void* (*volatile set)(void*, int, size_t) = &std::memset;
    void* (*volatile copy)(void*, const void*, size_t) = &std::memcpy;
    void* (*volatile move)(void*, const void*, size_t) = &std::memmove;
    int (*volatile cmp)(const void*, const void*, size_t) = &std::memcmp;
    unsigned char low[128], back[128], reference[128];
    for (unsigned i = 0; i < 128; ++i) low[i] = i;
    auto* cross = reinterpret_cast<unsigned char*>(slot + span - 64);
    assert(set(cross, 0xa5, 128) == cross);
    for (unsigned i = 0; i < 64; ++i) assert(tail[4032+i] == 0xa5 && next[i] == 0xa5);
    assert(copy(cross, low, 128) == cross);
    assert(copy(back, cross, 128) == back && cmp(back, low, 128) == 0);
    assert(cmp(cross, low, 128) == 0);
    low[100] ^= 1;
    assert(cmp(cross, low, 128) < 0);
    low[100] ^= 1;
    assert(copy(reference, low, 128) == reference);
    move(reference + 17, reference, 100);
    assert(move(cross + 17, cross, 100) == cross + 17);
    copy(back, cross, 128);
    assert(cmp(back, reference, 128) == 0);
    move(reference, reference + 19, 100);
    move(cross, cross + 19, 100);
    copy(back, cross, 128);
    assert(cmp(back, reference, 128) == 0);
    copy(reinterpret_cast<void*>(slot), low, 128);
    copy(cross, reinterpret_cast<void*>(slot), 128);
    assert(cmp(cross, low, 128) == 0);
    assert(copy(cross, low, 0) == cross && set(cross, 0, 0) == cross);
    assert(move(cross, cross, 128) == cross && cmp(cross, cross, 128) == 0);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p / 'test.cpp').write_text(program)
    subprocess.run(['g++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I', str(root / 'native/novafex'), str(p / 'test.cpp'),
                    str(root / 'native/novafex/guest_memory.cpp'),
                    '-Wl,--wrap=memset,--wrap=memcpy,--wrap=memmove,--wrap=memcmp',
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
print('NOVA_GUEST_MEMORY: PASS mixed addresses, slot crossings, overlap, return values, compare ordering')
