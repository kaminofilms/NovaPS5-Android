#!/usr/bin/env python3
"""Execute the production FP16 classification IR against all half encodings."""
from pathlib import Path
import subprocess, sys, tempfile
source = (Path(sys.argv[1]) / 'src/graphics/shader/recompiler/frontend/translate/Float.cpp').read_text()
start = source.index('const auto bits     = ReadU16LaneAsU32(operand, high, false);')
end = source.index('\n\t\t};', start)
body = source[start:end]
program = r'''
#include <cstdint>
#include <utility>
#include <cstdio>
namespace IR { using Value=uint32_t; using U32=uint32_t; }
struct IRInterpreter {
 uint32_t BitwiseAnd(uint32_t a,uint32_t b){return a&b;}
 uint32_t BitwiseOr(uint32_t a,uint32_t b){return a|b;}
 bool IEqual(uint32_t a,uint32_t b){return a==b;}
 bool INotEqual(uint32_t a,uint32_t b){return a!=b;}
 bool LogicalAnd(bool a,bool b){return a&&b;}
} ir;
uint32_t ReadU16LaneAsU32(uint32_t operand,bool high,bool){return high?operand>>16:operand&65535u;}
auto classify(uint32_t operand,bool high){
''' + body + r'''
}
int main(){
 for(uint32_t half=0;half<65536;half++)for(bool high:{false,true}){
  uint32_t packed=high?(half<<16)|0x7c01u:half|0x7c010000u;
  const auto result=classify(packed,high);
  uint32_t magnitude=half&32767u;
  const bool nan=magnitude>31744u;
  const bool signaling=nan && ((half>>9)&1u)==0;
  if(result.first!=signaling || result.second!=(half|512u)){
   std::fprintf(stderr,"half=0x%x high=%d signaling=%d expected=%d\n",half,high,result.first,signaling);return 1;
  }
 }
 std::puts("FP16 signaling-NaN classification: PASS (131072 lane/encoding cases)");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory); (path/'test.cpp').write_text(program)
    subprocess.run(['g++','-std=c++20','-O2','-Wall','-Wextra','-Werror',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
