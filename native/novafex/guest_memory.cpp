// Bulk guest memory access for native HLE. Linked with --wrap for the four C
// memory primitives; __real_* bypasses these wrappers without recursion.
// SPDX-License-Identifier: GPL-2.0-or-later
#include "novafex.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>

extern "C" {
void* __real_memset(void*, int, size_t);
void* __real_memcpy(void*, const void*, size_t);
void* __real_memmove(void*, const void*, size_t);
int __real_memcmp(const void*, const void*, size_t);
}

namespace {
constexpr uint64_t Low = uint64_t{1} << 39;
constexpr uint64_t End = uint64_t{1} << 47;
constexpr uint64_t Slot = uint64_t{1} << 30;
bool GuestRange(uint64_t address) { return address >= Low && address < End; }
bool NeedsTranslation(uint64_t a, uint64_t b = 0) {
    return NovaFex::GuestVAEnabled() && (GuestRange(a) || GuestRange(b));
}
uint64_t Forward(uint64_t a, uint64_t count) {
    if (a < Low) return std::min(count, Low - a);
    return GuestRange(a) ? std::min(count, Slot - (a & (Slot - 1))) : count;
}
uint64_t Backward(uint64_t end, uint64_t count) {
    return GuestRange(end - 1) ? std::min(count, ((end - 1) & (Slot - 1)) + 1) : count;
}
void* Host(uint64_t a) {
    return reinterpret_cast<void*>(GuestRange(a) ? NovaFex::TranslateGuestVA(a) : a);
}
}

extern "C" void* __wrap_memset(void* dst, int value, size_t count) {
    auto d = reinterpret_cast<uint64_t>(dst);
    if (count == 0 || !NeedsTranslation(d)) return __real_memset(dst, value, count);
    while (count) {
        const auto size = Forward(d, count);
        __real_memset(Host(d), value, size);
        d += size; count -= size;
    }
    return dst;
}

extern "C" void* __wrap_memcpy(void* dst, const void* src, size_t count) {
    auto d = reinterpret_cast<uint64_t>(dst), s = reinterpret_cast<uint64_t>(src);
    if (count == 0 || !NeedsTranslation(d, s)) return __real_memcpy(dst, src, count);
    while (count) {
        const auto size = Forward(s, Forward(d, count));
        __real_memcpy(Host(d), Host(s), size);
        d += size; s += size; count -= size;
    }
    return dst;
}

extern "C" void* __wrap_memmove(void* dst, const void* src, size_t count) {
    auto d = reinterpret_cast<uint64_t>(dst), s = reinterpret_cast<uint64_t>(src);
    if (count == 0 || !NeedsTranslation(d, s)) return __real_memmove(dst, src, count);
    if (d > s && d - s < count) {
        d += count; s += count;
        while (count) {
            const auto size = Backward(s, Backward(d, count));
            d -= size; s -= size;
            __real_memmove(Host(d), Host(s), size);
            count -= size;
        }
    } else {
        while (count) {
            const auto size = Forward(s, Forward(d, count));
            __real_memmove(Host(d), Host(s), size);
            d += size; s += size; count -= size;
        }
    }
    return dst;
}

extern "C" int __wrap_memcmp(const void* lhs, const void* rhs, size_t count) {
    auto a = reinterpret_cast<uint64_t>(lhs), b = reinterpret_cast<uint64_t>(rhs);
    if (count == 0 || !NeedsTranslation(a, b)) return __real_memcmp(lhs, rhs, count);
    while (count) {
        const auto size = Forward(b, Forward(a, count));
        const auto result = __real_memcmp(Host(a), Host(b), size);
        if (result) return result;
        a += size; b += size; count -= size;
    }
    return 0;
}
