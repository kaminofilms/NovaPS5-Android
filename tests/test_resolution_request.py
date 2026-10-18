#!/usr/bin/env python3
"""Test request routing and exact guest-owned argv bytes, not game acceptance."""
from pathlib import Path
import subprocess,sys,tempfile,os
root=Path(sys.argv[1]);header=root/'src/common/novaResolutionRequest.h'
code=r'''
#include "novaResolutionRequest.h"
#include <cassert>
#include <array>
int main(){
    using namespace NovaResolution;
    assert(Parse(nullptr).width==0);
    for(const char* invalid:{"", "0", "-1", "99999999999999999", "540junk", " 540", "720;quit"}) assert(Parse(invalid).width==0);
    for(const auto r:{Request{1920,1080},Request{1280,720},Request{960,540},Request{640,360}}){
        const auto parsed=Parse(std::to_string(r.height).c_str());assert(parsed.width==r.width&&parsed.height==r.height);
        assert(ForTitle("PPSA15552",std::to_string(r.height).c_str()).width==0);
        assert(ForTitle(nullptr,"540").width==0);
        const auto selected=ForTitle("PPSA04703",std::to_string(r.height).c_str());
        std::vector<std::string> args{"game"};Append(args,selected);
        assert(args.size()==5&&args[0]=="game"&&args[1]=="-screen-width"&&args[2]==std::to_string(r.width));
        assert(args[3]=="-screen-height"&&args[4]==std::to_string(r.height));
        size_t size=0;assert(StringBytes(args,size));
        std::vector<char> bytes(size+2, char(0x55));std::array<const char*,6> argv{};
        assert(Copy(args,bytes.data()+1,size,argv.data()));
        assert(bytes.front()==char(0x55)&&bytes.back()==char(0x55)&&argv[5]==nullptr);
        for(size_t i=0;i<args.size();i++){
            assert(argv[i]>=bytes.data()+1&&argv[i]<bytes.data()+size+1);
            assert(std::string(argv[i])==args[i]);
        }
        assert(!Copy(args,bytes.data()+1,size-1,argv.data()));
    }
    std::vector<std::string> original{"", "existing argument"};auto args=original;
    Append(args,{});assert(args==original);
    Append(args,ForTitle("PPSA15552","360"));assert(args==original);
    size_t size=0;assert(StringBytes(args,size));
    std::vector<std::string> bad(129,"x");assert(!StringBytes(bad,size));
    bad={std::string(4096,'x')};assert(!StringBytes(bad,size));
    bad={std::string("x\0y",3)};assert(!StringBytes(bad,size));
    bad=std::vector<std::string>(9,std::string(4095,'x'));assert(!StringBytes(bad,size));
    std::vector<std::string> empty;Append(empty,Parse("540"));assert(empty.front()=="/app0/eboot.bin");
}
'''
# Compile the actual loader stack-layout block as well as the shared helper.
loader=(root/'src/loader/runtimeLinker.cpp').read_text()
start=loader.index('        size_t argument_bytes = 0;')
end=loader.index('\n\t\tLOGF("stack_addr',start)
layout=loader[start:end]
code=code.replace('int main(){', 'void CheckLayout();\nint main(){\n    CheckLayout();')
code+='\nstruct EntryParams { int argc; uint32_t pad; const char* argv[1]; };\n#define EXIT_IF(x) assert(!(x))\nvoid CheckLayout(){\n    alignas(16) std::array<char,65536> stack {};\n    void* main_stack_top=stack.data()+stack.size();\n    std::vector<std::string> arguments {"", "-screen-width", "640", "-screen-height", "360"};\n'+layout+'\n    assert(params->argc==5 && params->pad==0 && params->argv[5]==nullptr);\n    assert((reinterpret_cast<uintptr_t>(params)&15)==0);\n    assert(reinterpret_cast<char*>(params)>stack.data());\n    for(size_t i=0;i<arguments.size();i++) {\n        assert(params->argv[i]>=reinterpret_cast<char*>(params));\n        assert(params->argv[i]<stack.data()+stack.size());\n        assert(std::string(params->argv[i])==arguments[i]);\n    }\n}\n'
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror',*flags,'-iquote',str(header.parent),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Resolution routing and guest argument-copy tests passed; game acceptance requires device measurement')
