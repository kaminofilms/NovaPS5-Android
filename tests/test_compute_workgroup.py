#!/usr/bin/env python3
"""Compile production workgroup/ID emission against an SSA evaluator.

Checks host shape and every guest local/global ID, including wave64-on-32
pairing. These host tests do not establish Adreno pipeline acceptance.
"""
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1])
def read(name):
    return (root / name).read_text()
def block(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

selection = block(read('src/graphics/shader/shader.h'), '[[nodiscard]] bool UsesLinearWorkgroup(')
local_index = block(read('src/graphics/shader/recompiler/backend/spirv/spirvEmitterHelpers.cpp'),
                    'uint32_t EmitLocalInvocationIndex(')
mapping = block(read('src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp'),
                'if ((state.lane_count == 2 || state.linear_workgroup)')
mode = block(read('src/graphics/shader/recompiler/backend/spirv/spirvEmitterModule.cpp'),
             'if (const auto* cs = ShaderWorkgroupInput(')
pipeline = read('src/graphics/host_gpu/renderer/pipeline/shaders.cpp')
compute = pipeline[pipeline.index('const ShaderComputeInputInfo& input_info,'):]
assert 'const auto wave_size = input_info.host_subgroup_size;' in compute
assert 'comp_subgroup_size.requiredSubgroupSize = wave_size;' in compute
module = read('src/graphics/shader/recompiler/backend/spirv/spirvEmitterModule.cpp')
assert 'if (state.lane_count == 2 || state.linear_workgroup)' in module
assert 'add_builtin(IR::StageInputKind::WorkgroupId' in module
emitter = read('src/graphics/shader/recompiler/backend/spirv/SpirvEmitter.cpp')
assert 'state.lane_count == 1u && input_info.compute != nullptr' in emitter
assert 'input_info.compute->UsesLinearWorkgroup(program.info.compute_derivatives)' in emitter

program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <unordered_map>
struct ShaderComputeInputInfo {
 uint32_t threads_num[3]={1,1,1};uint32_t max_workgroup_size_x=1024;
''' + selection + r'''
};
enum class ShaderType{Compute,Vertex};
namespace IR{enum class StageInputKind{LocalInvocationId,GlobalInvocationId,LocalInvocationIndex,WorkgroupId};}
namespace spv{enum Op{OpUDiv,OpUMod,OpIMul,OpBitwiseAnd,OpIAdd,OpLoad};enum Mode{ExecutionModeLocalSize};}
struct Builder{
 uint32_t physical_index=0,next=100;std::unordered_map<uint32_t,uint32_t> values;
 std::array<uint32_t,3> shape{};
 uint32_t AllocateId(){return next++;}
 uint32_t Constant(uint32_t v){auto id=AllocateId();values[id]=v;return id;}
 void AddFunction(spv::Op op,uint32_t,uint32_t result,uint32_t){assert(op==spv::OpLoad);values[result]=physical_index;}
 void AddExecutionMode(uint32_t,spv::Mode,uint32_t x,uint32_t y,uint32_t z){shape={x,y,z};}
};
struct State{ShaderType stage=ShaderType::Compute;struct{ShaderType stage=ShaderType::Compute;struct{bool compute_derivatives=false;}info;}program;
 struct{const ShaderComputeInputInfo* compute=nullptr;}input_info;
 Builder builder;uint32_t main_func=1,lane_count=1,lane_half=0;bool linear_workgroup=false;
 uint32_t group[3]={2,3,5};
};
using EmitterState=State;
const ShaderComputeInputInfo* ShaderWorkgroupInput(ShaderType,decltype(State::input_info) info){return info.compute;}
uint32_t InputVariableForKind(State&,IR::StageInputKind){return 1;}
uint32_t TypeU32(State&){return 1;}
uint32_t ConstantU32(State& s,uint32_t v){return s.builder.Constant(v);}
uint32_t EmitBinaryU32(State& s,spv::Op op,uint32_t a,uint32_t b){
 auto x=s.builder.values.at(a),y=s.builder.values.at(b);uint32_t v=0;
 switch(op){case spv::OpUDiv:assert(y);v=x/y;break;case spv::OpUMod:assert(y);v=x%y;break;
 case spv::OpIMul:v=x*y;break;case spv::OpBitwiseAnd:v=x&y;break;case spv::OpIAdd:v=x+y;break;default:assert(false);}
 return ConstantU32(s,v);
}
uint32_t EmitAddU32(State& s,uint32_t a,uint32_t b){return EmitBinaryU32(s,spv::OpIAdd,a,b);}
uint32_t EmitInputComponentU32(State& s,IR::StageInputKind k,uint32_t c){assert(k==IR::StageInputKind::WorkgroupId);return ConstantU32(s,s.group[c]);}
''' + local_index + r'''
uint32_t Map(State& state,IR::StageInputKind kind,uint32_t component){
''' + mapping + r'''
 assert(false);return 0;
}
void Shape(State& state){
''' + mode + r'''
}
int main(){
 uint32_t checked=0;
 for(auto dims:{std::array<uint32_t,3>{4,4,4},{8,8,1},{7,3,2},{2,3,5},{1,4,16},{64,1,1}}){
  ShaderComputeInputInfo input;std::copy(dims.begin(),dims.end(),input.threads_num);
  State s;s.input_info.compute=&input;s.linear_workgroup=input.UsesLinearWorkgroup(false);Shape(s);
  uint32_t n=dims[0]*dims[1]*dims[2];
  if(s.linear_workgroup){assert((s.builder.shape==std::array<uint32_t,3>{n,1,1}));}
  else{assert(s.builder.shape==dims);}
  for(uint32_t i=0;i<n && s.linear_workgroup;i++){
   s.builder.physical_index=i;uint32_t local[3]={i%dims[0],(i/dims[0])%dims[1],i/(dims[0]*dims[1])};
   for(uint32_t c=0;c<3;c++){
    assert(s.builder.values.at(Map(s,IR::StageInputKind::LocalInvocationId,c))==local[c]);
    assert(s.builder.values.at(Map(s,IR::StageInputKind::GlobalInvocationId,c))==local[c]+s.group[c]*dims[c]);
    checked++;
   }
  }
  s.program.info.compute_derivatives=true;s.linear_workgroup=input.UsesLinearWorkgroup(true);
  assert(!s.linear_workgroup);Shape(s);assert(s.builder.shape==dims);
 }
 // Preserve the existing AnyPS5-style paired wave64 lowering, with each
 // invocation representing low/high logical lanes 32 apart.
 {ShaderComputeInputInfo input;input.threads_num[0]=4;input.threads_num[1]=4;input.threads_num[2]=4;
  State s;s.input_info.compute=&input;s.lane_count=2;Shape(s);assert((s.builder.shape==std::array<uint32_t,3>{32,1,1}));
  for(uint32_t h=0;h<2;h++)for(uint32_t p=0;p<32;p++){
   s.lane_half=h;s.builder.physical_index=p;uint32_t i=p+32*h;
   uint32_t local[3]={i%4,(i/4)%4,i/16};for(uint32_t c=0;c<3;c++){
    assert(s.builder.values.at(Map(s,IR::StageInputKind::LocalInvocationId,c))==local[c]);checked++;
   }
  }
 }
 {ShaderComputeInputInfo i;i.threads_num[0]=4;i.threads_num[1]=4;i.threads_num[2]=4;
  i.max_workgroup_size_x=32;assert(!i.UsesLinearWorkgroup(false));
  i.max_workgroup_size_x=64;assert(i.UsesLinearWorkgroup(false));
  i.threads_num[0]=i.threads_num[1]=i.threads_num[2]=UINT32_MAX;assert(!i.UsesLinearWorkgroup(false));
 }
 printf("Compute workgroup lowering: PASS (%u coordinate checks, 4x4x4 -> 64x1x1, paired waves, derivatives, device limits)\n",checked);
}
'''
with tempfile.TemporaryDirectory() as d:
    source = pathlib.Path(d)/'test.cpp'
    source.write_text(program)
    exe = pathlib.Path(d)/'test'
    subprocess.run(['g++','-std=c++20','-O2','-Wall','-Wextra',str(source),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('Compute pipeline uses the compiler-selected host subgroup: PASS')
