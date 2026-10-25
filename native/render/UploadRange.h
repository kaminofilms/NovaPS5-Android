#pragma once
#include <algorithm>
#include <cstdint>
namespace NovaRender {
struct UploadRange { uint64_t offset, size; };
// Bound all destination copies, including gaps. Invalid input retains the old
// full-buffer dependency; never wrap offset + size or narrow past a copy.
template<class Copies>
UploadRange UploadDestinationRange(const Copies& copies, uint64_t capacity) {
    uint64_t first = capacity, last = 0;
    for (const auto& copy : copies) {
        if (!copy.size || copy.dstOffset >= capacity || copy.size > capacity - copy.dstOffset)
            return {0, capacity};
        first = std::min(first, uint64_t(copy.dstOffset));
        last = std::max(last, uint64_t(copy.dstOffset + copy.size));
    }
    return last > first ? UploadRange{first, last - first} : UploadRange{0, capacity};
}
}
