#include "runtime_fixture.hpp"
#include "prx/libSceAgcDriver/Submit/include/Acb.hpp"
#include "prx/libSceAgcDriver/Execution/include/Driver.hpp"
#include "prx/libc/include/Shutdown.hpp"
#include <array>
#include <atomic>
#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
namespace {
struct alignas(64) State { std::uint32_t label = 0, entered = 0, after = 0; };
void Check(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
std::array<std::uint32_t, 5> Write(std::uint32_t* pointer) {
    const auto address = reinterpret_cast<std::uintptr_t>(pointer);
    return {0xc0033700u, 0x00100200u, static_cast<std::uint32_t>(address), static_cast<std::uint32_t>(address >> 32), 1u};
}
std::vector<std::uint32_t> Commands(State& state, std::uint64_t labelAddress = 0) {
    const auto before = Write(&state.entered), after = Write(&state.after);
    const auto address = labelAddress ? labelAddress : reinterpret_cast<std::uintptr_t>(&state.label);
    std::vector<std::uint32_t> words(before.begin(), before.end());
    const std::array<std::uint32_t, 7> wait{0xc0053c00u, 0x13u, static_cast<std::uint32_t>(address), static_cast<std::uint32_t>(address >> 32), 1u, 0xffffffffu, 0x19u};
    words.insert(words.end(), wait.begin(), wait.end());
    words.insert(words.end(), after.begin(), after.end());
    return words;
}
void Reached(State& state) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (std::atomic_ref(state.entered).load(std::memory_order_acquire) != 1) {
        Check(std::chrono::steady_clock::now() < deadline, "real AGC queue did not reach its wait");
        std::this_thread::yield();
    }
}
}
int main() {
    try {
        NovaAnyTest::Configure();
        static State released, cancelled;
        constexpr std::uint64_t commandBoundary = 0xd000000000ull + (1ull << 30);
        constexpr std::uint64_t packetAddress = 0xe000001000ull;
        constexpr std::uint64_t labelAddress = 0xf000001000ull;
        NovaAnyTest::MapSynthetic(labelAddress, std::as_writable_bytes(std::span(&released.label, 1)));
        auto first = Commands(released, labelAddress);
        const auto firstBytes = std::as_writable_bytes(std::span(first));
        NovaAnyTest::MapSynthetic(commandBoundary - 16, firstBytes.first(16));
        NovaAnyTest::MapSynthetic(commandBoundary, firstBytes.subspan(16));
        Packet remote{reinterpret_cast<std::uint32_t*>(commandBoundary - 16), static_cast<std::uint32_t>(first.size()), 0, {}};
        NovaAnyTest::MapSynthetic(packetAddress, std::as_writable_bytes(std::span(&remote, 1)));
        Packet packet{};
        Check(sceAgcDriverSubmitAcb(0x20, reinterpret_cast<Packet*>(packetAddress)) == 0, "real AGC queue submission failed");
        Reached(released);
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        Check(std::atomic_ref(released.after).load() == 0, "unsatisfied GPU wait was bypassed");
        std::atomic_ref(released.label).store(1, std::memory_order_release);
        AgcDriverWaitIdle_nid_postfix();
        Check(released.after == 1, "satisfied queue did not execute its following command");
        auto second = Commands(cancelled);
        packet = {second.data(), static_cast<std::uint32_t>(second.size()), 0, {}};
        Check(sceAgcDriverSubmitAcb(0x28, &packet) == 0, "cancellation queue submission failed");
        Reached(cancelled);
        LibcRunShutdown_nid_postfix();
        Check(cancelled.label == 0 && cancelled.after == 0, "shutdown signalled an unsatisfied wait or executed its following command");
        LibcRunShutdown_nid_postfix();
        std::cout << "Real AGC queue ordering, satisfied waits and cancellation without fake labels passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
