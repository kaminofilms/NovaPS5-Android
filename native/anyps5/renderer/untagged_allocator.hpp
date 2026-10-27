#pragma once
#include <sys/mman.h>
#include <cstddef>
#include <new>
namespace NovaAnyPS5 {
// Android heap pointers carry a top-byte tag (TBI). Memory whose address is encoded into GPU
// registers (48-bit program addresses) must come from untagged pages instead.
template <class T>
struct UntaggedAllocator {
    using value_type = T;
    UntaggedAllocator() = default;
    template <class U> UntaggedAllocator(const UntaggedAllocator<U>&) noexcept {}
    T* allocate(std::size_t count) {
        if (count == 0) count = 1;
        void* memory = mmap(nullptr, count * sizeof(T), PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (memory == MAP_FAILED) throw std::bad_alloc();
        return static_cast<T*>(memory);
    }
    void deallocate(T* pointer, std::size_t count) noexcept { munmap(pointer, (count ? count : 1) * sizeof(T)); }
    template <class U> bool operator==(const UntaggedAllocator<U>&) const noexcept { return true; }
};
}
