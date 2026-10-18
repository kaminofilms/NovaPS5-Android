#!/usr/bin/env python3
"""Execute production ARM64 thread-entry selection and native/guest create wrappers."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root=Path(sys.argv[1]);s=(root/'src/kernel/pthread.cpp').read_text()
start=s.index('static KYTY_SYSV_ABI void* RunOnGuestStack(')
fex=s.index('#elif defined(KYTY_NOVA_FEX)',start)
body=s[fex+len('#elif defined(KYTY_NOVA_FEX)'):s.index('\n#else',fex)]
wrapper=s[s.index('int KYTY_SYSV_ABI PthreadCreate(Pthread*'):s.index('int KYTY_SYSV_ABI PthreadDetach(Pthread')]
create=s[s.index('static int PthreadCreateImpl('):s.index('int KYTY_SYSV_ABI PthreadCreate(Pthread*')]
assert create.index('created_thread->native_entry    = native_entry;') < create.index('pthread_create(&created_thread->p')
assert 'thread->native_entry' in s[s.index('static void* RunThread('):s.index('static int PthreadCreateImpl(')]
assert 'bool                  native_entry = false;' in s
av=(root/'src/libs/avPlayer.cpp').read_text()
assert av.count('PthreadCreateNative(&created, nullptr, entry, this, name)')==1
assert 'PthreadCreate(&created' not in av
for name in ['AvPlayerVideoDecoder','AvPlayerAudioDecoder','AvPlayerDemuxer']:
    assert name in av
pre=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <csetjmp>
#include <atomic>
#include <thread>
#include <vector>
#define KYTY_SYSV_ABI
using pthread_entry_func_t=void*(*)(void*);
using Pthread=void*;using PthreadAttr=void*;
thread_local sigjmp_buf* g_nova_exit_point=nullptr;
thread_local void* g_nova_exit_value=nullptr;
namespace Loader {uintptr_t NovaGuestFsBase(){return 0x123400;}}
namespace NovaFex {
 thread_local uintptr_t stack=0,fs=0,last_guest=0;
 thread_local unsigned guest_calls=0,abandoned=0;
 constexpr uint64_t GuestEntry=0x900000010ull,GuestCallback=0x930000020ull,GuestExit=0x910000030ull;
 void SetThreadGuestStack(uintptr_t p){stack=p;}
 void SetThreadFsBase(uintptr_t p){fs=p;}
 void AbandonGuestCalls(){++abandoned;}
 uint64_t CallGuest(uint64_t entry,uint64_t arg){
  // Native machine code must NEVER be passed to this x86-64-only interface.
  assert(entry==GuestEntry||entry==GuestCallback||entry==GuestExit);
  assert(stack==0x10000&&fs==0x123400&&g_nova_exit_point);
  ++guest_calls;last_guest=entry;
  if(entry==GuestExit){g_nova_exit_value=reinterpret_cast<void*>(0x55);siglongjmp(*g_nova_exit_point,1);}
  return arg+1;
 }
}
void* RunOnGuestStack(void* arg,pthread_entry_func_t func,void* stack_top,bool native_entry){
'''
bridge=r'''
}
thread_local bool created_native=false;
int PthreadCreateImpl(Pthread* thread,const PthreadAttr*,pthread_entry_func_t,void*,const char*,bool native_entry){
 if(!thread)return -1;created_native=native_entry;*thread=reinterpret_cast<void*>(0x22);return 0;
}
'''
post=r'''
std::atomic<unsigned> native_calls{0};
void* NativeWorker(void* arg){
 assert(NovaFex::stack==0x10000&&NovaFex::fs==0x123400&&g_nova_exit_point);
 ++native_calls;
 // A native worker can still enter an actual guest callback through the bridge.
 return reinterpret_cast<void*>(NovaFex::CallGuest(NovaFex::GuestCallback,reinterpret_cast<uint64_t>(arg)));
}
void* NativeExit(void*){g_nova_exit_value=reinterpret_cast<void*>(0x66);siglongjmp(*g_nova_exit_point,1);}
void run(){
 Pthread thread{};void* arg=reinterpret_cast<void*>(0x40);void* top=reinterpret_cast<void*>(0x1000f);
 const auto guest=reinterpret_cast<pthread_entry_func_t>(NovaFex::GuestEntry);
 assert(PthreadCreate(&thread,nullptr,guest,arg,"game")==0&&!created_native);
 assert(RunOnGuestStack(arg,guest,top,created_native)==reinterpret_cast<void*>(0x41));
 assert(NovaFex::guest_calls==1&&NovaFex::last_guest==NovaFex::GuestEntry&&!g_nova_exit_point);
 assert(PthreadCreateNative(&thread,nullptr,NativeWorker,arg,"decoder")==0&&created_native);
 assert(RunOnGuestStack(arg,NativeWorker,top,created_native)==reinterpret_cast<void*>(0x41));
 assert(NovaFex::guest_calls==2&&NovaFex::last_guest==NovaFex::GuestCallback&&!g_nova_exit_point);
 // Reusing a thread slot through the guest API must reset native mode.
 assert(PthreadCreate(&thread,nullptr,guest,arg,"game-again")==0&&!created_native);
 assert(RunOnGuestStack(arg,guest,top,created_native)==reinterpret_cast<void*>(0x41));
 assert(NovaFex::guest_calls==3&&NovaFex::last_guest==NovaFex::GuestEntry);
 assert(RunOnGuestStack(nullptr,NativeExit,top,true)==reinterpret_cast<void*>(0x66));
 assert(!g_nova_exit_point&&NovaFex::abandoned==1);
 assert(RunOnGuestStack(nullptr,reinterpret_cast<pthread_entry_func_t>(NovaFex::GuestExit),top,false)==reinterpret_cast<void*>(0x55));
 assert(!g_nova_exit_point&&NovaFex::abandoned==2);
 assert(PthreadCreate(nullptr,nullptr,guest,arg,"bad")==-1);
}
int main(){
 std::vector<std::thread> threads;
 for(unsigned i=0;i<3;++i)threads.emplace_back(run);
 for(auto& thread:threads)thread.join();
 assert(native_calls==3);
 puts("NOVA_NATIVE_WORKER_TEST: native decoder entries never enter FEX; guest entries/callbacks, TLS/stack, reuse, exit unwinding and three workers PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);(p/'test.cpp').write_text(pre+body+bridge+wrapper+post)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
    subprocess.run(['c++','-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',*flags,str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,timeout=20)
