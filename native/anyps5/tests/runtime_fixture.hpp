#pragma once
#include <cstddef>
#include <cstdint>
#include <span>
namespace NovaAnyTest {
void Configure();
void MapSynthetic(std::uint64_t guest, std::span<std::byte> host, bool writable = true);
}
