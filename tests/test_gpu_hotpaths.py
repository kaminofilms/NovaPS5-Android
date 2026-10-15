#!/usr/bin/env python3
"""Execute real interpolant functions with non-identity guest addresses and compare outputs."""
from pathlib import Path
import subprocess, sys, tempfile, re
root = Path(sys.argv[1])
s = (root/'src/libs/agc.cpp').read_text()
def extract(text, sig):
 start=text.index(sig); pos=text.index('{',start); depth=1; end=pos+1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}'); end+=1
 return text[start:end]
start=s.index('static uint32_t shader_semantic_word(')
end=s.index('\nint KYTY_SYSV_ABI AgcGetDataPacketPayloadAddress',start)
patched=s[start:end]
baseline=patched.replace(extract(patched,'static Shader nova_interpolant_shader('),'')
baseline=re.sub(r'#if defined\(KYTY_NOVA_FEX\).*?#endif', '', baseline, flags=re.S)
header=(root/'src/graphics/shader/shader.h').read_text()
types='\n'.join(extract(header,'struct '+name+' {')+';' for name in ['ShaderRegister','ShaderSemantic','Shader'])
gpu=(root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
occ=extract(gpu,'case 0x00000039:')
cpp=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <mutex>
#include <stdexcept>
#define KYTY_NOVA_FEX 1
#define KYTY_SYSV_ABI
#define PRINT_NAME(...)
#define AgcTrace(...)
#define EXIT_NOT_IMPLEMENTED(x) do { if(x) throw std::runtime_error("invalid"); } while(0)
#define EXIT(...) throw std::runtime_error("invalid")
constexpr int OK=0;
namespace Pm4 { constexpr uint32_t SPI_PS_INPUT_CNTL_0=0xa191; }
struct ShaderUserData; struct ShaderSpecialRegs;
namespace GuestMemory {
constexpr uint64_t base=0x8fc0000000ull;
alignas(64) std::array<unsigned char, 8192> memory{};
template<class T> T* Ptr(T* p, uint64_t n) {
 auto a=reinterpret_cast<uint64_t>(p);
 if(a>=base && a-base <= memory.size() && n<=memory.size()-(a-base))
  return reinterpret_cast<T*>(memory.data()+a-base);
 return p;
}
template<class T> T* Ptr(uint64_t p,uint64_t n) { return Ptr(reinterpret_cast<T*>(p),n); }
void Copy(void* d,const void* s,uint64_t n) { std::memcpy(Ptr(static_cast<unsigned char*>(d),n),Ptr(static_cast<const unsigned char*>(s),n),n); }
}
'''+types+'\nnamespace original {\n'+baseline+'\n}\nnamespace native {\n'+patched+r'''
}
int main() {
 uint32_t rng=117;
 auto random=[&]() { rng^=rng<<13; rng^=rng>>17; rng^=rng<<5; return rng; };
 for(unsigned trial=0;trial<4000;++trial) {
  std::array<ShaderSemantic,32> inputs{},outputs{};
  for(auto& x:inputs) { auto v=random(); std::memcpy(&x,&v,4); }
  for(auto& x:outputs) { auto v=random(); std::memcpy(&x,&v,4); }
  Shader ps{},gs{}; ps.num_input_semantics=random()%33; gs.num_output_semantics=random()%33;
  ps.input_semantics=inputs.data(); gs.output_semantics=outputs.data();
  Shader guest_ps=ps, guest_gs=gs;
  guest_ps.input_semantics=reinterpret_cast<ShaderSemantic*>(GuestMemory::base+1024);
  guest_gs.output_semantics=reinterpret_cast<ShaderSemantic*>(GuestMemory::base+2048);
  std::memcpy(GuestMemory::memory.data()+1024,inputs.data(),sizeof(inputs));
  std::memcpy(GuestMemory::memory.data()+2048,outputs.data(),sizeof(outputs));
  std::memcpy(GuestMemory::memory.data(),&guest_ps,sizeof(guest_ps));
  std::memcpy(GuestMemory::memory.data()+256,&guest_gs,sizeof(guest_gs));
  for(unsigned version=0;version<2;++version) {
   std::array<ShaderRegister,32> expected{};
   auto* preg=reinterpret_cast<ShaderRegister*>(GuestMemory::base+4096);
   auto* pps=reinterpret_cast<Shader*>(GuestMemory::base);
   auto* pgs=reinterpret_cast<Shader*>(GuestMemory::base+256);
   if(version) { original::AgcCreateInterpolantMapping2(expected.data(),&gs,&ps); native::AgcCreateInterpolantMapping2(preg,pgs,pps); }
   else { original::AgcCreateInterpolantMapping(expected.data(),&gs,&ps); native::AgcCreateInterpolantMapping(preg,pgs,pps); }
   assert(std::memcmp(expected.data(),GuestMemory::memory.data()+4096,sizeof(expected))==0);
   assert(std::memcmp(&guest_ps,GuestMemory::memory.data(),sizeof(guest_ps))==0);
   assert(std::memcmp(&guest_gs,GuestMemory::memory.data()+256,sizeof(guest_gs))==0);
  }
 }
 uint32_t event_index=1; uint64_t event_address=GuestMemory::base+6144;
 uint64_t m_synthetic_occlusion_counter=19;
 auto* values=reinterpret_cast<uint64_t*>(GuestMemory::memory.data()+6144);
 for(unsigned i=0;i<32;++i) values[i]=0xcafebabedeadbeefull;
 switch(0x39) {
'''+occ+r'''
 }
 for(unsigned i=0;i<32;++i) assert(values[i]==(i%2 ? 0xcafebabedeadbeefull : (1ull<<63)|19));
 assert(m_synthetic_occlusion_counter==20);
 std::puts("GPU_HOTPATH_TEST: 8000 interpolant comparisons and interleaved occlusion stores PASS");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d); (p/'test.cpp').write_text(cpp)
 subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-fsanitize=undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
