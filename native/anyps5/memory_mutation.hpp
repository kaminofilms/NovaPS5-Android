#pragma once
#include <cstdint>
namespace NovaAnyPS5 {
bool MemoryHooksReady();
void* BeginMemoryChange();
void EndMemoryChange(void* mutation);
// Called by Kyty right before it changes host mappings or protection of [address, address+bytes)
// inside a MemoryChange: waits for GPU work that still leases that range (and only that range).
void PrepareRangeChange(std::uint64_t address, std::uint64_t bytes);
// Android write watch (AnyPS5 backend), fed by Kyty's existing hooks: a write fault that Kyty's
// process-wide handler offers to Memory::HandleGpuFault, and Memory::InvalidateMemory before
// Kyty's own host code writes guest memory. Both return immediately until the watch is active.
bool WriteWatchFault(std::uint64_t address);
void WriteWatchHostWrite(std::uint64_t address, std::uint64_t bytes);
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
