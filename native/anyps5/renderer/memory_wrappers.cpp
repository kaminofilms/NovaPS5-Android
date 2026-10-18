#include "host_services.hpp"
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <stdexcept>
extern "C" {
void* __real_memcpy(void*, const void*, std::size_t);
void* __real_memmove(void*, const void*, std::size_t);
void* __real_memset(void*, int, std::size_t);
int __real_memcmp(const void*, const void*, std::size_t);
}
namespace {
bool Guest(std::uint64_t address) { return address >= (std::uint64_t{1} << 39) && address < (std::uint64_t{1} << 47); }
std::size_t Forward(std::uint64_t address, std::size_t count) {
    if (!Guest(address)) return count;
    return std::min<std::uint64_t>(count, (std::uint64_t{1} << 30) - (address & ((std::uint64_t{1} << 30) - 1)));
}
std::size_t Backward(std::uint64_t end, std::size_t count) {
    if (!Guest(end - 1)) return count;
    return std::min<std::uint64_t>(count, ((end - 1) & ((std::uint64_t{1} << 30) - 1)) + 1);
}
void* Host(std::uint64_t address, std::size_t count) {
    if (!Guest(address)) return reinterpret_cast<void*>(address);
    auto* host = NovaAnyPS5::ContiguousMemory(address, count);
    if (!host) throw std::runtime_error("AnyPS5 memory primitive crossed an untranslated guest range");
    return host;
}
}
extern "C" void* __wrap_memcpy(void* destination, const void* source, std::size_t bytes) {
    if (bytes && (Guest(reinterpret_cast<std::uint64_t>(destination)) || Guest(reinterpret_cast<std::uint64_t>(source)))) {
        NovaAnyPS5::CopyMemory(destination, source, bytes);
        return destination;
    }
    return __real_memcpy(destination, source, bytes);
}
extern "C" int __wrap_memcmp(const void* left, const void* right, std::size_t bytes) {
    if (bytes && (Guest(reinterpret_cast<std::uint64_t>(left)) || Guest(reinterpret_cast<std::uint64_t>(right))))
        return NovaAnyPS5::CompareMemory(left, right, bytes);
    return __real_memcmp(left, right, bytes);
}
extern "C" void* __wrap_memset(void* destination, int value, std::size_t bytes) {
    auto address = reinterpret_cast<std::uint64_t>(destination);
    if (!bytes || !Guest(address)) return __real_memset(destination, value, bytes);
    while (bytes) {
        const auto count = Forward(address, bytes);
        __real_memset(Host(address, count), value, count);
        address += count;
        bytes -= count;
    }
    return destination;
}
extern "C" void* __wrap_memmove(void* destination, const void* source, std::size_t bytes) {
    auto to = reinterpret_cast<std::uint64_t>(destination);
    auto from = reinterpret_cast<std::uint64_t>(source);
    if (!bytes || (!Guest(to) && !Guest(from))) return __real_memmove(destination, source, bytes);
    if (to > from && to - from < bytes) {
        to += bytes;
        from += bytes;
        while (bytes) {
            const auto count = Backward(to, Backward(from, bytes));
            to -= count;
            from -= count;
            __real_memmove(Host(to, count), Host(from, count), count);
            bytes -= count;
        }
    } else {
        while (bytes) {
            const auto count = Forward(to, Forward(from, bytes));
            __real_memmove(Host(to, count), Host(from, count), count);
            to += count;
            from += count;
            bytes -= count;
        }
    }
    return destination;
}
