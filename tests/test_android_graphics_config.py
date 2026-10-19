#!/usr/bin/env python3
"""Compile the complete production config translation unit without forced
KYTY_NOVA_FEX. This catches the include-order bug missed by extracted getters.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1])
main=r'''
#include "common/emulatorConfig.h"
#include <cassert>
#include <cstdlib>
int main(){
#ifdef KYTY_NOVA_FEX
#error This test must not force the NovaFEX macro
#endif
    Config::Initialize(); Config::ConfigOptions cfg;
    cfg.guest_arguments={"existing"};cfg.present_mode=Config::PresentMode::Mailbox;
    Config::Load(cfg);
    const auto& args=Config::GetGuestArguments();
#if defined(__ANDROID__) && defined(__aarch64__)
    assert(Config::GetPresentMode()==Config::PresentMode::Fifo);
    if(std::string(std::getenv("NOVA_CACHE_TITLE_ID"))=="PPSA04703") {
        assert(args.size()==5&&args[0]=="existing"&&args[1]=="-screen-width"&&args[2]=="960"&&args[3]=="-screen-height"&&args[4]=="540");
    } else assert(args==cfg.guest_arguments);
#else
    assert(Config::GetPresentMode()==Config::PresentMode::Mailbox);
    assert(args==cfg.guest_arguments);
#endif
    assert(Config::GetScreenWidth()==cfg.screen_width&&Config::GetScreenHeight()==cfg.screen_height);
    Config::Shutdown();
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'common').mkdir()
 (p/'common/assert.h').write_text('#pragma once\n#include <cstdlib>\n#define EXIT_IF(x) do{if(x)std::abort();}while(0)\n')
 (p/'cmake_config.h').write_text('#define KYTY_PLATFORM 5\n#define KYTY_BUILD 2\n#define KYTY_COMPILER 1\n#define KYTY_LINKER 1\n#define KYTY_ENDIAN 2\n')
 (p/'main.cpp').write_text(main)
 sanitize=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
 for arch in [[],['-D__ANDROID__=1','-D__aarch64__=1']]:
    subprocess.run(['g++','-std=c++20',*sanitize,*arch,'-I',str(p),'-I',str(r/'src'),str(r/'src/common/emulatorConfig.cpp'),str(p/'main.cpp'),'-o',str(p/'test')],check=True)
    for title in ['PPSA04703','PPSA15552']:
        subprocess.run([str(p/'test')],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title,NOVA_UNITY_RESOLUTION='540',NOVA_PRESENT_MODE='fifo'),check=True)
print('Complete config TU: Android request/presentation enabled, desktop/default dimensions/other titles preserved')
