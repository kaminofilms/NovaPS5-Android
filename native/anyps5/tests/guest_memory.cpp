#include "runtime_fixture.hpp"
#include "renderer/host_services.hpp"
#include "prx/libSceAgcDriver/Execution/include/GuestMemory.hpp"
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
namespace { void Check(bool value, const char* message) { if (!value) throw std::runtime_error(message); } }
int main() {
    try {
        NovaAnyTest::Configure();
        constexpr std::uint64_t boundary = 0xa000000000ull + (1ull << 30);
        alignas(16) std::array<std::byte, 8> first{}, second{};
        first.fill(std::byte{0x11}); second.fill(std::byte{0x11});
        NovaAnyTest::MapSynthetic(boundary - 8, first);
        NovaAnyTest::MapSynthetic(boundary, second);
        Check(NovaAnyPS5::ContiguousMemory(boundary - 8, 16) == nullptr, "noncontiguous guest slots were accepted for Vulkan host import");
        Check(NovaAnyPS5::ContiguousMemory(boundary - 8, 8) == first.data(), "contiguous guest span did not translate");
        std::array<std::byte, 16> original{}, current{}, readback{};
        original.fill(std::byte{0x11}); current = original;
        current[3] = std::byte{0x99}; current[10] = std::byte{0x77};
        first[4] = std::byte{0xab};
        AgcDriver::GuestMemory::WriteChanged(boundary - 8, current, original);
        AgcDriver::GuestMemory::Read(boundary - 8, readback, 1);
        Check(readback[3] == std::byte{0x99} && readback[10] == std::byte{0x77}, "changed-byte write-back failed across guest slots");
        Check(readback[4] == std::byte{0xab}, "write-back overwrote an independently changed byte");
        constexpr std::uint64_t label = 0x12345678abcdef01ull;
        AgcDriverStoreGuestLabel_nid_postfix(reinterpret_cast<std::uint64_t*>(boundary - 8), label);
        std::uint64_t actual = 0; std::memcpy(&actual, first.data(), sizeof(actual));
        Check(actual == label, "GPU label release store did not target translated host memory");
        bool rejected = false;
        try { AgcDriver::GuestMemory::CheckRange(reinterpret_cast<void*>(UINT64_MAX - 3), 8, 1, true); }
        catch (const std::exception&) { rejected = true; }
        Check(rejected, "overflowing guest range was accepted");
        std::cout << "Cross-slot copies, changed-byte preservation, atomic labels and host-import translation passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
