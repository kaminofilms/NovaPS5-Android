#!/usr/bin/env python3
"""Execute the real patched AGC CommandBuffer and register-packet helpers on host.

Use synthetic high guest addresses backed by a non-identity aligned host
window. Detect guest-vs-host pointer mixups, lost callback semantics, invalid
PM4 guards, and low 14-bit register-count regressions.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

s = (Path(sys.argv[1]) / "src/libs/agc.cpp").read_text()

def extract(signature: str) -> str:
    start = s.index(signature)
    begin = s.index("{", start)
    depth, end = 1, begin + 1
    while depth:
        depth += (s[end] == "{") - (s[end] == "}")
        end += 1
    return s[start:end]

required = [
    'const auto* state = GuestMemory::Ptr(this, sizeof(CommandBuffer));',
    'auto* state = GuestMemory::Ptr(this, sizeof(CommandBuffer));',
    'state->callback(this, num_dw + state->reserved_dw, state->user_data)',
    'state->cursor_up += size_dw',
    'cmd = GuestMemory::Ptr(cmd, uint64_t {5} * sizeof(uint32_t));',
    'cmd = GuestMemory::Ptr(cmd, uint64_t {4} * sizeof(uint32_t));',
]
for expr in required:
    assert expr in s, f"missing AGC native guest hot path: {expr}"

cpp = r'''
#include <cstdint>
#include <cstdio>
#include <cassert>
#include <array>
#include <stdexcept>
#include <cstring>
#define KYTY_SYSV_ABI
#define PRINT_NAME(...)
#define AgcTrace(...)
#define LOGF(...)
#define LOGF_COLOR(...)
#define EXIT_NOT_IMPLEMENTED(expr) do { if(expr) throw std::runtime_error("Invalid"); } while(0)
#define KYTY_PM4(n,op,r) (0xc0000000u | (((n)-2u)<<16u) | ((op)<<8u) | (r))
namespace Pm4 {
constexpr uint32_t IT_INDIRECT_BUFFER = 0x3f;
constexpr uint32_t IT_SET_CONTEXT_REG_INDIRECT = 0x72;
constexpr uint32_t IT_SET_SH_REG_INDIRECT = 0x73;
constexpr uint32_t IT_SET_UCONFIG_REG_INDIRECT = 0x74;
}
constexpr uint32_t RegIndirectPacketSizeDw = 5;
constexpr int OK = 0;
constexpr int GRAPHICS5_ERROR_INVALID_PACKET = -22;
enum class RegIndirectPacket { Cx, Sh, Uc };
namespace GuestMemory {
constexpr uint64_t kBase = 0x8fc0000000ull;
alignas(64) std::array<unsigned char,8192> backing{};
template<class T> T* Ptr(T* guest, uint64_t bytes) {
    auto address = reinterpret_cast<uint64_t>(guest);
    if (address >= kBase && address - kBase <= backing.size() &&
        bytes <= backing.size() - (address - kBase)) {
        return reinterpret_cast<T*>(backing.data() + address - kBase);
    }
    return guest;
}
}
''' + extract('struct CommandBuffer {') + ';\n' + '\n'.join(
    extract(x) for x in [
        'static uint32_t reg_indirect_native_op(',
        'static constexpr bool is_trinity_mode(',
        'static uint32_t reg_indirect_pm4_r(',
        'static bool is_native_reg_indirect_packet(',
        'static void reg_indirect_write_packet(',
        'static int reg_indirect_patch_set_address(',
        'static int reg_indirect_patch_set_num_registers(',
        'static int reg_indirect_patch_add_registers(',
        'int KYTY_SYSV_ABI AgcUnknownIkfdtRIqCE(',
    ]
) + r'''
static CommandBuffer* expected_guest = nullptr;
static int grows = 0;
static bool grow(CommandBuffer* guest, uint32_t requested, void* user) {
    assert(guest == expected_guest);
    assert(user == reinterpret_cast<void*>(0x1234));
    assert(requested > 0);
    ++grows;
    auto* host = GuestMemory::Ptr(guest, sizeof(*guest));
    host->cursor_down = host->cursor_up + requested + 64;
    return true;
}
int main() {
    using namespace GuestMemory;
    auto* guest = reinterpret_cast<CommandBuffer*>(kBase);
    expected_guest = guest;
    auto* cb = Ptr(guest, sizeof(*guest));
    assert(cb != guest);
    *cb = {};
    cb->cursor_up = reinterpret_cast<uint32_t*>(kBase + 0x800);
    cb->cursor_down = cb->cursor_up + 10;
    cb->reserved_dw = 2;
    cb->callback = &grow;
    cb->user_data = reinterpret_cast<void*>(0x1234);
    assert(guest->GetAvailableSizeDW() == 8);
    auto* first = guest->AllocateDW(3);
    assert(reinterpret_cast<uint64_t>(first) == kBase + 0x800);
    assert(reinterpret_cast<uint64_t>(cb->cursor_up) == kBase + 0x80c);
    assert(grows == 0);
    auto* next = guest->AllocateDW(20);
    assert(reinterpret_cast<uint64_t>(next) == kBase + 0x80c);
    assert(grows == 1);
    assert(reinterpret_cast<uint64_t>(cb->cursor_up) == kBase + 0x85c);
    const auto* native = Ptr(guest, sizeof(*guest));
    assert(native->GetAvailableSizeDW() >= 1);

    auto* packet_guest = reinterpret_cast<uint32_t*>(kBase + 0x1000);
    auto* packet = Ptr(packet_guest, 5 * sizeof(uint32_t));
    for (auto kind : {RegIndirectPacket::Cx, RegIndirectPacket::Sh, RegIndirectPacket::Uc}) {
        for (uint32_t num : {0u, 1u, 17u, 0x3fffu, 0x4000u, 0xffffffffu}) {
            reg_indirect_write_packet(packet_guest, kBase + 0x500, num, kind);
            assert(is_native_reg_indirect_packet(packet_guest, kind));
            auto prior = packet[4];
            assert(reg_indirect_patch_add_registers(packet_guest, num, kind) == OK);
            assert((packet[4] & 0x3fffu) == (((prior & 0x3fffu) + num) & 0x3fffu));
            assert(reg_indirect_patch_set_num_registers(packet_guest, num, kind) == OK);
            assert((packet[4] & 0x3fffu) == (num & 0x3fffu));
            auto addr = kBase + 0x1abc;
            assert(reg_indirect_patch_set_address(packet_guest, addr, kind) == OK);
            assert(packet[2] == uint32_t(addr >> 32u));
            assert((packet[1] & ~0x3u) == (uint32_t(addr) & ~0x3u));
        }
    }
    packet[0] = 0;
    assert(reg_indirect_patch_add_registers(packet_guest, 7, RegIndirectPacket::Cx)
           == GRAPHICS5_ERROR_INVALID_PACKET);

    packet[0] = KYTY_PM4(5, Pm4::IT_INDIRECT_BUFFER, 0);
    packet[1] = 2;
    packet[3] = 0xcff00001u;
    auto* target = reinterpret_cast<const volatile uint32_t*>(kBase + 0x3440);
    assert(AgcUnknownIkfdtRIqCE(packet_guest, 2, target, 0x345, 0, 0) == OK);
    assert((packet[1] & ~0x3u) == uint32_t(kBase + 0x3440));
    assert(packet[2] == uint32_t((kBase + 0x3440) >> 32));
    assert((packet[3] & 0xfffffu) == 0x345);
    packet[0] = 0;
    assert(AgcUnknownIkfdtRIqCE(packet_guest, 2, target, 0x345, 0, 0)
           == GRAPHICS5_ERROR_INVALID_PACKET);
    puts("PASS AGC CommandBuffer native guest views, grow callback, and register PM4 mutations");
}
'''

with tempfile.TemporaryDirectory() as d:
    src, exe = Path(d) / "agc_hostview.cpp", Path(d) / "agc_hostview"
    src.write_text(cpp)
    subprocess.run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra",
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
