#pragma once
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>
namespace NovaAnyPS5 {
inline int CreateMemoryFile(const char* name, unsigned flags) {
#if defined(__ANDROID__)
    return static_cast<int>(syscall(SYS_memfd_create, name, flags));
#else
    return memfd_create(name, flags);
#endif
}
}
