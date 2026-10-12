#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace Nova {
// Bounded, straight-line integer smoke-test translator. No memory, syscalls,
// branches, flags consumers, SIMD, ABI calls, or console runtime execution.
// RET is a test-block boundary returning RAX, not a guest-stack return.
struct Block {
    bool ok = false;
    std::string error;
    size_t guest_bytes = 0;
    size_t instructions = 0;
    std::array<uint64_t,16> reference{};
    std::vector<uint32_t> arm64;
};
Block TranslateBlock(const uint8_t* code, size_t size);
std::string RunCpuSmokeTest();
}
