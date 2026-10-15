#!/usr/bin/env python3
"""Bounded Luna mapping/APR correlation; no mapping, completion or return-code changes."""
from pathlib import Path
import sys
root = Path(sys.argv[1])
memory = root/'src/kernel/memory.cpp'
ampr = root/'src/libs/libAmpr.cpp'
m, a = memory.read_text(), ampr.read_text()
header = Path(__file__).with_name('novaLunaTrace.h').read_text()
if '/* NOVA_LUNA_BEGIN */' in m or '/* NOVA_LUNA_BEGIN */' in a:
    raise SystemExit('NOVA_LUNA_TRACE: already applied')
def once(s, old, new):
    if s.count(old) != 1:
        raise SystemExit(f'NOVA_LUNA_TRACE: anchor count {s.count(old)}: {old[:90]}')
    return s.replace(old, new, 1)
def instrument(s, old, added, before=False):
    tagged = '/* NOVA_LUNA_BEGIN */\n' + added + '\n/* NOVA_LUNA_END */'
    return once(s, old, tagged+'\n'+old if before else old+'\n'+tagged)

m = instrument(m, '#include "common/novaFex.h"', '#include "common/novaLunaTrace.h"')
start=m.index('int KYTY_SYSV_ABI KernelBatchMap2(')
end=m.index('\nint KYTY_SYSV_ABI KernelBatchMap(',start)
b=m[start:end]
b=instrument(b, '\t\tauto* entry = &entries[i];', '''
        if (NovaLunaTrace::Enabled()) {
            KernelBatchMapEntry snapshot {};
            GuestMemory::Read(&snapshot, reinterpret_cast<uint64_t>(entry), sizeof(snapshot));
            NovaMemTrace("BatchMap.before", reinterpret_cast<uint64_t>(snapshot.start), snapshot.length,
                snapshot.offset, (uint64_t(unsigned(snapshot.operation)) << 32) |
                    (uint64_t(snapshot.type) << 8) | snapshot.protection, 0, 0);
            NovaLunaTrace::Print(NovaLunaTrace::Kind::Batch,
                "before entries=%p index=%d/%d start=%p offset=0x%llx len=0x%llx op=%d prot=0x%x type=0x%x flags=0x%x",
                static_cast<void*>(entries), i, num_entries, snapshot.start,
                static_cast<unsigned long long>(snapshot.offset), static_cast<unsigned long long>(snapshot.length),
                snapshot.operation, unsigned(snapshot.protection), unsigned(snapshot.type), unsigned(flags));
        }''')
b=instrument(b, '\n\t\tif (result != OK) {', '''
        if (NovaLunaTrace::Enabled()) {
            KernelBatchMapEntry snapshot {};
            GuestMemory::Read(&snapshot, reinterpret_cast<uint64_t>(entry), sizeof(snapshot));
            NovaMemTrace("BatchMap.after", reinterpret_cast<uint64_t>(snapshot.start), snapshot.length,
                snapshot.offset, (uint64_t(unsigned(snapshot.operation)) << 32) |
                    (uint64_t(snapshot.type) << 8) | snapshot.protection, reinterpret_cast<uint64_t>(snapshot.start), result);
            NovaLunaTrace::Print(NovaLunaTrace::Kind::Batch,
                "after entries=%p index=%d start=%p offset=0x%llx len=0x%llx op=%d prot=0x%x type=0x%x result=0x%x processed=%d",
                static_cast<void*>(entries), i, snapshot.start,
                static_cast<unsigned long long>(snapshot.offset), static_cast<unsigned long long>(snapshot.length),
                snapshot.operation, unsigned(snapshot.protection), unsigned(snapshot.type), unsigned(result), processed);
        }''', before=True)
m=m[:start]+b+m[end:]
a=instrument(a, '#include "common/abi.h"', '#include "common/novaLunaTrace.h"')
a=instrument(a, '\t\t                                      command.size, &bytes_read);', '''
        NovaLunaTrace::Print(NovaLunaTrace::Kind::Read,
            "file=%u dst=0x%llx offset=0x%llx requested=%llu got=%llu result=0x%x",
            command.file_id, static_cast<unsigned long long>(command.destination),
            static_cast<unsigned long long>(command.file_offset), static_cast<unsigned long long>(command.size),
            static_cast<unsigned long long>(bytes_read), unsigned(result));''')
a=instrument(a, '\t\t    reinterpret_cast<void*>(command.data));', '''
        NovaLunaTrace::Print(NovaLunaTrace::Kind::Event,
            "eq=0x%llx ident=%d filter=%d data=0x%llx result=0x%x",
            static_cast<unsigned long long>(command.eq), command.id, LibKernel::EventQueue::KERNEL_EVFILT_AMPR,
            static_cast<unsigned long long>(command.data), unsigned(result));''')
a=instrument(a, '\t\t\t\tresult              = ExecuteCommand(command);', '''
                NovaLunaTrace::Print(NovaLunaTrace::Kind::Execute,
                    "submission=%u cursor=%zu record=0x%llx variant=%zu",
                    submission.id, submission.cursor - 1, static_cast<unsigned long long>(command.record_offset), command.data.index());''',before=True)
a=instrument(a, '\t\t\t\tAprShared::WriteResult(submission.result, result, error_offset);', '''
                NovaLunaTrace::Print(NovaLunaTrace::Kind::Complete,
                    "submission=%u result=0x%x error_offset=0x%x cursor=%zu commands=%zu",
                    submission.id, unsigned(result), error_offset, submission.cursor, submission.commands.size());''')
a=instrument(a, '\tconst uint32_t id = out_submission_id != nullptr ? AprShared::AllocateSubmissionId() : 0;', '''
    NovaLunaTrace::Print(NovaLunaTrace::Kind::Submit,
        "cb=0x%llx engine=%s submission=%u priority=%u commands=%zu bytes=%llu",
        static_cast<unsigned long long>(command_buffer), amm ? "AMM" : "APR", id, priority,
        state.commands.size(), static_cast<unsigned long long>(end));''')
# All anchors must succeed before any source is written.
memory.write_text(m)
ampr.write_text(a)
(root/'src/common/novaLunaTrace.h').write_text(header)
print('NOVA_LUNA_TRACE: bounded BatchMap and APR read/event/submit/execute/completion correlation')
