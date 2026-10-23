#!/usr/bin/env python3
"""Execute the production DPP predicate emitter against a scalar SPIR-V interpreter."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
cache = (root / 'src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp').read_text()
if 'NovaPC26:' in cache or cache.count('NovaPC65DPP:') != 1:
    raise SystemExit('DPP shader semantics must use a fresh cache signature')
emitter = (root / 'src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp').read_text()
start = emitter.index('uint32_t EmitDppWriteCondition(')
end = emitter.index('\nuint32_t ', start + 10)
function = emitter[start:end]
translator = (root / 'src/graphics/shader/recompiler/frontend/translate/Translate.cpp').read_text()
start = translator.index('const auto old = ir.GetVectorReg(reg);')
match = re.search(r'if \((.*?)\) \{', translator[start:], re.S)
if not match:
    raise SystemExit('Missing production vector write predicate')
condition = match.group(1)
program = r'''
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <vector>
namespace spv { enum Op { OpBitFieldUExtract, OpLogicalAnd, OpINotEqual }; }
namespace IR {
enum class Type { U32 };
struct DppMoveFlags { uint32_t control, row_mask, bank_mask; bool fetch_inactive, bound_control, dpp8; };
}
struct State {
 uint32_t lane = 0; bool valid = true;
 std::vector<uint32_t> values{0};
 uint32_t add(uint32_t value) { values.push_back(value); return uint32_t(values.size()-1); }
};
struct ValueEmitContext { State& state; };
uint32_t ConstantU32(State& s,uint32_t v){return s.add(v);}
uint32_t TypeBool(State&){return 0;}
uint32_t EmitSubgroupLocalInvocationId(State& s){return s.add(s.lane);}
template<spv::Op op, IR::Type type>
uint32_t EmitNative(State& s,uint32_t a,uint32_t b,uint32_t c){
 (void)type; static_assert(op==spv::OpBitFieldUExtract);
 const auto width=s.values[c];
 return s.add((s.values[a]>>s.values[b])&((1u<<width)-1u));
}
uint32_t Binary(State& s,spv::Op op,uint32_t,uint32_t a,uint32_t b){
 if(op==spv::OpLogicalAnd)return s.add(s.values[a]&&s.values[b]);
 if(op==spv::OpINotEqual)return s.add(s.values[a]!=s.values[b]);
 throw std::runtime_error("Unexpected SPIR-V operation");
}
struct Target {uint32_t valid;};
Target EmitDppTargetLane(State& s,const IR::DppMoveFlags&){return {s.add(s.valid)};}
''' + function + r'''
struct Operand {bool dpp,dpp_bound_ctrl,dpp8;uint32_t dpp_row_mask,dpp_bank_mask;};
bool preserves_old(const Operand& operand) { return CONDITION; }
int main(){
 if(preserves_old({true,true,false,15,15}) || preserves_old({true,false,true,15,15}))return 1;
 if(!preserves_old({true,false,false,15,15}) || !preserves_old({true,true,false,7,15}))return 2;
 unsigned long long cases=0;
 for(uint32_t bank=0;bank<16;bank++)for(uint32_t row=0;row<16;row++)
 for(uint32_t lane=0;lane<64;lane++)for(uint32_t control:{0u,0x100u,0x101u,0x10fu,0x110u,0x111u,0x11fu,0x120u,0x140u})
 for(bool bound:{false,true})for(bool exec:{false,true})for(bool valid:{false,true}){
  State s; s.lane=lane;s.valid=valid; ValueEmitContext ctx{s};
  IR::DppMoveFlags f{control,row,bank,false,bound,false};
  auto result=EmitDppWriteCondition(ctx,f,s.add(exec));
  const bool mask = (bank & (1u<<((lane/4)%4))) && (row & (1u<<(lane/16)));
  const bool vacating = (control>=0x101u && control<=0x10fu)||(control>=0x111u && control<=0x11fu);
  const bool expected=exec&&mask&&(bound||!vacating||valid);
  if(bool(s.values[result])!=expected){std::fprintf(stderr,"DPP mismatch lane=%u control=%x\n",lane,control);return 3;}
  ++cases;
 }
 std::printf("DPP production emitter: PASS (%llu mask/lane/boundary cases)\n",cases);
}
'''
program = program.replace('CONDITION', condition)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.cpp').write_text(program)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('SANITIZE') == '1' else []
    subprocess.run(['g++', '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', *flags,
                    str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
