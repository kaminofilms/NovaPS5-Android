#!/usr/bin/env python3
"""Use explicit guest reads and successful-map pointer/count write-back in BatchMap."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'src/kernel/memory.cpp'
s=p.read_text()
include='#include "common/guestMemory.h"'
if s.count(include)!=1:
    raise SystemExit('NOVA_BATCH_WRITEBACK: guest memory include anchor changed')
if '#include <cstddef>' not in s:
    s=s.replace(include, include+'\n#include <cstddef>',1)
start=s.index('int KYTY_SYSV_ABI KernelBatchMap2(')
end=s.index('\nint KYTY_SYSV_ABI KernelBatchMap(',start)
b=s[start:end]
if 'NOVA_BATCH_WRITEBACK' in b:
    raise SystemExit('NOVA_BATCH_WRITEBACK: already applied')
def once(old,new):
    global b
    if b.count(old)!=1:
        raise SystemExit(f'NOVA_BATCH_WRITEBACK: anchor count {b.count(old)}: {old[:80]}')
    b=b.replace(old,new,1)
once('\t\tauto* entry = &entries[i];', '''
        // NOVA_BATCH_WRITEBACK: keep guest addresses in the ABI; never publish host aliases.
        const uint64_t guest_entry = reinterpret_cast<uint64_t>(entries) +
                                     uint64_t(i) * sizeof(KernelBatchMapEntry);
        KernelBatchMapEntry local_entry {};
        GuestMemory::Read(&local_entry, guest_entry, sizeof(local_entry));
        auto* entry = &local_entry;''')
once('\t\t\tdefault: result = KERNEL_ERROR_EINVAL; break;\n\t\t}', '''\t\t\tdefault: result = KERNEL_ERROR_EINVAL; break;
\t\t}
        // Mapping implementations validate and return a guest VA through local_entry.start.
        // Only mapping operations own this output; failed maps, protect and unmap do not.
        if (result == OK && (entry->operation == MAP_OP_MAP_DIRECT ||
                             entry->operation == MAP_OP_MAP_FLEXIBLE)) {
            static_assert(offsetof(KernelBatchMapEntry, start) == 0);
            GuestMemory::Write(guest_entry, &entry->start, sizeof(entry->start));
            if (NovaLunaTrace::Enabled()) {
                void* observed = nullptr;
                GuestMemory::Read(&observed, guest_entry, sizeof(observed));
                NovaMemTrace("BatchMap.writeback", guest_entry, sizeof(observed),
                    reinterpret_cast<uint64_t>(entry->start), observed == entry->start,
                    reinterpret_cast<uint64_t>(observed), result);
                NovaLunaTrace::Print(NovaLunaTrace::Kind::Batch,
                    "writeback entry=0x%llx expected=%p observed=%p matches=%d",
                    static_cast<unsigned long long>(guest_entry), entry->start, observed, observed == entry->start);
            }
        }''')
old='*num_entries_out = processed;'
if b.count(old)!=2:
    raise SystemExit('NOVA_BATCH_WRITEBACK: processed-count anchors changed')
b=b.replace(old, 'GuestMemory::Write(reinterpret_cast<uint64_t>(num_entries_out), &processed, sizeof(processed));')
p.write_text(s[:start]+b+s[end:])
print('NOVA_BATCH_WRITEBACK: explicit guest entry reads, successful-map start writes and processed-count writes')
