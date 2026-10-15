#!/usr/bin/env python3
"""Compare compiled copy/wait builders against the vendored reference packets.

The fast builders write to inaccessible synthetic guest addresses through the real
bulk-memory wrapper, including packets split across noncontiguous 1 GiB slots.
"""
from pathlib import Path
import subprocess
import re
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]) / 'src/libs/agc.cpp'
reference = (repo / 'vendor/kytyps5/src/libs/agc.cpp').read_text()
patched = source.read_text()


def function(s, name):
    a = re.search(r'^(?:static uint32_t|static void|uint32_t\* KYTY_SYSV_ABI) ' + name + r'\(', s, re.M).start()
    b = s.index('{', a)
    depth, end = 1, b + 1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}')
        end += 1
    return s[a:end]


helpers = reference[reference.index('static constexpr uint32_t AGC_INTERNAL_DATA_REGISTER'):reference.index('uint32_t* KYTY_SYSV_ABI AgcDcbDrawIndex(')]
helpers += '\n'.join(function(reference, n) for n in [
    'wait_reg_mem_poll_cycles_to_packet', 'wait_reg_mem32_control', 'wait_reg_mem64_control'])
program = r'''
#include "novafex.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#define KYTY_SYSV_ABI
#define PRINT_NAME(...)
#define LOGF(...)
#define LOGF_COLOR(...)
#define AgcTrace(...)
#define EXIT_NOT_IMPLEMENTED(x) do { if (x) throw std::runtime_error("invalid"); } while (0)
#define KYTY_PM4(n,op,r) (0xc0000000u | (((n)-2u)<<16u) | ((op)<<8u) | (r))
namespace Pm4 { constexpr uint32_t IT_COPY_DATA=0x40, IT_SET_UCONFIG_REG=0x79, IT_WAIT_REG_MEM=0x3c, IT_WAIT_REG_MEM_64=0x93; }
constexpr uint64_t base=0x8fc0000000ull, span=1ull<<30;
std::array<unsigned char,128> first, second;
namespace NovaFex {
bool GuestVAEnabled() {return true;}
uint64_t TranslateGuestVA(uint64_t a) {
 if(a>=base+span-128 && a<base+span) return (uint64_t)first.data()+a-(base+span-128);
 if(a>=base+span && a<base+span+128) return (uint64_t)second.data()+a-(base+span);
 return a;
}
}
unsigned copies=0;
namespace NovaGuest { void Copy(void* d,const void* s,size_t n){
 ++copies;
 // Match NovaGuest's translated copy via the production slot-aware wrapper;
 // prevent fortified memcpy from becoming raw stores to synthetic addresses.
 void* (*volatile copy)(void*,const void*,size_t)=&std::memcpy;
 copy(d,s,n);
} }
struct CommandBuffer {
 uint32_t* dst; unsigned words=0; bool fail=false;
 uint32_t* AllocateDW(unsigned n){words=n; return fail?nullptr:dst;}
};
''' + helpers
names = ['AgcDcbCopyData', 'AgcDcbWaitRegMem']
program += '\nnamespace baseline {\n' + '\n'.join(function(reference,n) for n in names) + '\n}\n'
program += '\nnamespace fast {\n' + '\n'.join(function(patched,n) for n in names) + '\n}\n'
program += r'''
void check(const std::array<uint32_t,32>& expected, uint64_t address,unsigned words) {
 for(unsigned i=0;i<words*4;++i) assert(*(const unsigned char*)NovaFex::TranslateGuestVA(address+i)==((const unsigned char*)expected.data())[i]);
 assert(*(const unsigned char*)NovaFex::TranslateGuestVA(address-1)==0xa5);
 assert(*(const unsigned char*)NovaFex::TranslateGuestVA(address+words*4)==0xa5);
}
int main(){
 unsigned cases=0;
 for(unsigned split : {4u,12u,24u,60u,80u}) {
  const auto address=base+span-split;
  auto* guest=(uint32_t*)address;
  for(unsigned i=0;i<256;++i){
   first.fill(0xa5);second.fill(0xa5);std::array<uint32_t,32> expected{};
   CommandBuffer a{expected.data()}, b{guest};
   auto dst=0x8d12345678ull+i, src=0xfedcba9876543210ull+i;
   copies=0;
   assert(baseline::AgcDcbCopyData(&a,i,i>>2,dst,i>>1,i>>4,src,i>>5,i>>6)==a.dst);
   assert(fast::AgcDcbCopyData(&b,i,i>>2,dst,i>>1,i>>4,src,i>>5,i>>6)==guest);
   assert(a.words==b.words && copies==1);check(expected,address,b.words);++cases;
  }
  for(unsigned size=0;size<2;++size) for(unsigned op=0;op<16;++op)
  for(unsigned cmp=0;cmp<8;++cmp) for(unsigned policy=0;policy<4;++policy)
  for(uint32_t poll : {0u,15u,16u,0xffffffffu}) {
   first.fill(0xa5);second.fill(0xa5);std::array<uint32_t,32> expected{};
   CommandBuffer a{expected.data()}, b{guest};
   const auto* label=(const volatile void*)0x8d00171003ull;
   copies=0;
   assert(baseline::AgcDcbWaitRegMem(&a,size,cmp,op,policy,label,0xfedcba9876543210ull,0x123456789abcdef0ull,poll)==a.dst);
   assert(fast::AgcDcbWaitRegMem(&b,size,cmp,op,policy,label,0xfedcba9876543210ull,0x123456789abcdef0ull,poll)==guest);
   assert(a.words==b.words && copies==1);check(expected,address,b.words);++cases;
  }
 }
 CommandBuffer failed{nullptr,0,true};copies=0;
 assert(fast::AgcDcbCopyData(nullptr,0,0,0,0,0,0,0,0)==nullptr);
 assert(fast::AgcDcbCopyData(&failed,0,0,0,0,0,0,0,0)==nullptr);
 assert(fast::AgcDcbWaitRegMem(&failed,0,0,0,0,nullptr,0,0,0)==nullptr);
 assert(fast::AgcDcbWaitRegMem(&failed,2,0,0,0,nullptr,0,0,0)==nullptr);
 assert(copies==0);
 printf("AGC packet equivalence and translated slot-boundary writes: PASS (%u cases)\n",cases);
}
'''
with tempfile.TemporaryDirectory() as d:
    cpp, exe = Path(d)/'test.cpp', Path(d)/'test'
    cpp.write_text(program)
    subprocess.run(['g++','-std=c++20','-O2','-fno-builtin','-DKYTY_NOVA_FEX=1',
                    '-I'+str(repo/'native/novafex'),str(cpp),
                    str(repo/'native/novafex/guest_memory.cpp'),
                    '-Wl,--wrap=memcpy,--wrap=memset,--wrap=memmove,--wrap=memcmp',
                    '-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
