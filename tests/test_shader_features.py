#!/usr/bin/env python3
"""Compile production LDS backing selection, emitter constructor and shader cache key.
No physical-device or game-boot result is inferred from these host checks.
"""
import pathlib, subprocess, sys, tempfile, shutil
root=pathlib.Path(sys.argv[1])
h=(root/'src/graphics/shader/shader.h').read_text()
a=h.index('[[nodiscard]] bool UsesStorageLds(');b=h.index('\n\t}',a)+3
selection=h[a:b]
s=(root/'src/graphics/shader/recompiler/backend/spirv/spirvEmitterInternal.h').read_text()
a=s.index('\tEmitterState(IR::Program&');b=s.index('\n\n\tBuilder',a)
constructor=s[a:b]
s=(root/'src/graphics/shader/shader.cpp').read_text();a=s.index('void BuildStageStaticKey(const ShaderComputeInputInfo&');b=s.index('\nShaderParams PrepareProgram(',a);cache=s[a:b]
s=(root/'src/graphics/presentation/window/vulkanWindow.cpp').read_text();a=s.index('graphics.native_lds_int64_atomics_enabled =');b=s.index(';',a)+1;profile=s[a:b]
assert 'state.lds_storage_class == spv::StorageClassStorageBuffer' in (root/'src/graphics/shader/recompiler/backend/spirv/SpirvEmitter.cpp').read_text()
assert 'input_info.native_lds_int64_atomics = m_graphics.native_lds_int64_atomics_enabled' in (root/'src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp').read_text()
program=r'''
#include <cstdint>
#include <vector>
#include <cassert>
#include <cstdio>
struct ShaderComputeInputInfo {
 bool lds_storage=false,native_lds_int64_atomics=true,dispatch_thread_dimensions=false,async_compute=false,tg_size_en=false;
 uint32_t workgroup_register=0,wave_size=64,host_subgroup_size=32,thread_ids_num=0,lds_size_dwords=0,scratch_size_dwords=0;
 uint32_t max_workgroup_size_x=0;uint8_t float_mode=0xc0;uint32_t threads_num[3]={64,1,1};bool group_id[3]={false,false,false};
''' + selection+r'''
};
enum class ShaderType{Compute,Mesh,Vertex};
namespace IR {struct Program {ShaderType stage=ShaderType::Compute;struct {bool uses_lds=true,shared_int64_atomics=false;}info;};}
struct ShaderStageInputInfo {const ShaderComputeInputInfo* compute=nullptr;};
const ShaderComputeInputInfo* ShaderWorkgroupInput(ShaderType stage,ShaderStageInputInfo info){return stage==ShaderType::Compute?info.compute:nullptr;}
namespace spv {enum StorageClass{StorageClassFunction,StorageClassWorkgroup,StorageClassStorageBuffer};}
struct Builder {Builder(uint32_t){}};
struct EmitterState {
''' + constructor+r'''
 Builder builder;IR::Program& program;ShaderStageInputInfo input_info;spv::StorageClass lds_storage_class=spv::StorageClassFunction;
};
''' + cache+r'''
int main(){
 for(bool over:{false,true})for(bool atomic64:{false,true})for(bool native:{false,true}){
  ShaderComputeInputInfo input;input.lds_storage=over;input.native_lds_int64_atomics=native;
  IR::Program p;p.info.shared_int64_atomics=atomic64;
  EmitterState s(p,{&input});
  const bool expected=over || (atomic64 && !native);
  assert((s.lds_storage_class==spv::StorageClassStorageBuffer)==expected);
  if(!over && !atomic64)assert(s.lds_storage_class==spv::StorageClassWorkgroup);
 }
 {ShaderComputeInputInfo i;IR::Program p;p.stage=ShaderType::Vertex;p.info.shared_int64_atomics=true;i.native_lds_int64_atomics=false;EmitterState s(p,{&i});assert(s.lds_storage_class==spv::StorageClassFunction);}
 for(bool atomic:{false,true})for(bool extension:{false,true})for(bool layout:{false,true}){
  constexpr uint32_t VK_TRUE=1;
  struct{uint32_t shaderSharedInt64Atomics;}features12{atomic?1u:0u};
  struct{uint32_t workgroupMemoryExplicitLayout;}workgroup_layout{layout?1u:0u};
  struct{bool native_lds_int64_atomics_enabled=false;}graphics;
  const bool workgroup_layout_extension=extension;
''' +profile+r'''
  assert(graphics.native_lds_int64_atomics_enabled==(atomic&&extension&&layout));
 }
 ShaderComputeInputInfo i;std::vector<uint32_t> a,b,c;BuildStageStaticKey(i,a);i.native_lds_int64_atomics=false;BuildStageStaticKey(i,b);i.lds_storage=true;BuildStageStaticKey(i,c);assert(a!=b && b!=c && a!=c);
 puts("Shader device profile: PASS (8 enabled-feature combinations, 8 LDS backing combinations, vertex isolation, distinct storage/profile cache variants)");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d)/'test.cpp';p.write_text(program);out=pathlib.Path(d)/'test'
 subprocess.run(['g++','-std=c++20','-O2','-Wall','-Wextra',str(p),'-o',str(out)],check=True);subprocess.run([str(out)],check=True)
 if shutil.which('spirv-val'):
  asm=pathlib.Path(d)/'lds.spvasm';binary=pathlib.Path(d)/'lds.spv'
  asm.write_text('''OpCapability Shader
OpCapability Int64
OpCapability Int64Atomics
OpMemoryModel Logical GLSL450
OpEntryPoint GLCompute %main "main"
OpExecutionMode %main LocalSize 32 1 1
OpDecorate %array ArrayStride 8
OpMemberDecorate %block 0 Offset 0
OpDecorate %block Block
OpDecorate %buffer DescriptorSet 0
OpDecorate %buffer Binding 0
%void = OpTypeVoid
%fn = OpTypeFunction %void
%uint = OpTypeInt 32 0
%ulong = OpTypeInt 64 0
%zero = OpConstant %uint 0
%scope = OpConstant %uint 2
%semantics = OpConstant %uint 72
%one = OpConstant %ulong 1
%array = OpTypeRuntimeArray %ulong
%block = OpTypeStruct %array
%ptr_block = OpTypePointer StorageBuffer %block
%ptr_ulong = OpTypePointer StorageBuffer %ulong
%buffer = OpVariable %ptr_block StorageBuffer
%main = OpFunction %void None %fn
%entry = OpLabel
%ptr = OpAccessChain %ptr_ulong %buffer %zero %zero
%old = OpAtomicIAdd %ulong %ptr %scope %semantics %one
OpReturn
OpFunctionEnd
''')
  subprocess.run(['spirv-as','--target-env','vulkan1.1',str(asm),'-o',str(binary)],check=True)
  subprocess.run(['spirv-val','--target-env','vulkan1.1',str(binary)],check=True)
  print('Storage-backed 64-bit LDS atomic SPIR-V validation: PASS (no WorkgroupMemoryExplicitLayout capability)')
 else:print('Storage-backed LDS SPIR-V validation: SKIP locally (spirv-tools required in CI)')
