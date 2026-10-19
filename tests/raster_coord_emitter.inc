#include "graphics/shader/recompiler/backend/spirv/SpirvBuilder.h"
#include <fstream>
#include <bit>
using Libs::Graphics::ShaderRecompiler::Spirv::Builder;
namespace IR {enum class StageInputKind {FragCoord,TessCoord};}
struct State {Builder builder;uint32_t push_constant_variable=0,input=0;};
uint32_t TypeU32(State&s){return s.builder.Type(spv::OpTypeInt,32u,0u);}
uint32_t TypeF32(State&s){return s.builder.Type(spv::OpTypeFloat,32u);}
uint32_t ConstantU32(State&s,uint32_t v){return s.builder.Constant(spv::OpConstant,TypeU32(s),v);}
uint32_t TypePointer(State&s,spv::StorageClass storage,uint32_t type){return s.builder.Type(spv::OpTypePointer,storage,type);}
uint32_t TypePushConstantElementPointer(State&s){return TypePointer(s,spv::StorageClassPushConstant,TypeU32(s));}
uint32_t Coord(State&state,uint32_t component){
 const auto variable=state.input;const auto kind=IR::StageInputKind::FragCoord;
 /* PRODUCTION_COORD_BRANCH */
 return 0;
}
int main(int argc,char**argv){if(argc!=2)return 1;State s;auto& b=s.builder;
 b.RequireCapability(spv::CapabilityShader);b.AddMemoryModel(spv::AddressingModelLogical,spv::MemoryModelGLSL450);
 auto f=TypeF32(s),u=TypeU32(s),v4=b.Type(spv::OpTypeVector,f,4u);
 auto array=b.DecoratedType(spv::OpTypeArray,{{spv::OpDecorate,{spv::DecorationArrayStride,4}}},u,ConstantU32(s,32));
 auto block=b.DecoratedType(spv::OpTypeStruct,{{spv::OpMemberDecorate,{0,spv::DecorationOffset,0}},{spv::OpDecorate,{spv::DecorationBlock}}},array);
 s.push_constant_variable=b.DefineGlobalVariable(TypePointer(s,spv::StorageClassPushConstant,block),spv::StorageClassPushConstant);
 s.input=b.DefineGlobalVariable(TypePointer(s,spv::StorageClassInput,v4),spv::StorageClassInput);
 b.AddAnnotation(spv::OpDecorate,s.input,spv::DecorationBuiltIn,spv::BuiltInFragCoord);
 std::vector<uint32_t> outputs;
 for(unsigned i=0;i<4;++i){auto id=b.DefineGlobalVariable(TypePointer(s,spv::StorageClassOutput,f),spv::StorageClassOutput);b.AddAnnotation(spv::OpDecorate,id,spv::DecorationLocation,i);outputs.push_back(id);}
 auto fn=b.AllocateId(),void_t=b.Type(spv::OpTypeVoid),fn_t=b.Type(spv::OpTypeFunction,void_t),label=b.AllocateId();
 b.AddFunction(spv::OpFunction,void_t,fn,spv::FunctionControlMaskNone,fn_t);b.AddFunction(spv::OpLabel,label);
 auto x=Coord(s,0),y=Coord(s,1);auto xf=b.AllocateId(),yf=b.AllocateId();
 b.AddFunction(spv::OpBitcast,f,xf,x);b.AddFunction(spv::OpBitcast,f,yf,y);
 b.AddFunction(spv::OpStore,outputs[0],xf);b.AddFunction(spv::OpStore,outputs[1],yf);
 auto half=b.Constant(spv::OpConstant,f,std::bit_cast<uint32_t>(0.5f)),one=b.Constant(spv::OpConstant,f,std::bit_cast<uint32_t>(1.f));
 b.AddFunction(spv::OpStore,outputs[2],half);b.AddFunction(spv::OpStore,outputs[3],one);
 b.AddFunction(spv::OpReturn);b.AddFunction(spv::OpFunctionEnd);
 outputs.push_back(s.input);b.AddEntryPoint(spv::ExecutionModelFragment,fn,"main",outputs);b.AddExecutionMode(fn,spv::ExecutionModeOriginUpperLeft);
 auto code=b.Build();std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<char*>(code.data()),code.size()*4);
}
