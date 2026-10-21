#!/usr/bin/env python3
"""0.9.57: structure of the guest exit report (both guest exit entry points)."""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src'
libc = (src / 'libs/libC.cpp').read_text()
lk = (src / 'libs/libKernel.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


rep = between(libc, 'void NovaReportGuestExit(const char* who, int code) {', '\n[[noreturn]] static KYTY_SYSV_ABI void abort(')
for needle in ['reported.exchange(true)', 'NovaFex::GetGuestCallContext(&g)', 'guest RIP %s', 'where(g.rip)',
               'NOVA_GUEST_EXIT: stack[%03d] %s', 'text%s', 'NovaFex::DumpRecentHostCalls("NOVA_GUEST_EXIT:")',
               'NovaDumpMemoryTrace()', 'std::fflush(stderr)']:
    assert needle in rep, needle
for body, who in [(between(libc, 'static KYTY_SYSV_ABI void exit(int code) {', '\n}'), '"libc exit"'),
                  (between(lk, 'static void KYTY_SYSV_ABI exit(int code) {', '\n}'), '"libkernel exit"')]:
    assert body.index('NovaReportGuestExit(' + who) < body.index('::exit(code);'), who
assert 'void         NovaReportGuestExit(const char* who, int code);' in lk
print('NOVA_0957_EXIT_REPORT: PASS')
