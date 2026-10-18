#pragma once
#include "host_services.hpp"
#include <atomic>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <vector>
namespace NovaAnyPS5 {
template<typename T>
std::atomic_ref<T> Atomic(T& value) {
    auto* host = static_cast<T*>(ContiguousMemory(reinterpret_cast<std::uintptr_t>(&value), sizeof(T)));
    if (!host || reinterpret_cast<std::uintptr_t>(host) % std::atomic_ref<T>::required_alignment)
        throw std::runtime_error("AnyPS5 atomic guest access is not aligned and contiguous in host memory");
    return std::atomic_ref<T>(*host);
}
template<typename T, typename Address>
T ReadVolatile(Address address) {
    auto* host = static_cast<const volatile T*>(ContiguousMemory((std::uintptr_t)address, sizeof(T)));
    if (!host || (std::uintptr_t)host % alignof(T)) throw std::runtime_error("AnyPS5 volatile guest access is not aligned and contiguous");
    return *host;
}
template<typename T>
class TranslatedRead {
public:
    TranslatedRead(const T* guest, std::size_t count) {
        if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) throw std::overflow_error("AnyPS5 translated span overflow");
        const auto bytes = count * sizeof(T);
        const auto* host = static_cast<const T*>(ContiguousMemory(reinterpret_cast<std::uintptr_t>(guest), bytes));
        if (host) view = {host, count};
        else {
            copy.resize(count);
            CopyMemory(copy.data(), guest, bytes);
            view = copy;
        }
    }
    const T* Data() const { return view.data(); }
private:
    std::vector<T> copy;
    std::span<const T> view;
};
}
