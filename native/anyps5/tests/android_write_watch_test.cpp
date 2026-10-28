// Host check of the Android page-protection GuestWriteWatch backend (built with -D__ANDROID__ on
// Linux; it only uses mprotect and pthreads). The SIGSEGV handler stands in for Kyty's
// KytyExceptionHandler -> Memory::HandleGpuFault -> NovaAnyPS5::WriteWatchFault path.
#include <cerrno>
#include "prx/libc/include/GuestWriteWatch.hpp"
#include <csignal>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>
using namespace GuestWriteWatch;
extern "C" bool NovaAnyPS5WriteWatchFault(std::uintptr_t);
extern "C" void NovaAnyPS5WriteWatchMarkWritten(std::uintptr_t, std::size_t);
static int faults = 0;
static void handler(int, siginfo_t* info, void*) {  // stands in for Kyty's KytyExceptionHandler
    ++faults;
    if (!NovaAnyPS5WriteWatchFault(reinterpret_cast<std::uintptr_t>(info->si_addr))) { std::puts("FAIL: unclaimed fault"); _exit(3); }
}
static std::vector<std::pair<uintptr_t, uintptr_t>> got;
static void cb(void*, uintptr_t b, uintptr_t e) { got.emplace_back(b, e); }
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)
int main() {
    struct sigaction sa{}; sa.sa_sigaction = handler; sa.sa_flags = SA_SIGINFO; sigaction(SIGSEGV, &sa, nullptr);
    const size_t pg = getpagesize(), n = 16;
    auto* m = static_cast<char*>(mmap(nullptr, pg * n, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    auto a = reinterpret_cast<uintptr_t>(m);
    CHECK(GuestWriteWatchAvailable_nid_postfix());
    GuestWriteWatchRegister_nid_postfix(m, pg * n);
    CHECK(GuestWriteWatchCovers_nid_postfix(a, pg * n));
    got.clear(); CHECK(GuestWriteWatchCollect_nid_postfix(a, pg * n, cb, nullptr));
    CHECK(got.size() == 1 && got[0].first == a && got[0].second == a + pg * n);  // initially all written
    got.clear(); CHECK(GuestWriteWatchCollect_nid_postfix(a, pg * n, cb, nullptr)); CHECK(got.empty());  // now armed
    m[3 * pg + 5] = 1; m[3 * pg + 9] = 2; m[7 * pg] = 3;  // guest writes: fault once per page
    CHECK(faults == 2);
    got.clear(); CHECK(GuestWriteWatchCollect_nid_postfix(a, pg * n, cb, nullptr));
    CHECK(got.size() == 2 && got[0].first == a + 3 * pg && got[1].first == a + 7 * pg);
    // Kyty host write (InvalidateMemory before a kernel read()): must not EFAULT, must be reported.
    NovaAnyPS5WriteWatchMarkWritten(a + 10 * pg + 100, 2 * pg);
    int fd = open("/proc/self/exe", O_RDONLY);
    { auto r = read(fd, m + 10 * pg + 100, 2 * pg); if (r != (ssize_t)(2 * pg)) std::printf("read=%zd errno=%s\n", r, strerror(errno)); CHECK(r == (ssize_t)(2 * pg)); }
    close(fd);
    CHECK(faults == 2);
    got.clear(); CHECK(GuestWriteWatchCollect_nid_postfix(a, pg * n, cb, nullptr));
    CHECK(got.size() == 1 && got[0].first == a + 10 * pg && got[0].second == a + 13 * pg);
    // Fault outside any watched range is not claimed.
    CHECK(!NovaAnyPS5WriteWatchFault(a + pg * n + pg * 1000));
    // Unregister restores write access.
    CHECK(GuestWriteWatchUnregister_nid_postfix(m, pg * n));
    m[0] = 9; m[5 * pg] = 9; CHECK(faults == 2);
    std::puts("android write watch: all checks passed");
}
