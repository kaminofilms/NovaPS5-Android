#!/usr/bin/env python3
"""Execute real patched functions with inaccessible guest VAs and native backing."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(sys.argv[1]);agc=(root/'src/libs/agc.cpp').read_text();gpu=(root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
def extract(s,name):
 a=s.index(name);b=s.index('{',a);d=1;e=b+1
 while d:d+=(s[e]=='{')-(s[e]=='}');e+=1
 return s[a:e]
h=(root/'src/graphics/shader/shader.h').read_text()
structs=h[h.index('struct ShaderSharp {'):h.index('void ShaderInit();')]
prefix=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <type_traits>
#include <atomic>
#include <sys/mman.h>
#define KYTY_SYSV_ABI
#define PRINT_NAME()
#define LOGF(...)
#define AgcTrace(...)
#define EXIT_NOT_IMPLEMENTED(x) assert(!(x))
#define EXIT(...) assert(false)
#define KYTY_PM4_LEN(x) (((x)>>16)+2u)
#define KYTY_PM4_R(x) (((x)>>1)&1u)
constexpr int OK=0,GRAPHICS5_ERROR_INVALID_PACKET=-1,GRAPHICS5_ERROR_INVALID_SHADER_PROGRAM=-2;
constexpr uint32_t AGC_WAIT_USER_DATA_BEGIN_DW=4,AGC_INTERNAL_DATA_PACKET_SIZE_DW=5;
constexpr uint32_t AGC_WAIT_USER_DATA_BEGIN_32_TAG=0xc8010000,AGC_WAIT_USER_DATA_BEGIN_64_TAG=0xc8020000;
constexpr uint32_t AGC_INTERNAL_DATA_REGISTER=0x123,AGC_WAIT_USER_DATA_END_TAG=7,AGC_DRAW_INDIRECT_MULTI_BEGIN_TAG=8,AGC_DRAW_INDIRECT_MULTI_END_TAG=9;
namespace Pm4 {constexpr uint32_t IT_WAIT_REG_MEM=0x3c,IT_WAIT_REG_MEM_64=0x93,IT_SET_UCONFIG_REG=0x79;
uint32_t PacketSizeDw(uint32_t x){return KYTY_PM4_LEN(x);}}
namespace Prospero {enum class ShaderBinaryType:uint8_t {};}
static unsigned char native[8192]; static uintptr_t guest;
namespace GuestMemory {
template<class T>T* Ptr(T* p,uint64_t size){auto a=reinterpret_cast<uintptr_t>(p);if(a>=guest&&a<guest+8192){assert(size<=8192-(a-guest));return reinterpret_cast<T*>(native+a-guest);}return p;}
template<class T>T* Ptr(uint64_t p,uint64_t size){return Ptr(reinterpret_cast<T*>(p),size);}
}
bool get_shader_program_address_register(uint8_t,uint32_t* out){*out=0x10;return true;}
bool AgcIsInternalDataPacket(uint32_t,const uint32_t*);
'''
functions=['static int patch_program_address_register(','int KYTY_SYSV_ABI AgcCreateShader(','uint32_t KYTY_SYSV_ABI AgcGetPacketSize(','int KYTY_SYSV_ABI AgcSetPacketPredication(','int KYTY_SYSV_ABI AgcSetRangePredication(','bool AgcIsInternalDataPacket(','static uint32_t* get_agc_wait_packet(','int KYTY_SYSV_ABI AgcWaitRegMemPatchAddress(']
cpp=prefix+structs+r'''
static ShaderMappedData mapped;
void ShaderMapUserData(uint64_t,const ShaderMappedData& m){mapped=m;}
void dbg_dump_shader(const Shader*){}
struct CommandProcessor {bool m_predicate_skip=false;int suspended=0;void SuspendPm4(){++suspended;}
void SetPredication(uint32_t,uint32_t,uint32_t,const volatile void*,uint32_t);};
'''+ '\n'.join(extract(agc,n) for n in functions)+extract(gpu,'void CommandProcessor::SetPredication(')+r'''
uint32_t header(uint32_t len,uint32_t op,uint32_t r=0){return ((len-2)<<16)|(op<<8)|(r<<1);}
int main(){
 void* reserved=mmap(nullptr,8192,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(reserved!=MAP_FAILED);guest=reinterpret_cast<uintptr_t>(reserved);
 auto* packet=reinterpret_cast<uint32_t*>(guest);auto* v=reinterpret_cast<uint32_t*>(native);
 assert(get_agc_wait_packet(nullptr)==nullptr);
 for(auto wide:{false,true}){
  v[0]=header(4,Pm4::IT_SET_UCONFIG_REG,1);v[1]=AGC_INTERNAL_DATA_REGISTER;
  v[2]=wide?AGC_WAIT_USER_DATA_BEGIN_64_TAG:AGC_WAIT_USER_DATA_BEGIN_32_TAG;
  v[4]=header(wide?9:7,wide?Pm4::IT_WAIT_REG_MEM_64:Pm4::IT_WAIT_REG_MEM);
  assert(get_agc_wait_packet(packet)==packet+4);
  auto addr=reinterpret_cast<void*>(0x1234567800ull);assert(AgcWaitRegMemPatchAddress(packet,addr)==OK);
  v[4]|=2;assert(get_agc_wait_packet(packet)==nullptr);v[4]&=~2u;
  v[1]++;assert(get_agc_wait_packet(packet)==nullptr);v[1]--;
  v[2]^=0x10000000;assert(get_agc_wait_packet(packet)==nullptr);
 }
 for(uint32_t pred:{0u,1u,2u,257u}){
  v[0]=header(4,0x10);v[4]=header(3,0x20);uint32_t first=v[0],second=v[4];
  assert(AgcGetPacketSize(packet)==4);AgcSetRangePredication(packet,packet+7,pred);
  const auto bit=uint8_t(pred)==1?1u:0u;assert(v[0]==(first|bit)&&v[4]==(second|bit));
  AgcSetPacketPredication(packet,pred);assert(v[0]==(first|bit));
 }
 auto* sh=reinterpret_cast<Shader*>(native+512);*sh={};auto* gsh=reinterpret_cast<Shader*>(guest+512);
 auto* data=reinterpret_cast<ShaderUserData*>(native+768);*data={};
 sh->file_header=0x34333231;sh->version=0x18;sh->num_sh_registers=2;
 auto relative=[](uintptr_t target,uintptr_t field){return target-field;};
 sh->user_data=reinterpret_cast<ShaderUserData*>(relative(guest+768,guest+512+offsetof(Shader,user_data)));
 sh->sh_registers=reinterpret_cast<ShaderRegister*>(relative(guest+1024,guest+512+offsetof(Shader,sh_registers)));
 data->direct_resource_offset=reinterpret_cast<uint16_t*>(relative(guest+1200,guest+768+offsetof(ShaderUserData,direct_resource_offset)));
 data->sharp_resource_offset[2]=reinterpret_cast<ShaderSharp*>(relative(guest+1216,guest+768+offsetof(ShaderUserData,sharp_resource_offset)+2*sizeof(void*)));
 auto* regs=reinterpret_cast<ShaderRegister*>(native+1024);regs[0]={0x10,0};regs[1]={0x11,0xabcdef00};
 auto* output=reinterpret_cast<Shader**>(guest+1400);const auto* code=reinterpret_cast<void*>(0x1234567800ull);
 assert(AgcCreateShader(output,gsh,code)==OK);assert(*reinterpret_cast<Shader**>(native+1400)==gsh);
 assert(sh->user_data==reinterpret_cast<ShaderUserData*>(guest+768));assert(sh->sh_registers==reinterpret_cast<ShaderRegister*>(guest+1024));
 assert(data->direct_resource_offset==reinterpret_cast<uint16_t*>(guest+1200));assert(data->sharp_resource_offset[0]==nullptr);
 assert(data->sharp_resource_offset[2]==reinterpret_cast<ShaderSharp*>(guest+1216));
 assert(mapped.user_data==sh->user_data&&sh->code==code);assert(regs[0].value==0x12345678&&regs[1].value==0xabcdef00);
 CommandProcessor cp;auto* counters=reinterpret_cast<uint64_t*>(native+2048);auto* gc=reinterpret_cast<void*>(guest+2048);
 for(auto condition:{0u,1u})for(auto wait:{0u,1u}){
  for(int i=0;i<32;i++)counters[i]=(1ull<<63);cp.SetPredication(condition,1,wait,gc,0);assert(cp.m_predicate_skip==(condition==1));
  counters[31]++;cp.SetPredication(condition,1,wait,gc,0);assert(cp.m_predicate_skip==(condition==0));
  counters[30]=0;cp.m_predicate_skip=true;int old=cp.suspended;cp.SetPredication(condition,1,wait,gc,0);assert(cp.suspended==old+(wait==0));if(wait)assert(!cp.m_predicate_skip);
  for(auto val:{0ull,1ull}){counters[0]=val;cp.SetPredication(condition,3,wait,gc,0);assert(cp.m_predicate_skip==(condition?val==0:val!=0));}
 }
 cp.SetPredication(0,0,0,nullptr,0);assert(!cp.m_predicate_skip);munmap(reserved,8192);
 puts("NOVA_ACCESS_TEST: PASS inaccessible guest pointers, relocation ABI, packets, query readiness and conditions");
}
'''
cpp=cpp.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(cpp)
 subprocess.run(['c++','-std=c++20','-O2','-fsanitize=undefined','-fno-sanitize-recover=all',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
