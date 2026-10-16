#!/usr/bin/env python3
"""Run the production packet fetcher against protected aliases and exact dirty bytes."""
import pathlib,subprocess,sys,tempfile,os
root=pathlib.Path(sys.argv[1]);s=(root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
a=s.index('static const uint32_t* NovaReadPm4Packet(');b=s.index('\nvoid CommandProcessor::ProcessPm4(',a);fetch=s[a:b]
a=s.index('static std::span<const uint32_t> HostCommands(');b=s.index('\nvoid GuestGpu::Submit(',a);host=s[a:b]
assert s.index('NovaReadPm4Packet(guest_packet, remaining_dw')<s.index('const auto        packet_header = packet[0];',s.index('void CommandProcessor::ProcessPm4('))
assert 'handler(*this, packet_header & ~1u, packet + 1, remaining_dw, total_dw)' in s
pre=r'''
#include "novaRenderCosts.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <span>
#include <vector>
#include <stdexcept>
#include <sys/mman.h>
#include <unistd.h>
#define EXIT_IF(c) do{if(c)throw std::runtime_error("invalid packet");}while(0)
#define KYTY_PM4_R(h) (((h)>>2)&63u)
namespace Pm4 {constexpr uint32_t IT_NOP=0x10,R_ZERO=0;uint32_t PacketSizeDw(uint32_t h){return (h&0x3fffff00u)==0x3fff1000u?1u:((h>>16)&0x3fff)+2;}}
#if defined(__SANITIZE_ADDRESS__)
constexpr uint64_t guest=0x20003ffff000ull; // ASAN application range, outside shadow/gap.
#else
constexpr uint64_t guest=0x903ffff000ull;
#endif
std::vector<uint8_t> backing(128*1024);uint64_t dirty=0;unsigned waits=0,reads=0;bool valid=true;
namespace GuestMemory {template<class T>T* Ptr(T*,uint64_t){return reinterpret_cast<T*>(backing.data());}}
namespace LibKernel::Memory {
bool TryReadBufferBacking(uint64_t a,void* p,uint64_t n){
 ++reads;if(!valid || a<guest || n>backing.size() || a-guest>backing.size()-n)return false;
 if(dirty && a<dirty+4 && a+n>dirty){++waits;uint32_t real=0x12345678;std::memcpy(backing.data()+dirty-guest,&real,4);dirty=0;}
 std::memcpy(p,backing.data()+a-guest,n);return true;
}}
'''
post=r'''
int main(){
 // The guest pointer is intentionally inaccessible; exact backing reads must work.
 void* inaccessible=mmap(reinterpret_cast<void*>(guest),backing.size(),PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);assert(inaccessible==reinterpret_cast<void*>(guest));
 std::vector<uint32_t> scratch;uint32_t header=0xc0023700,words[]={header,11,22,33};std::memcpy(backing.data(),words,sizeof words);
 auto span=HostCommands({reinterpret_cast<const uint32_t*>(guest),4});assert(span.data()==(NovaRender::EverProfile()?reinterpret_cast<const uint32_t*>(guest):reinterpret_cast<const uint32_t*>(backing.data())));
 dirty=guest+512;auto* packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),4,scratch);assert(packet[0]==header && packet[3]==33 && waits==0 && dirty==guest+512);
 // Ordinary NOP padding can contain labels; unused payload bytes are not fetched.
 uint32_t nopwords[]={0xc0021000u,0,0,0};std::memcpy(backing.data(),nopwords,sizeof nopwords);dirty=guest+8;
 packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),4,scratch);assert(waits==0 && dirty==guest+8 && packet[1]==0);
 nopwords[1]=0x68750000u;std::memcpy(backing.data(),nopwords,sizeof nopwords);
 packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),4,scratch);assert(waits==1 && packet[2]==0x12345678);waits=0;
 std::memcpy(backing.data(),words,sizeof words);
 // A genuine GPU write inside the packet must still synchronize.
 dirty=guest+8;packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),4,scratch);assert(waits==1 && packet[2]==0x12345678);
 // A later update must be refetched on retry; no whole-command-list snapshot.
 uint32_t changed=99;std::memcpy(backing.data()+12,&changed,4);packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),4,scratch);assert(packet[3]==99);
 for(uint32_t nop:{0x80000000u,0x3fff1000u}){std::memcpy(backing.data(),&nop,4);packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),1,scratch);assert(scratch.size()==1 && packet[0]==nop);}
 // Maximum packet and a packet crossing the translated 1 GiB slot boundary.
 uint32_t large=0xffff3700u;std::memcpy(backing.data(),&large,4);packet=NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),16385,scratch);assert(scratch.size()==16385);
 bool rejected=false;try{NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),2,scratch);}catch(...){rejected=true;}assert(rejected);
 valid=false;rejected=false;try{NovaReadPm4Packet(reinterpret_cast<const uint32_t*>(guest),16385,scratch);}catch(...){rejected=true;}assert(rejected);
 munmap(inaccessible,backing.size());puts("NOVA_PM4_FETCH_TEST: protected alias, adjacent labels without waits, real dirty command synchronization, retry/refetch, NOP/max/cross-slot packets, bounds and profile isolation PASS");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d)/'fetch.cpp';p.write_text(pre+host+fetch+post);out=pathlib.Path(d)/'fetch'
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.environ.get('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-O2','-Wall','-Wextra',*flags,'-I'+str(root/'src/graphics/host_gpu/renderer'),str(p),'-o',str(out)],check=True)
 for title in ('PPSA04703','PPSA15552',''):
  subprocess.run([str(out)],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True)
