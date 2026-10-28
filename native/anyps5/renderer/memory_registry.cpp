#include <cstdio>
#include "memory_registry.hpp"
#include "../memory_mutation.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include "prx/libc/include/GuestWriteWatch.hpp"
#include <algorithm>
#include <atomic>
#include <mutex>
#include <stdexcept>
#if defined(__ANDROID__)
extern "C" bool NovaAnyPS5WriteWatchFault(std::uintptr_t address);
extern "C" void NovaAnyPS5WriteWatchMarkWritten(std::uintptr_t address, std::size_t bytes);
#endif
namespace NovaAnyPS5 {
namespace {
// Set once the first guest range is registered with an available watch. Until then the fault
// and host-write hooks do nothing (and never construct the watch inside a signal handler).
std::atomic<bool> watchActive{false};
std::atomic<MappingSnapshot> takeSnapshot{nullptr};
std::atomic<bool> ready{false};
std::vector<Mapping> tracked;
thread_local std::uint32_t mutationDepth = 0;
thread_local void* activeMutation = nullptr;
// AnyPS5 re-copies guest heaps it cannot write-watch on every address-based build. Register Nova's
// writable guest mappings so only pages the guest wrote are refreshed. Guest addresses at or above
// 2^39 are translated to other host addresses and are left to the copy path.
constexpr std::uint64_t IdentityGuestLimit = std::uint64_t{1} << 39;
bool watchable(const Mapping& item) { return item.writable && item.readable && item.address + item.bytes <= IdentityGuestLimit; }
std::uint64_t watchedRanges = 0, watchedBytes = 0;
void watch(const Mapping& item) {
    if (!watchable(item)) return;
    static const bool available = [] {
        const bool on = GuestWriteWatch::GuestWriteWatchAvailable_nid_postfix();
        std::fprintf(stderr, "NOVA_ANYPS5: guest write watch %s\n", on ? "available: guest heaps are registered" : "UNAVAILABLE: guest heaps are copied on every address-based build");
        return on;
    }();
    if (!available) return;
    GuestWriteWatch::GuestWriteWatchRegister_nid_postfix(reinterpret_cast<const void*>(item.address), item.bytes);
    watchActive.store(true, std::memory_order_release);
    ++watchedRanges;
    watchedBytes += item.bytes;
    if ((watchedRanges & (watchedRanges - 1)) == 0)
        std::fprintf(stderr, "NOVA_ANYPS5: write watch registered %llu guest ranges (%llu MiB); last 0x%llx+0x%llx covered=%d\n",
            static_cast<unsigned long long>(watchedRanges), static_cast<unsigned long long>(watchedBytes >> 20),
            static_cast<unsigned long long>(item.address), static_cast<unsigned long long>(item.bytes),
            GuestWriteWatch::GuestWriteWatchCovers_nid_postfix(static_cast<std::uintptr_t>(item.address), item.bytes) ? 1 : 0);
}
void unwatch(const Mapping& item) {
    if (watchable(item)) GuestWriteWatch::GuestWriteWatchUnregister_nid_postfix(reinterpret_cast<const void*>(item.address), item.bytes);
}
}
void ConfigureMemoryRegistry(MappingSnapshot snapshot) {
    if (!snapshot) throw std::invalid_argument("Null native guest memory registry snapshot");
    MappingSnapshot expected = nullptr;
    if (!takeSnapshot.compare_exchange_strong(expected, snapshot)) throw std::logic_error("Native guest memory registry already configured");
    ready.store(true, std::memory_order_release);
}
void DisableMemoryRegistry() { ready.store(false, std::memory_order_release); }
bool MemoryHooksReady() { return ready.load(std::memory_order_acquire); }
void* BeginMemoryChange() {
    if (mutationDepth++) return nullptr;
    void* mutation = nullptr;
    try {
        mutation = GuestAllocations::GuestAllocationsBegin_nid_postfix();
    } catch (...) {
        --mutationDepth;
        throw;
    }
    activeMutation = mutation;
    return mutation;
}
// Previously every Kyty memory call (even a pure reservation) waited for GPU work on every tracked
// range. Only ranges whose host mapping or protection actually changes need that wait.
void PrepareRangeChange(std::uint64_t address, std::uint64_t bytes) {
    if (!activeMutation || !bytes) return;
    GuestAllocations::GuestAllocationsRequireUnpinned_nid_postfix(activeMutation, reinterpret_cast<void*>(address), static_cast<std::size_t>(bytes));
}
void EndMemoryChange(void* mutation) {
    if (!mutationDepth) throw std::logic_error("Native guest memory mutation depth underflow");
    if (--mutationDepth) return;
    activeMutation = nullptr;
    try {
        auto next = takeSnapshot.load(std::memory_order_acquire)();
        std::sort(next.begin(), next.end(), [](const auto& a, const auto& b) { return a.address < b.address; });
        std::uint64_t end = 0;
        for (const auto& item : next) {
            if (!item.address || !item.bytes || item.address < end || item.bytes > UINT64_MAX - item.address || (item.writable && !item.readable))
                throw std::runtime_error("Invalid native guest memory mapping snapshot");
            end = item.address + item.bytes;
        }
        // Both lists are sorted by address and non-overlapping: one linear merge instead of O(n^2).
        // Removals are applied before additions, as before, so a replaced range never overlaps.
        std::vector<const Mapping*> added;
        std::size_t i = 0, j = 0;
        while (i < tracked.size() || j < next.size()) {
            if (j == next.size() || (i < tracked.size() && tracked[i].address < next[j].address)) {
                unwatch(tracked[i]);
                GuestAllocations::GuestAllocationsRemove_nid_postfix(mutation, reinterpret_cast<void*>(tracked[i++].address));
            } else if (i == tracked.size() || next[j].address < tracked[i].address) {
                added.push_back(&next[j++]);
            } else if (tracked[i] == next[j]) {
                ++i; ++j;
            } else {
                unwatch(tracked[i]);
                GuestAllocations::GuestAllocationsRemove_nid_postfix(mutation, reinterpret_cast<void*>(tracked[i++].address));
                added.push_back(&next[j++]);
            }
        }
        for (const auto* item : added) {
            GuestAllocations::GuestAllocationsAdd_nid_postfix(mutation, reinterpret_cast<void*>(item->address), item->bytes, item->readable, item->writable, item->gpu);
            watch(*item);
        }
        tracked = std::move(next);
    } catch (...) {
        GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
        throw;
    }
    GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
}
bool WriteWatchFault(std::uint64_t address) {
#if defined(__ANDROID__)
    if (!watchActive.load(std::memory_order_acquire) || address >= IdentityGuestLimit) return false;
    return NovaAnyPS5WriteWatchFault(static_cast<std::uintptr_t>(address));
#else
    (void)address;
    return false;
#endif
}
void WriteWatchHostWrite(std::uint64_t address, std::uint64_t bytes) {
#if defined(__ANDROID__)
    if (!watchActive.load(std::memory_order_acquire) || bytes == 0 || address >= IdentityGuestLimit) return;
    NovaAnyPS5WriteWatchMarkWritten(static_cast<std::uintptr_t>(address), static_cast<std::size_t>(std::min(bytes, IdentityGuestLimit - address)));
#else
    (void)address;
    (void)bytes;
#endif
}
}
