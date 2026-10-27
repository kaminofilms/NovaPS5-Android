#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
struct KernelEqueueEvent;
namespace NovaAnyPS5 {
struct MemoryRun {
    std::uint64_t begin;
    std::uint64_t end;
    bool readable;
    bool writable;
};
struct HostServices {
    void (*copy)(void*, const void*, std::size_t);
    int (*compare)(const void*, const void*, std::size_t);
    void* (*translate)(std::uint64_t, std::size_t, std::size_t*);
    bool (*query)(std::uint64_t, MemoryRun*);
    std::shared_ptr<void> (*pinQueue)(std::int64_t);
    int (*addEvent)(std::int64_t, const KernelEqueueEvent&);
    int (*deleteEvent)(std::int64_t, std::uintptr_t, std::int16_t);
    int (*triggerEvent)(std::int64_t, std::uintptr_t, std::int16_t, void*);
    void* (*map)(void*, std::size_t, int, int, int, std::int64_t) noexcept;
    bool (*sharedBacking)(std::uintptr_t, std::size_t, int*, std::uint64_t*);
    bool (*writeBacking)(std::uintptr_t, const void*, std::size_t);
    // Maps the PS5 AGC driver block at its fixed guest address through Nova's kernel memory.
    void* (*driverMemory)(std::uint64_t, std::size_t);
};
void ConfigureHostServices(const HostServices& services);
const HostServices& Services();
void CopyMemory(void* destination, const void* source, std::size_t bytes);
int CompareMemory(const void* left, const void* right, std::size_t bytes);
void* ContiguousMemory(std::uint64_t address, std::size_t bytes);
void ShutdownRuntime();
}
