#!/usr/bin/env python3
"""Keep native decoder worker entry points out of the guest x86-64 JIT."""
from pathlib import Path
import sys

root=Path(sys.argv[1])
changes={}
def edit(path,old,new):
    text=changes.get(path,(root/path).read_text())
    if text.count(old)!=1:
        raise SystemExit('NOVA_NATIVE_WORKER: changed anchor '+path)
    changes[path]=text.replace(old,new,1)

p='src/kernel/pthread.cpp'
edit(p,'\tpthread_entry_func_t  entry;','\tpthread_entry_func_t  entry;\n\tbool                  native_entry = false;')
edit(p,'static KYTY_SYSV_ABI void* RunOnGuestStack(void* arg, pthread_entry_func_t func, void* stack_top) {',
     'static KYTY_SYSV_ABI void* RunOnGuestStack(void* arg, pthread_entry_func_t func, void* stack_top, bool native_entry) {\n\t(void)native_entry;')
edit(p,'\tconst auto ret = NovaFex::CallGuest(reinterpret_cast<uint64_t>(func), reinterpret_cast<uint64_t>(arg));',
     '''	// Internal C++ worker entries are ARM64 host code, not guest x86-64.
	// Keep guest stack/FS and exit setup above: native workers may call back
	// into guest code, which must still enter NovaFEX through its normal bridge.
	const auto ret = native_entry ? reinterpret_cast<uint64_t>(func(arg))
	                             : NovaFex::CallGuest(reinterpret_cast<uint64_t>(func), reinterpret_cast<uint64_t>(arg));''')
edit(p,'\tret = RunOnGuestStack(thread->arg, thread->entry, stack_top);',
     '\tret = RunOnGuestStack(thread->arg, thread->entry, stack_top, thread->native_entry);')
edit(p,'''int KYTY_SYSV_ABI PthreadCreate(Pthread* thread, const PthreadAttr* attr,
                                pthread_entry_func_t entry, void* arg, const char* name) {''',
     '''static int PthreadCreateImpl(Pthread* thread, const PthreadAttr* attr,
                             pthread_entry_func_t entry, void* arg, const char* name, bool native_entry) {''')
edit(p,'\t\tcreated_thread->entry           = entry;',
     '\t\tcreated_thread->entry           = entry;\n\t\tcreated_thread->native_entry    = native_entry;')
wrappers='''int KYTY_SYSV_ABI PthreadCreate(Pthread* thread, const PthreadAttr* attr,
                                pthread_entry_func_t entry, void* arg, const char* name) {
    return PthreadCreateImpl(thread, attr, entry, arg, name, false);
}

// Internal host API only; never registered as a guest import.
int PthreadCreateNative(Pthread* thread, const PthreadAttr* attr,
                        pthread_entry_func_t entry, void* arg, const char* name) {
    return PthreadCreateImpl(thread, attr, entry, arg, name, true);
}

'''
edit(p,'int KYTY_SYSV_ABI PthreadDetach(Pthread thread) {',wrappers+'int KYTY_SYSV_ABI PthreadDetach(Pthread thread) {')
edit('src/kernel/pthread.h','int KYTY_SYSV_ABI     PthreadDetach(Pthread thread);',
     'int                  PthreadCreateNative(Pthread* thread, const PthreadAttr* attr,\n                                          pthread_entry_func_t entry, void* arg, const char* name);\nint KYTY_SYSV_ABI     PthreadDetach(Pthread thread);')
edit('src/libs/avPlayer.cpp','LibKernel::PthreadCreate(&created, nullptr, entry, this, name)',
     'LibKernel::PthreadCreateNative(&created, nullptr, entry, this, name)')
for path,text in changes.items():
    (root/path).write_text(text)
print('NOVA_NATIVE_WORKER: explicit AvPlayer native entries; guest pthreads retain NovaFEX; TLS/stack/cleanup/join retained')
