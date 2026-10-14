#!/usr/bin/env python3
"""Execute the actual patched RELEASE_MEM parser against a recording command processor.
Verifies dispatch and batching, not Vulkan execution or hardware interrupt semantics.
"""
import pathlib, subprocess, sys, tempfile
root=pathlib.Path(sys.argv[1]); s=(root/'src/graphics/guest_gpu/command_processor/pm4Handlers.cpp').read_text()
a=s.index('KYTY_CP_OP_PARSER(CpOpReleaseMem)'); b=s.index('KYTY_CP_OP_PARSER(CpOpSetContextReg)',a)
f=s[a:b].replace('KYTY_CP_OP_PARSER(CpOpReleaseMem)', 'int release(CP& cp, uint32_t cmd_id, const uint32_t* buffer)')
program=r'''
#include <cstdint>
#include <atomic>
#include <cstdio>
#include <cassert>
#include <stdexcept>
#define KYTY_PROFILER_FUNCTION()
#define EXIT_NOT_IMPLEMENTED(x) do {if(x) throw std::runtime_error("invalid");} while(0)
#define EXIT_IF(x) EXIT_NOT_IMPLEMENTED(x)
#define EXIT(x) throw std::runtime_error(x)
constexpr uint32_t GcrGl2Writeback=1;
void LogUnknownReleaseMemGcr(uint32_t) {}
bool ReleaseMemGcrNeedsBarrier(uint32_t, uint32_t) {return false;}
uint32_t ReleaseMemCacheActionFromGcr(uint32_t) {return 0;}
struct CP {
 unsigned writes=0, bits=0, selector=99, context=0, flushes=0, interrupts=0;
 void TriggerEopEventAtEndOfPipe(uint32_t c) {++interrupts; context=c;}
 void BufferFlush(){++flushes;}
 void EmitGlobalBarrier(){}
 void WriteAtEndOfPipe32(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,void*,uint32_t,uint32_t i,uint32_t c){++writes;bits=32;selector=i;context=c;}
 void WriteAtEndOfPipe64(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,void*,uint64_t,uint32_t i,uint32_t c){++writes;bits=64;selector=i;context=c;}
};
''' + f + r'''
int main(){
 for(unsigned data : {0u,1u,2u,3u,5u}) for(unsigned irq : {0u,1u,2u,3u,4u}){
  CP cp; uint32_t packet[]={0x28,(data<<29)|(irq<<24),0x1000,0,0x1234,0x5678,0x123};
  assert(release(cp,0xc0061060,packet)==7);
  if(data==0 || irq==4){assert(cp.writes==0); assert(cp.interrupts==(irq!=0));}
  else {assert(cp.writes==1);assert(cp.bits==((data==1 || data==5)?32:64));assert(cp.selector==(irq==3?2:irq));}
  if(irq==3 && data!=0) assert(cp.flushes==0);
  if(irq!=0 || data!=0) assert(cp.context==0x123);
 }
 for(unsigned data : {4u,6u,7u}){CP cp;uint32_t p[]={0x28,data<<29,0x1000,0,0,0,0};bool rejected=false;try{release(cp,0xc0061060,p);}catch(...){rejected=true;}assert(rejected);}
 puts("RELEASE_MEM dispatch and batching: PASS (25 combinations, 3 rejected data selectors)");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d)/'test.cpp';p.write_text(program);binary=pathlib.Path(d)/'test'
 subprocess.run(['g++','-std=c++20','-O2',str(p),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
