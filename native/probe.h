#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
namespace Nova {
struct ElfProbe {bool valid=false;uint16_t machine=0;uint16_t type=0;uint64_t entry=0;uint16_t segments=0;std::string message;};
ElfProbe InspectElf(const uint8_t* data,size_t size);
}
