// Table-based PFS reader. Format cross-checked with shadPS4 pfs.h and
// KytyPlus src/package/naps/GameImage.cs (MIT). No recovery/file carving.
#pragma once
#include <string>
#include <cstdint>
namespace NovaPkg {
uint32_t ExtractTablePfs(const std::string& path, uint64_t base, uint64_t size,
                         uint64_t superblock, const std::string& output);
}
