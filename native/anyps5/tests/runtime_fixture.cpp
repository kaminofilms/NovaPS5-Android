#include "runtime_fixture.hpp"
#include "renderer/host_services.hpp"
#include "renderer/selected_vulkan_loader.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include "prx/libkernel/Equeue/Equeue.hpp"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <vector>
namespace NovaAnyTest {
namespace {
struct Synthetic { std::uint64_t guest; std::span<std::byte> host; bool writable; };
std::vector<Synthetic> synthetic;
void* Translate(std::uint64_t address, std::size_t bytes, std::size_t* available) {
    for (const auto& run : synthetic) {
        if (address >= run.guest && address - run.guest < run.host.size()) {
            const auto offset = static_cast<std::size_t>(address - run.guest);
            *available = std::min(bytes, run.host.size() - offset);
            return run.host.data() + offset;
        }
    }
    *available = bytes;
    return reinterpret_cast<void*>(address);
}
void Copy(void* destination, const void* source, std::size_t bytes) {
    auto to = reinterpret_cast<std::uint64_t>(destination), from = reinterpret_cast<std::uint64_t>(source);
    while (bytes) {
        std::size_t a = 0, b = 0;
        void* dst = Translate(to, bytes, &a);
        auto* src = Translate(from, bytes, &b);
        const auto count = std::min(a, b);
        if (!count) throw std::runtime_error("fixture translation made no progress");
        std::memcpy(dst, src, count);
        to += count; from += count; bytes -= count;
    }
}
int Compare(const void* left, const void* right, std::size_t bytes) {
    std::vector<std::byte> a(bytes), b(bytes);
    Copy(a.data(), left, bytes); Copy(b.data(), right, bytes);
    return std::memcmp(a.data(), b.data(), bytes);
}
bool Query(std::uint64_t address, NovaAnyPS5::MemoryRun* result) {
    for (const auto& run : synthetic) {
        if (address >= run.guest && address - run.guest < run.host.size()) {
            *result = {run.guest, run.guest + run.host.size(), true, run.writable};
            return true;
        }
    }
    std::ifstream maps("/proc/self/maps");
    std::string line;
    while (std::getline(maps, line)) {
        unsigned long long first = 0, last = 0; char flags[5]{};
        if (std::sscanf(line.c_str(), "%llx-%llx %4s", &first, &last, flags) != 3 || last <= address) continue;
        *result = first > address ? NovaAnyPS5::MemoryRun{address, first, false, false} : NovaAnyPS5::MemoryRun{first, last, flags[0] == 'r', flags[1] == 'w'};
        return true;
    }
    return false;
}
void* Map(void* address, std::size_t bytes, int protection, int flags, int file, std::int64_t offset) noexcept {
    int nativeFlags = (flags & 1) ? MAP_SHARED : MAP_PRIVATE;
    if (flags & 0x1000) nativeFlags |= MAP_ANONYMOUS;
    if (flags & 0x10) nativeFlags |= MAP_FIXED_NOREPLACE;
    auto* result = mmap(address, bytes, protection, nativeFlags, file, offset);
    if (result != MAP_FAILED) {
        try { GuestAllocations::Mutation mutation; mutation.Add(result, bytes, (protection & 3) != 0, (protection & 2) != 0, true); }
        catch (...) { munmap(result, bytes); return MAP_FAILED; }
    }
    return result;
}
}
void MapSynthetic(std::uint64_t guest, std::span<std::byte> host, bool writable) { synthetic.push_back({guest, host, writable}); }
void Configure() {
    NovaAnyPS5::ConfigureHostServices({Copy, Compare, Translate, Query,
        [](std::int64_t) -> std::shared_ptr<void> { throw std::runtime_error("fixture does not create event queues"); },
        [](std::int64_t, const KernelEqueueEvent&) -> int { throw std::runtime_error("fixture does not create event queues"); },
        [](std::int64_t, std::uintptr_t, std::int16_t) -> int { throw std::runtime_error("fixture does not create event queues"); },
        [](std::int64_t, std::uintptr_t, std::int16_t, void*) -> int { throw std::runtime_error("fixture does not create event queues"); },
        Map, [](std::uintptr_t, std::size_t, int*, std::uint64_t*) { return false; },
        [](std::uintptr_t, const void*, std::size_t) { return false; },
        // Same contract as Nova: map at the fixed address and register the allocation.
        [](std::uint64_t address, std::size_t bytes) -> void* {
            void* mapped = Map(reinterpret_cast<void*>(address), bytes, 3, 0x1000 | 0x10, -1, 0);
            return mapped == MAP_FAILED ? nullptr : mapped;
        }});
    void* library = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!library) throw std::runtime_error(dlerror());
    auto owner = std::shared_ptr<void>(library, [](void* handle) { dlclose(handle); });
    auto entry = reinterpret_cast<PFN_vkGetInstanceProcAddr>(dlsym(library, "vkGetInstanceProcAddr"));
    NovaAnyPS5::ConfigureSelectedVulkan(entry, std::move(owner));
}
}
