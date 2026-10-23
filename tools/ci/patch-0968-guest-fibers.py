#!/usr/bin/env python3
"""Install translated x86-64 fiber continuations without changing guest object ABI."""
from pathlib import Path
import shutil
import sys
repo=Path(__file__).resolve().parents[2]
root=Path(sys.argv[1]);p=root/'src/libs/libKernel.cpp';s=p.read_text()
def once(old,new):
    global s
    if s.count(old)!=1: raise SystemExit('NOVA_FIBER: source anchor changed: '+old[:90])
    s=s.replace(old,new,1)
once('#include <vector>', '#include <vector>\n#include <memory>\n#include <mutex>\n#include <unordered_map>\n#if defined(KYTY_NOVA_FEX)\n#include <sys/mman.h>\n#endif')
anchor='int32_t KYTY_SYSV_ABI FiberInitialize(FiberObject* fiber,'
once(anchor,'#include "common/guestfiber/NovaFiberImpl.inc"\n\n'+anchor)
# Reset sidecars only after the original public argument validation succeeds.
once('\tstd::memset(fiber, 0, sizeof(*fiber));','''#if defined(KYTY_NOVA_FEX)
    NovaFiberReset(fiber);
#endif
\tstd::memset(fiber, 0, sizeof(*fiber));''')
# Successful finalize owns the fiber permanently; its native sidecar can be released.
once('\treturn OK;\n}\n\nint32_t KYTY_SYSV_ABI FiberRun', '#if defined(KYTY_NOVA_FEX)\n    NovaFiberReset(fiber);\n#endif\n\treturn OK;\n}\n\nint32_t KYTY_SYSV_ABI FiberRun')
for name,call in [('FiberRun','NovaFiberRun(fiber, arg_on_run, arg_on_return)'),('FiberSwitch','NovaFiberSwitch(fiber, arg_on_run, arg_on_return)'),('FiberReturnToThread','NovaFiberReturn(arg_on_return, arg_on_run)')]:
    start=s.index('int32_t KYTY_SYSV_ABI '+name+'(')
    brace=s.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    old=s[start:end]
    new=old.replace('int32_t KYTY_SYSV_ABI','FiberResult KYTY_SYSV_ABI',1)
    b=new.index('{')+1
    new=new[:b]+'\n#if defined(KYTY_NOVA_FEX)\n    return '+call+';\n#else'+new[b:-1]+'#endif\n}'
    once(old,new)
once('} // namespace Fiber\n\nint chmod', '''} // namespace Fiber
#if defined(KYTY_NOVA_FEX)
uint64_t NovaFiberExportAddress(uint64_t address) {
    if (address == reinterpret_cast<uint64_t>(&Fiber::FiberRun) ||
        address == reinterpret_cast<uint64_t>(&Fiber::FiberSwitch) ||
        address == reinterpret_cast<uint64_t>(&Fiber::FiberReturnToThread))
        return Fiber::NovaFiberWrap(address);
    return 0;
}
#endif

int chmod''')
p.write_text(s)
p=root/'src/libs/libs.h';s=p.read_text();anchor='inline uint64_t NovaExportAddress(uint64_t address, Loader::SymbolType type) {'
assert s.count(anchor)==1
s=s.replace(anchor,'#if defined(KYTY_NOVA_FEX)\nuint64_t NovaFiberExportAddress(uint64_t address);\n#endif\n'+anchor)
anchor='\t\treturn NovaFex::MakeGate(reinterpret_cast<const void*>(address));';assert s.count(anchor)==1
s=s.replace(anchor,'\t\tif (auto fiber = NovaFiberExportAddress(address); fiber != 0) return fiber;\n'+anchor)
p.write_text(s)
shutil.copytree(repo/'native/guestfiber',root/'src/common/guestfiber',dirs_exist_ok=True)
print('NOVA_FIBER: translated guest continuation switching installed (Run/Switch/ReturnToThread)')
