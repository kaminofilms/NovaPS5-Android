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
        for (const auto& range : tracked)
            GuestAllocations::GuestAllocationsRequireUnpinned_nid_postfix(mutation, reinterpret_cast<void*>(range.address), range.bytes);
    } catch (...) {
        if (mutation) GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
        --mutationDepth;
        throw;
    }
    return mutation;
}
void EndMemoryChange(void* mutation) {
    if (!mutationDepth) throw std::logic_error("Native guest memory mutation depth underflow");
    if (--mutationDepth) return;
    try {
        auto next = takeSnapshot.load(std::memory_order_acquire)();
        std::sort(next.begin(), next.end(), [](const auto& a, const auto& b) { return a.address < b.address; });
        std::uint64_t end = 0;
        for (const auto& item : next) {
            if (!item.address || !item.bytes || item.address < end || item.bytes > UINT64_MAX - item.address || (item.writable && !item.readable))
                throw std::runtime_error("Invalid native guest memory mapping snapshot");
            end = item.address + item.bytes;
        }
        for (const auto& old : tracked)
            if (std::find(next.begin(), next.end(), old) == next.end())
                GuestAllocations::GuestAllocationsRemove_nid_postfix(mutation, reinterpret_cast<void*>(old.address));
        for (const auto& item : next)
            if (std::find(tracked.begin(), tracked.end(), item) == tracked.end())
                GuestAllocations::GuestAllocationsAdd_nid_postfix(mutation, reinterpret_cast<void*>(item.address), item.bytes, item.readable, item.writable, item.gpu);
        tracked = std::move(next);
    } catch (...) {
        GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
        throw;
    }
    GuestAllocations::GuestAllocationsEnd_nid_postfix(mutation);
}
}
