#pragma once
#include <cstdint>
namespace NovaAnyPS5 {
bool MemoryHooksReady();
void* BeginMemoryChange();
void EndMemoryChange(void* mutation);
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
