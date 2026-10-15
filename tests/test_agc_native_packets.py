#!/usr/bin/env python3
"""Run real AGC builders with protected guest mappings and native shared aliases.

Checks packet bytes, unchanged padding, returned guest pointers, cursor advances,
register reads, allocation failure, slot-crossing fallback, and callback identity.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
work = Path(sys.argv[1])
before = (repo/'vendor/kytyps5/src/libs/agc.cpp').read_text()
after = (work/'src/libs/agc.cpp').read_text()


def block(s, marker):
    a = s.index(marker)
    b = s.index('{', a)
    depth, end = 1, b+1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}')
        end += 1
    return s[a:end]


def function(s, name):
    match = re.search(r'^(?:static uint32_t\*|static uint32_t|uint32_t\* KYTY_SYSV_ABI) '+name+r'\(', s, re.M)
    return block(s, match[0])


names = ['AgcCbNop', 'AgcCbDispatch', 'AgcCbSetShRegisterRangeDirect',
         'AgcCbSetShRegistersDirect', 'AgcCbSetUcRegistersDirect',
         'AgcDcbSetShRegisterDirect', 'AgcDcbSetCxRegisterDirect', 'AgcDcbSetUcRegisterDirect',
         'AgcDcbSetIndexSize', 'AgcDcbSetIndexBuffer', 'AgcDcbSetIndexCount',
         'AgcDcbSetNumInstances', 'AgcDcbDrawIndex', 'AgcDcbDrawIndexMultiInstanced',
         'AgcDcbDrawIndexAuto', 'AgcDcbDrawIndexOffset', 'AgcDcbSetBaseIndirectArgs',
         'AgcDcbDispatchIndirect', 'AgcAcbCopyData', 'AgcAcbWriteData']

program = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
#include "common/guestMemory.h"
#define KYTY_SYSV_ABI
#define PRINT_NAME(...)
#define LOGF(...)
#define LOGF_COLOR(...)
#define AgcTrace(...)
#define EXIT_NOT_IMPLEMENTED(x) do{if(x)throw std::runtime_error("invalid");}while(0)
'''
pm4 = (work/'src/graphics/guest_gpu/pm4.h').read_text()
pm4 = re.sub(r'#include "common/(?:abi|common).h"', '', pm4)
program += pm4 + '\nnamespace Pm4=Libs::Graphics::Pm4;\n'
program += block(after, 'struct CommandBuffer {') + ';\n'
program += 'struct ShaderRegister {uint32_t offset,value;};\n'
program += function(after, 'decode_draw_index_initiator')
program += '\nnamespace baseline {\n'+'\n'.join(function(before,n) for n in names)+'\n}\n'
program += '\nnamespace fast {\n'+function(after,'allocate_guest_packet')+'\n'
program += '\n'.join(function(after,n) for n in names)+'\n}\n'
program += r'''
struct Mapping {uint64_t guest; void* host; size_t size;};
std::vector<Mapping> mappings;
namespace NovaFex {
bool GuestVAEnabled(){return true;}
uint64_t TranslateGuestVA(uint64_t a){
 for(auto m:mappings)if(a>=m.guest && a<m.guest+m.size)return (uint64_t)m.host+a-m.guest;
 return a;
}
}
void* shared(uint64_t guest,size_t size){
 char name[]="/tmp/nova-agc-XXXXXX";int fd=mkstemp(name);assert(fd>=0);unlink(name);
 assert(ftruncate(fd,size)==0);
 auto* g=mmap((void*)guest,size,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED_NOREPLACE,fd,0);
 auto* h=mmap(nullptr,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);
 assert(g==(void*)guest && h!=MAP_FAILED);mappings.push_back({guest,h,size});return h;
}
constexpr uint64_t object=0x9100100000ull, packet=0x9000100000ull, registers=0x9200100000ull;
CommandBuffer* native_object;
uint32_t* native_packet;
unsigned cases=0,grows=0;
bool grow(CommandBuffer* original,uint32_t words,void* user){
 assert(original==(CommandBuffer*)object && user==(void*)0x1234);++grows;
 original->cursor_up=(uint32_t*)packet;original->cursor_down=(uint32_t*)packet+128;
 return words<=128;
}
template<typename F>void verify(F f){
 std::array<uint32_t,256> expected;expected.fill(0xa5a5a5a5u);
 std::fill_n(native_packet,256,0xa5a5a5a5u);
 CommandBuffer low{};low.cursor_up=expected.data();low.cursor_down=expected.data()+128;
 *native_object=low;native_object->cursor_up=(uint32_t*)packet;native_object->cursor_down=(uint32_t*)packet+128;
 auto* a=f(&low,false);auto* b=f((CommandBuffer*)object,true);
 assert((a==nullptr)==(b==nullptr));
 if(a)assert((uint64_t)b==packet+4*(a-expected.data()));
 assert((uint64_t)native_object->cursor_up-packet==4*(low.cursor_up-expected.data()));
 assert(std::memcmp(expected.data(),native_packet,sizeof(expected))==0);++cases;
}
int main(){
 native_object=(CommandBuffer*)shared(object,4096);native_packet=(uint32_t*)shared(packet,4096);
 auto* native_regs=(ShaderRegister*)shared(registers,4096);
 assert(mprotect((void*)object,4096,PROT_NONE)==0);
 assert(mprotect((void*)packet,4096,PROT_NONE)==0);
 assert(mprotect((void*)registers,4096,PROT_NONE)==0);
 for(unsigned i=0;i<512;++i){
  std::array<ShaderRegister,32> regs;
  std::array<uint32_t,32> values;
  for(unsigned j=0;j<32;++j){regs[j]={j*(1u+(i&1)),i^j};native_regs[j]=regs[j];values[j]=i+j;}
  auto* reg_ptr=(const volatile ShaderRegister*)registers;
  auto n=1+(i%32);
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcCbNop(b,n):baseline::AgcCbNop(b,n);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcCbDispatch(b,i,i+1,i+2,i):baseline::AgcCbDispatch(b,i,i+1,i+2,i);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcCbSetShRegisterRangeDirect(b,i,values.data(),n):baseline::AgcCbSetShRegisterRangeDirect(b,i,values.data(),n);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcCbSetShRegistersDirect(b,reg_ptr,n):baseline::AgcCbSetShRegistersDirect(b,regs.data(),n);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcCbSetUcRegistersDirect(b,reg_ptr,n):baseline::AgcCbSetUcRegistersDirect(b,regs.data(),n);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetShRegisterDirect(b,regs[0]):baseline::AgcDcbSetShRegisterDirect(b,regs[0]);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetCxRegisterDirect(b,regs[0]):baseline::AgcDcbSetCxRegisterDirect(b,regs[0]);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetUcRegisterDirect(b,regs[0]):baseline::AgcDcbSetUcRegisterDirect(b,regs[0]);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetIndexSize(b,i&3,i&3):baseline::AgcDcbSetIndexSize(b,i&3,i&3);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetIndexBuffer(b,packet+i*4):baseline::AgcDcbSetIndexBuffer(b,packet+i*4);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetIndexCount(b,i):baseline::AgcDcbSetIndexCount(b,i);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetNumInstances(b,i):baseline::AgcDcbSetNumInstances(b,i);});
  auto* index=(const volatile void*)0x9300001000ull;
  uint64_t mod=i|(uint64_t(i&1)<<32);
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbDrawIndex(b,i,index,mod):baseline::AgcDcbDrawIndex(b,i,index,mod);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbDrawIndexMultiInstanced(b,i,index,index,i,mod):baseline::AgcDcbDrawIndexMultiInstanced(b,i,index,index,i,mod);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbDrawIndexAuto(b,i,mod):baseline::AgcDcbDrawIndexAuto(b,i,mod);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbDrawIndexOffset(b,i+1,i,mod):baseline::AgcDcbDrawIndexOffset(b,i+1,i,mod);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbSetBaseIndirectArgs(b,i&1,index):baseline::AgcDcbSetBaseIndirectArgs(b,i&1,index);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcDcbDispatchIndirect(b,i,i):baseline::AgcDcbDispatchIndirect(b,i,i);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcAcbCopyData(b,i,i,packet,i,i,0xfedcba9876543210ull+i,i,i):baseline::AgcAcbCopyData(b,i,i,packet,i,i,0xfedcba9876543210ull+i,i,i);});
  verify([&](CommandBuffer*b,bool x){return x?fast::AgcAcbWriteData(b,i&1,i&3,packet,values.data(),n,i&1,i&1):baseline::AgcAcbWriteData(b,i&1,i&3,packet,values.data(),n,i&1,i&1);});
 }
 // A grow callback sees the guest receiver, even when a native alias exists.
 assert(mprotect((void*)object,4096,PROT_READ|PROT_WRITE)==0);
 native_object->cursor_up=(uint32_t*)packet;native_object->cursor_down=(uint32_t*)packet;
 native_object->callback=grow;native_object->user_data=(void*)0x1234;native_object->reserved_dw=4;
 assert(fast::AgcCbNop((CommandBuffer*)object,8)==(uint32_t*)packet && grows==1);
 assert(native_object->cursor_up==(uint32_t*)packet+8);
 native_object->cursor_down=native_object->cursor_up;
 native_object->callback=nullptr;
 assert(fast::AgcCbNop((CommandBuffer*)object,8)==nullptr);
 assert(fast::AgcCbNop((CommandBuffer*)object,0)==nullptr);
 // A range spanning two slots must retain the original pointer (no false contiguous alias).
 assert(GuestMemory::Ptr((uint32_t*)(0x9400000000ull-4),8)==(uint32_t*)(0x9400000000ull-4));
 printf("AGC native packets: PASS (%u cases, protected guest memory, original callback receiver, allocation failure, slot fallback)\n",cases);
}
'''
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root/'common').mkdir()
    # Exercise the production translation helpers on the x86 CI host.
    header = (work/'src/common/novaFex.h').read_text().replace('#if defined(__aarch64__)', '#if 1')
    (root/'common/novaFex.h').write_text(header)
    (root/'common/guestMemory.h').write_text((work/'src/common/guestMemory.h').read_text())
    cpp, exe = root/'test.cpp', root/'test'
    cpp.write_text(program)
    subprocess.run(['g++','-std=c++20','-O2','-fno-builtin','-I'+str(root),
                    '-I'+str(repo/'native/novafex'),str(cpp),
                    str(repo/'native/novafex/guest_memory.cpp'),
                    '-Wl,--wrap=memcpy,--wrap=memset,--wrap=memmove,--wrap=memcmp',
                    '-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
