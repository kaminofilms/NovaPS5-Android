#include "memory_registry.hpp"
#include "../memory_mutation.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include <algorithm>
#include <atomic>
#include <mutex>
#include <stdexcept>
namespace NovaAnyPS5 {
namespace {
std::atomic<MappingSnapshot> takeSnapshot{nullptr};
std::atomic<bool> ready{false};
std::vector<Mapping> tracked;
thread_local std::uint32_t mutationDepth = 0;
thread_local void* activeMutation = nullptr;
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
                GuestAllocations::GuestAllocationsRemove_nid_postfix(mutation, reinterpret_cast<void*>(tracked[i++].address));
            } else if (i == tracked.size() || next[j].address < tracked[i].address) {
                added.push_back(&next[j++]);
            } else if (tracked[i] == next[j]) {
                ++i; ++j;
            } else {
                GuestAllocations::GuestAllocationsRemove_nid_postfix(mutation, reinterpret_cast<void*>(tracked[i++].address));
                added.push_back(&next[j++]);
            }
        }
        for (const auto* item : added)
            GuestAllocations::GuestAllocationsAdd_nid_postfix(mutation, reinterpret_cast<void*>(item->address), item->bytes, item->readable, item->writable, item->gpu);
        tracked = std::move(next);
    } catch (...) {
        GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
        throw;
    }
    GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
}
}
