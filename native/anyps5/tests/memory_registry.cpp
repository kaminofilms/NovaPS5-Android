#include "renderer/memory_registry.hpp"
#include "memory_mutation.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include <atomic>
#include <chrono>
#include <future>
#include <iostream>
#include <stdexcept>
#include <thread>
namespace {
std::vector<NovaAnyPS5::Mapping> mappings;
std::atomic<unsigned> snapshots{0};
std::vector<NovaAnyPS5::Mapping> Snapshot() { ++snapshots; return mappings; }
void Check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
}
int main() {
    using namespace NovaAnyPS5;
    using namespace std::chrono_literals;
    try {
        ConfigureMemoryRegistry(Snapshot);
        {
            MemoryChange outer;
            mappings = {{0x100000, 0x4000, true, true, true}};
            { MemoryChange nested; }
            Check(snapshots == 0, "nested memory mutation published early");
        }
        Check(snapshots == 1, "outer mutation did not publish one snapshot");
        auto held = GuestAllocations::GuestAllocationsAcquireAll_nid_postfix();
        Check(held.size() == 1 && held[0]->writable, "initial mapping was not registered");
        std::atomic<bool> entered{false}, completed{false};
        auto mutation = std::async(std::launch::async, [&] {
            entered.store(true);
            { MemoryChange change; mappings = {{0x100000, 0x2000, true, false, true}, {0x102000, 0x2000, true, true, true}}; }
            completed.store(true);
        });
        while (!entered.load()) std::this_thread::yield();
        std::this_thread::sleep_for(50ms);
        Check(!completed.load(), "mapping changed while a GPU memory lease was held");
        held.clear();
        Check(mutation.wait_for(2s) == std::future_status::ready, "mapping mutation did not resume after lease release");
        mutation.get();
        {
            auto changed = GuestAllocations::GuestAllocationsAcquireAll_nid_postfix();
            Check(changed.size() == 2 && !changed[0]->writable && changed[1]->writable, "split/protection mapping update was incorrect");
        }
        { MemoryChange change; mappings.clear(); }
        Check(GuestAllocations::GuestAllocationsAcquireAll_nid_postfix().empty(), "unmapped guest allocation remained in the renderer registry");
        DisableMemoryRegistry();
        std::cout << "Native mapping leases, nested mutations, splitting, protection and removal passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
