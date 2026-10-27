#pragma once
#include <cstdint>
namespace NovaAnyPS5 {
bool MemoryHooksReady();
void* BeginMemoryChange();
void EndMemoryChange(void* mutation);
// Called by Kyty right before it changes host mappings or protection of [address, address+bytes)
// inside a MemoryChange: waits for GPU work that still leases that range (and only that range).
void PrepareRangeChange(std::uint64_t address, std::uint64_t bytes);
class MemoryChange {
public:
    MemoryChange() : active(MemoryHooksReady()), mutation(active ? BeginMemoryChange() : nullptr) {}
    ~MemoryChange() noexcept(false) { if (active) EndMemoryChange(mutation); }
    MemoryChange(const MemoryChange&) = delete;
    MemoryChange& operator=(const MemoryChange&) = delete;
private:
    bool active;
    void* mutation;
};
}
