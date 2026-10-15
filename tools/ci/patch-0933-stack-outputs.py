#!/usr/bin/env python3
"""Initialize unknown-stack outputs and access guest outputs through bounded views."""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/kernel/memory.cpp'
s = p.read_text()
def once(a, b):
    global s
    if s.count(a) != 1:
        raise SystemExit(f'NOVA_STACK_OUTPUTS: expected one anchor: {a[:90]}')
    s = s.replace(a, b, 1)

once('#include "common/novaFex.h"', '#include "common/novaFex.h"\n#include "common/guestMemory.h"')
once('int KYTY_SYSV_ABI KernelIsStack(void* addr, void** start, void** end) {',
     '''int KYTY_SYSV_ABI KernelIsStack(void* addr, void** start, void** end) {
    // Outputs belong to the guest. Keep addr in guest VA for the range query.
    if (start != nullptr) start = GuestMemory::Ptr(start, sizeof(*start));
    if (end != nullptr) end = GuestMemory::Ptr(end, sizeof(*end));''')
start = s.index('static int KYTY_SYSV_ABI KernelIsStackNovaT(void* addr, void** start, void** end) {')
end = s.index('\n}', start) + 2
body = s[start:end]
old = '''\tif (!g_virtual_ranges->Query(vaddr, 0, &candidate)) {
\t\treturn KERNEL_ERROR_EACCES;
\t}'''
new = '''\tif (!g_virtual_ranges->Query(vaddr, 0, &candidate)) {
        // Never expose stale caller stack values to libc's VM allocator.
        // Preserve Kyty's error result and successful stack-range semantics.
        if (start != nullptr) *start = nullptr;
        if (end != nullptr) *end = nullptr;
\t\treturn KERNEL_ERROR_EACCES;
\t}'''
if body.count(old) != 1:
    raise SystemExit('NOVA_STACK_OUTPUTS: unknown-range anchor changed')
s = s[:start] + body.replace(old, new, 1) + s[end:]
p.write_text(s)
print('NOVA_STACK_OUTPUTS: guest views and initialized failure outputs; return codes preserved')
