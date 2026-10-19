#!/usr/bin/env python3
"""Execute production presentation selection and disk-cache directory policy."""
from pathlib import Path
import subprocess,sys,tempfile,os
r=Path(sys.argv[1])
s=(r/'src/common/emulatorConfig.cpp').read_text();start=s.index('PresentMode GetPresentMode() {');end=s.index('\nint32_t GetGpuIndex()',start)
getter=s[start:end]
s=(r/'src/graphics/host_gpu/renderer/pipeline/novaShaderDisk.h').read_text();start=s.index('inline std::filesystem::path Directory(');end=s.index('inline std::filesystem::path File(',start)
directory=s[start:end]
code='''#include <filesystem>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <cassert>
#include <string>
enum class PresentMode { Fifo, Mailbox, Immediate };
struct Options { PresentMode present_mode=PresentMode::Mailbox; } config;
Options* g_config=&config;
unsigned long long XXH3_64bits(const void*,size_t) {return 42;}
'''+getter+directory+'''int main(){
unsetenv("NOVA_PRESENT_MODE"); assert(GetPresentMode()==PresentMode::Mailbox);
setenv("NOVA_PRESENT_MODE","fifo",1);assert(GetPresentMode()==PresentMode::Fifo);
setenv("NOVA_PRESENT_MODE","immediate",1);assert(GetPresentMode()==PresentMode::Immediate);
setenv("NOVA_PRESENT_MODE","invalid",1);assert(GetPresentMode()==PresentMode::Mailbox);
setenv("NOVA_PRESENT_MODE","mailbox",1);assert(GetPresentMode()==PresentMode::Mailbox);
unsetenv("NOVA_SHADER_CACHE");assert(!Directory("driver","PPSA04703").empty());
setenv("NOVA_SHADER_CACHE","0",1);assert(Directory("driver","PPSA04703").empty());
setenv("NOVA_SHADER_CACHE","1",1);assert(!Directory("driver","PPSA04703").empty());
assert(Directory("driver","").empty());
assert(Directory("driver","PPSA04703")!=Directory("driver","PPSA15552"));
}'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.cpp').write_text(code)
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 subprocess.run(['g++','-std=c++20','-D__ANDROID__=1','-D__aarch64__=1',*flags,str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Graphics settings production selection tests passed')
