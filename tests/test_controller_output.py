#!/usr/bin/env python3
"""Compile the actual packet initializer and guest copy helpers, without SDL/FEX."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
source = (root / 'src/libs/controller.cpp').read_text()
start = source.index('static void pad_fill_data(')
end = source.index('\n}\n', start) + 2
body = source[start:end]
assert 'NOVA_CONTROLLER_OUTPUT' in body
# Recover the original initializer for byte-for-byte differential comparison.
legacy = body.replace('pad_fill_data(', 'legacy_fill(')
a = legacy.index('\n\t// NOVA_CONTROLLER_OUTPUT')
b = legacy.index('\n\tstd::memset', a)
legacy = legacy[:a] + '\n' + legacy[b:]
a = legacy.index('\n\t// Copy also handles')
legacy = legacy[:a] + '\n}'
axis = (root / 'src/libs/controller.h').read_text().split('enum class Axis {', 1)[1].split('};', 1)[0]
state = source.split('struct ControllerState {', 1)[1].split('\nclass GameController', 1)[0]
state = 'struct ControllerState {' + state
pad = (root / 'src/libs/padData.h').read_text().split('namespace Libs::Controller {', 1)[1].split('} // namespace', 1)[0]
nova = (root / 'src/common/novaFex.h').read_text().split('namespace NovaGuest {', 1)[1].split('} // namespace NovaGuest', 1)[0]
guest = (root / 'src/common/guestMemory.h').read_text().split('namespace GuestMemory {', 1)[1].split('} // namespace GuestMemory', 1)[0]
program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#define KYTY_NOVA_FEX 1
#define EXIT_IF(x) do { if (x) std::abort(); } while (false)
constexpr uint64_t boundary = 0x9040000000ull;
uint8_t *left_page, *right_page;
size_t page_size;
unsigned translated_destinations = 0;
bool right_mapped = true;
namespace NovaFex {
uint64_t TranslateGuestVA(uint64_t a) {
    if (a >= boundary - page_size && a < boundary) {
        ++translated_destinations;
        return reinterpret_cast<uint64_t>(left_page + page_size) - (boundary - a);
    }
    if (a >= boundary && a < boundary + page_size && right_mapped) {
        ++translated_destinations;
        return reinterpret_cast<uint64_t>(right_page) + a - boundary;
    }
    return a;
}
}
namespace NovaGuest {
''' + nova + '\n}\nnamespace GuestMemory {\n' + guest + '\n}\n' + pad + '\nenum class Axis {' + axis + '};\n' + state + '\n' + legacy + '\n' + body + r'''
int main() {
    page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    left_page = static_cast<uint8_t*>(mmap(nullptr, page_size, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
    right_page = static_cast<uint8_t*>(mmap(nullptr, page_size, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
    assert(left_page != MAP_FAILED && right_page != MAP_FAILED);
    unsigned cases = 0;
    for (unsigned variant = 0; variant != 6; ++variant) {
        ControllerState s;
        s.time = 0xfedcba9876543210ull + variant;
        s.buttons = 0xabcdef00 | variant;
        for (int i = 0; i != 6; ++i) s.axes[i] = (i*47 + variant) & 255;
        s.accel = {-1.25f,2.5f,3.0f}; s.gyro = {4.0f,-5.5f,6.0f};
        s.orientation = {0.25f,0.5f,-0.75f,1.0f};
        s.touch[0] = {7, variant % 3 != 0, 1920, 1080};
        s.touch[1] = {9, variant % 3 == 2, 123, 456};
        const bool connected = (variant & 1) != 0;
        const int count = variant == 5 ? 300 : static_cast<int>(variant);
        PadData expected, direct;
        std::memset(&expected,0xa5,sizeof(expected));
        std::memset(&direct,0x5a,sizeof(direct));
        legacy_fill(&expected,s,connected,count);
        pad_fill_data(&direct,s,connected,count);
        assert(std::memcmp(&expected,&direct,sizeof(expected)) == 0);
        for (unsigned remaining = 0; remaining <= sizeof(PadData); ++remaining) {
            std::memset(left_page,0xcc,page_size); std::memset(right_page,0xcc,page_size);
            translated_destinations = 0;
            const uint64_t address = boundary - remaining;
            pad_fill_data(reinterpret_cast<PadData*>(address),s,connected,count);
            const unsigned want_pieces = remaining && remaining < sizeof(PadData) ? 2 : 1;
            assert(translated_destinations == want_pieces);
            for (unsigned i = 0; i != sizeof(expected); ++i) {
                const uint64_t a = address + i;
                const uint8_t got = a < boundary ? left_page[page_size - (boundary-a)] : right_page[a-boundary];
                assert(got == reinterpret_cast<uint8_t*>(&expected)[i]);
            }
            if (remaining) assert(left_page[page_size-remaining-1] == 0xcc);
            assert(right_page[sizeof(PadData)-remaining] == 0xcc);
            ++cases;
        }
    }
    for (unsigned unmapped = 0; unmapped != 2; ++unmapped) {
        int errors[2]; assert(pipe(errors) == 0);
        const pid_t pid = fork(); assert(pid >= 0);
        if (pid == 0) {
            close(errors[0]); assert(dup2(errors[1],2) == 2); close(errors[1]);
            signal(SIGSEGV, SIG_DFL);
            if (unmapped) right_mapped = false;
            else if (mprotect(right_page,page_size,PROT_NONE)) _exit(2);
            ControllerState s;
            pad_fill_data(reinterpret_cast<PadData*>(boundary-13),s,true,1);
            _exit(3);
        }
        close(errors[1]);
        char report[8192] {}; size_t used = 0;
        for (;;) {
            char piece[1024]; const ssize_t n = read(errors[0],piece,sizeof(piece));
            if (n <= 0) break;
            const size_t keep = std::min(static_cast<size_t>(n),sizeof(report)-1-used);
            std::memcpy(report+used,piece,keep); used += keep;
        }
        close(errors[0]);
        int status = 0; assert(waitpid(pid,&status,0) == pid);
        bool faulted = WIFSIGNALED(status) && WTERMSIG(status) == SIGSEGV;
#if defined(NOVA_TEST_SANITIZED)
        // ASan intercepts memcpy to this unmapped address in its shadow gap before
        // the CPU store executes. Require that exact report, not any sanitizer exit.
        if (unmapped && WIFEXITED(status) && WEXITSTATUS(status) == 1)
            faulted = std::strstr(report,"AddressSanitizer: unknown-crash") &&
                      std::strstr(report,"WRITE of size 107 at 0x009040000000");
#endif
        if (!faulted) std::fprintf(stderr,"unexpected negative-case status=%d: %s",status,report);
        assert(faulted);
    }
    munmap(left_page,page_size); munmap(right_page,page_size);
    printf("NOVA_CONTROLLER_OUTPUT: PASS %u packet comparisons, 119 split alignments, padding, sensors, touches, bounded translation and genuine faults\n", cases);
}
'''
with tempfile.TemporaryDirectory() as d:
    cpp = Path(d) / 'test.cpp'
    binary = Path(d) / 'test'
    cpp.write_text(program)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-DNOVA_TEST_SANITIZED=1'] if os.environ.get('SANITIZE') else []
    subprocess.run(['g++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', *flags, str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
