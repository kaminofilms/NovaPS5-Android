#!/usr/bin/env python3
"""Execute production WRITE_DATA and guestMemory.h with disjoint translated slots.
This verifies word-address selection and publication semantics, not device FPS.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);src=(root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
a=src.index('void CommandProcessor::WriteData(');b=src.index('\nvoid CommandProcessor::WriteReferenceClock',a)
method=src[a:b]
stub=r'''
#pragma once
#include <cstdint>
#include <algorithm>
#define KYTY_NOVA_FEX 1
inline uint32_t input0[4],input1[4],output0[4],output1[4];
inline unsigned translations=0;
inline constexpr uint64_t high=0x10000000000ull;
namespace NovaGuest {
inline bool IsHigh(uint64_t a,uint64_t){return a>=high&&a<high+64;}
inline uint64_t Piece(uint64_t a,uint64_t n){return std::min(n,16-(a%16));}
inline void Copy(void*,const void*,uint64_t){__builtin_trap();}
inline void Set(void*,int,uint64_t){__builtin_trap();}
}
namespace NovaFex {
inline uint64_t TranslateGuestVA(uint64_t a){
 ++translations;uint32_t* slots[]={input0,input1,output0,output1};
 return reinterpret_cast<uint64_t>(slots[(a-high)/16])+(a%16);
}
}
'''
main=r'''
#include "common/guestMemory.h"
#include <cassert>
#include <cinttypes>
#include <stdexcept>
#define EXIT(...) throw std::runtime_error("bad selector")
unsigned notes=0;uint32_t noted=0;
void NovaNoteGpuWrite(void*,uint64_t v,uint32_t,char){++notes;noted=v;}
struct CommandProcessor {uint32_t m_interrupt_event_id=0;void WriteData(uint32_t*,const uint32_t*,uint32_t,uint32_t);};
'''+method+r'''
int main(){
 CommandProcessor cp;
 // Zero-length packets must touch neither pointer nor history.
 cp.WriteData(nullptr,nullptr,0,0);assert(notes==0&&translations==0);
 for(uint32_t mode:{0u,1u<<16})for(unsigned n=1;n<=8;++n){
  for(unsigned i=0;i<4;++i){input0[i]=100+i;input1[i]=104+i;output0[i]=output1[i]=0;}
  cp.WriteData(reinterpret_cast<uint32_t*>(high+32),reinterpret_cast<const uint32_t*>(high),n,mode);
  if(mode){assert(output0[0]==99+n);for(unsigned i=1;i<4;++i)assert(output0[i]==0);for(auto v:output1)assert(v==0);}
  else for(unsigned i=0;i<8;++i)assert((i<4?output0[i]:output1[i-4])==(i<n?100+i:0));
  assert(noted==99+n);
 }
 // Host pointers still work, including write-one-address's final word.
 uint32_t host_src[]={4,8,12,16,20,24,28},host_dst[7]={};
 cp.WriteData(host_dst,host_src,7,0);for(unsigned i=0;i<7;++i)assert(host_dst[i]==host_src[i]);
 cp.WriteData(host_dst,host_src,7,1u<<16);assert(host_dst[0]==28);
 // Exact scalar order is observable for overlapping data; no bulk-copy rewrite.
 uint32_t overlap[]={1,2,3,4};cp.WriteData(overlap+1,overlap,3,0);
 for(auto v:overlap)assert(v==1);
 bool rejected=false;try{cp.WriteData(host_dst,host_src,1,0x780);}catch(...){rejected=true;}
 assert(rejected);
 puts("PM4 word publication: host/translated/cross-slot/increment/repeated/zero/invalid packets PASS");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'common').mkdir();(p/'common/novaFex.h').write_text(stub);(p/'test.cpp').write_text(main)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-O2',*flags,'-I'+str(p),'-I'+str(root/'src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
