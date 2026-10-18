#pragma once
#include <cstdint>
#include <vector>
namespace NovaAnyPS5 {
struct Mapping {
    std::uint64_t address;
    std::uint64_t bytes;
    bool readable;
    bool writable;
    bool gpu;
    bool operator==(const Mapping&) const = default;
};
using MappingSnapshot = std::vector<Mapping> (*)();
void ConfigureMemoryRegistry(MappingSnapshot snapshot);
void DisableMemoryRegistry();
}
