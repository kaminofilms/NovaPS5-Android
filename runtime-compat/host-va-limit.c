/* SPDX-License-Identifier: GPL-2.0-only
 * Freestanding Linux probe. No libc, Wine, or Android linker dependencies.
 * Probe the same host VA ceiling Wine uses before the Kyty process starts.
 */
typedef unsigned long u64;
#if defined(__aarch64__)
static long call6(long n, long a, long b, long c, long d, long e, long f) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a, x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c, x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e, x5 __asm__("x5") = f;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2),
                     "r"(x3), "r"(x4), "r"(x5) : "memory");
    return x0;
}
#define MMAP 222
#define MUNMAP 215
#define WRITE 64
#define EXIT 93
#elif defined(__x86_64__)
static long call6(long n, long a, long b, long c, long d, long e, long f) {
    register long r10 __asm__("r10") = d, r8 __asm__("r8") = e;
    register long r9 __asm__("r9") = f;
    long ret;
    __asm__ volatile("syscall" : "=a"(ret) : "a"(n), "D"(a), "S"(b),
                     "d"(c), "r"(r10), "r"(r8), "r"(r9) : "rcx", "r11", "memory");
    return ret;
}
#define MMAP 9
#define MUNMAP 11
#define WRITE 1
#define EXIT 60
#else
#error Unsupported probe architecture
#endif
#if defined(__x86_64__)
__attribute__((force_align_arg_pointer))
#endif
void _start(void) {
    u64 limit = 0;
    for (int bit = 62; bit >= 32; --bit) {
        u64 address = 1ul << bit;
        long ret = call6(MMAP, address, 4096, 0, 0x100022, -1, 0);
        if (ret == (long)address || ret == -17 /* EEXIST: address is valid */) {
            if (ret == (long)address) call6(MUNMAP, address, 4096, 0, 0, 0, 0);
            limit = (address << 1) - 0x10000;
            break;
        }
        if (ret > 0) call6(MUNMAP, ret, 4096, 0, 0, 0, 0);
    }
    if (!limit) { call6(EXIT, 70, 0, 0, 0, 0, 0); __builtin_unreachable(); }
    /* Wine's Windows user address limit can be lower than Linux's. */
    if (limit > 0x7fffffff0000ul) limit = 0x7fffffff0000ul;
    char out[19] = "0x0000000000000000\n";
    for (int i = 0; i < 16; ++i) out[17-i] = "0123456789abcdef"[(limit >> (i*4)) & 15];
    call6(WRITE, 1, (long)out, 19, 0, 0, 0);
    call6(EXIT, 0, 0, 0, 0, 0, 0);
    __builtin_unreachable();
}
