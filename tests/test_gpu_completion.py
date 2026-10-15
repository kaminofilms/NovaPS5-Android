#!/usr/bin/env python3
"""Compile actual EOP and shader-fence bodies; verify ordering with a recording GPU timeline.
No claim of device/Vulkan game execution: this is a deterministic host regression.
"""
import pathlib, subprocess, sys, tempfile, shutil, struct
root = pathlib.Path(sys.argv[1])
s = (root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
a = s.index('template <typename T>\nvoid CommandProcessor::WriteAtEndOfPipe(')
b = s.index('\nvoid CommandProcessor::WriteAtEndOfPipe32(', a)
body = s[a:b]
wait=s[s.index('void CommandProcessor::WaitRegMem('):s.index('template void CommandProcessor::WaitRegMem<uint32_t>')]
assert 'gave up' not in wait and 'known_bad' not in wait and 'SuspendPm4();' in wait
print('WAIT_REG_MEM: PASS (unsatisfied waits remain suspended; no timeout success)')
flow=(root/'src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp').read_text()
a=flow.index('void EmitStoreCompletion(');b=flow.index('\nvoid EmitBarrier(',a)
shader=flow[a:b]
pre=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cinttypes>
#include <functional>
#include <vector>
#include <stdexcept>
#include <type_traits>
#define EXIT_IF(x) do {if(x) throw std::runtime_error("invalid");} while(0)
#define EXIT_NOT_IMPLEMENTED(x) EXIT_IF(x)
#define EXIT(...) throw std::runtime_error("unsupported")
#define LOGF(...) ((void)0)
bool GraphicsRunDebugDumpEnabled(){return false;}
namespace GuestMemory { unsigned writes=0; void Copy(void* p,const void* v,size_t n); }
extern bool gpu_finished;
namespace GuestMemory { void Copy(void* p,const void* v,size_t n){assert(gpu_finished);++writes;std::memcpy(p,v,n);} template<class T>T* Ptr(T* p,uint64_t){return p;} }
namespace Sync {uint64_t clock=10;uint64_t ReadReferenceClock(){return ++clock;} template<class... T>void ReadGds(T...){}}
struct Cache {int* GetGdsBuffer(){static int x;return &x;}};
struct Renderer { unsigned irqs=0;uint32_t context=0;uint64_t* label=nullptr;uint64_t expected=0;Cache cache;Cache& GetBufferCache(){return cache;} void TriggerInterrupt(unsigned,uint32_t c){if(label)assert(*label==expected);++irqs;context=c;} };
struct Buffer {int Handle(){return 1;}};
bool gpu_finished=false;
struct Scheduler {
 struct Op{unsigned tick;std::function<void()> fn;};
 unsigned tick=1,submitted=0,completed=0;std::vector<Op> pending;
 void DeferPriorityOperation(std::function<void()> f){pending.push_back({tick,std::move(f)});}
 void Flush(){submitted=tick++;}
 void Run(){while(!pending.empty() && pending.front().tick<=completed){auto f=std::move(pending.front().fn);pending.erase(pending.begin());f();}}
 void Complete(){completed=submitted;gpu_finished=true;Run();}
 void Finish(){Flush();Complete();}
 unsigned CurrentTick(){return tick;}
 void WaitPriorityOperations(unsigned t){assert(completed>=t);Run();}
};
struct CommandProcessor {
 Renderer m_renderer; unsigned m_interrupt_event_id=7;Scheduler scheduler;Buffer command;
 Buffer& CurrentBuffer(){return command;}Scheduler& GetScheduler(){return scheduler;}
 bool IsAsyncComputeQueue(){return false;}void SynchronizeGpu(){scheduler.Flush();scheduler.Complete();}
 void TriggerEopEventAtEndOfPipe(uint32_t c){scheduler.DeferPriorityOperation([this,c]{m_renderer.TriggerInterrupt(m_interrupt_event_id,c);});}
 template<class T>void WriteAtEndOfPipe(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,void*,T,uint32_t,uint32_t);
};
'''
post=r'''
int main(){
 for(unsigned cache : {0u,0x38u}) for(unsigned irq:{0u,2u}) for(unsigned event:{0x2bu,0x2du}){
  gpu_finished=false;CommandProcessor cp;uint64_t label=0;cp.m_renderer.label=&label;cp.m_renderer.expected=0x123456789abcdef0ull;
  cp.WriteAtEndOfPipe<uint64_t>(0,0,event,cache,0,2,&label,cp.m_renderer.expected,irq,0x123);
  assert(gpu_finished && cp.scheduler.submitted==cp.scheduler.completed);
  assert(label==cp.m_renderer.expected && cp.m_renderer.irqs==(irq==2));
  if(irq)assert(cp.m_renderer.context==0x123);
 }
 {gpu_finished=false;CommandProcessor cp;uint32_t label=0;cp.WriteAtEndOfPipe<uint32_t>(0,0,0x2f,0,6,2,&label,0x98765432u,2,9);assert(gpu_finished);assert(label==0x98765432u && cp.m_renderer.irqs==1);}
 {gpu_finished=false;CommandProcessor cp;uint64_t stamp=0;cp.WriteAtEndOfPipe<uint64_t>(0,0,0x28,0,0,4,&stamp,0,0,0);assert(gpu_finished && stamp==11);}
 {CommandProcessor cp;uint64_t label=0;bool rejected=false;try{cp.WriteAtEndOfPipe<uint64_t>(0,0,0x3f,0,0,2,&label,1,0,0);}catch(...){rejected=true;}assert(rejected && label==0 && cp.scheduler.pending.empty());}
 puts("GPU completion: PASS (GPU-before-store 32/64-bit labels, IRQ after store, no-IRQ progress, completion timestamp, unsupported-event rejection)");
}
'''
# Exercise the exact SPIR-V emission method with recording constants/builder.
shaderpre=r'''
#include <cstdint>
#include <cassert>
#include <vector>
#include <cstdio>
namespace spv {enum :uint32_t{OpMemoryBarrier=225,ScopeDevice=1,MemorySemanticsAcquireReleaseMask=8,MemorySemanticsUniformMemoryMask=64,MemorySemanticsImageMemoryMask=2048};}
struct Builder{std::vector<uint32_t> words;void AddFunction(uint32_t op,uint32_t scope,uint32_t semantics){words={op,scope,semantics};}};
struct EmitterState{Builder builder;};
uint32_t ConstantU32(EmitterState&,uint32_t value){return value;}
'''
shaderpost=r'''
int main(){EmitterState s;EmitStoreCompletion(s);assert((s.builder.words==std::vector<uint32_t>{225,1,2120}));puts("SPIR-V store completion: PASS (device memory fence, acquire/release buffer and image visibility, no control barrier)");}
'''
with tempfile.TemporaryDirectory() as d:
 for name,source in [('completion',pre+body+post),('shader',shaderpre+shader+shaderpost)]:
  p=pathlib.Path(d)/(name+'.cpp');p.write_text(source);binary=pathlib.Path(d)/name
  subprocess.run(['g++','-std=c++20','-O2','-Wall','-Wextra','-Wno-unused-variable',str(p),'-o',str(binary)],check=True)
  subprocess.run([str(binary)],check=True)
 # Validate a minimal Vulkan compute module using the exact emitted memory-fence operands.
 # Full generated game shaders remain a device/integration validation requirement.
 val=shutil.which('spirv-val')
 if val:
  asm=shutil.which('spirv-as')
  assert asm
  p=pathlib.Path(d)/'fence.spvasm'
  p.write_text('''OpCapability Shader
OpMemoryModel Logical GLSL450
OpEntryPoint GLCompute %main "main"
OpExecutionMode %main LocalSize 1 1 1
%void = OpTypeVoid
%fn = OpTypeFunction %void
%uint = OpTypeInt 32 0
%device = OpConstant %uint 1
%semantics = OpConstant %uint 2120
%main = OpFunction %void None %fn
%entry = OpLabel
OpMemoryBarrier %device %semantics
OpReturn
OpFunctionEnd
''')
  out=pathlib.Path(d)/'fence.spv'
  subprocess.run([asm,'--target-env','vulkan1.1',str(p),'-o',str(out)],check=True)
  subprocess.run([val,'--target-env','vulkan1.1',str(out)],check=True)
  print('SPIR-V Vulkan 1.1 fence module validation: PASS')
 else: print('SPIR-V binary validation: SKIP (spirv-tools absent locally; required in Android CI)')
