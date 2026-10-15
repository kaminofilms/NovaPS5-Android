#!/usr/bin/env python3
"""Execute the production signal-safe tracker beyond its old 48-site limit."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo/'native/novafex/novafex.cpp').read_text()
tracker = source[source.index('constexpr int kEmuSites'):source.index('// Names a host code address')]
program = r'''
#include <atomic>
#include <cstdint>
#include <thread>
#include <vector>
#include <cassert>
#include <cstdio>
''' + tracker + r'''
int main() {
 for(unsigned i=0;i<512;++i) NoteHostEmulation(0x7100000000ull+4*i);
 const uint64_t late=0x714abcdef0ull;
 std::vector<std::thread> workers;
 for(int i=0;i<4;++i) workers.emplace_back([=]{for(int j=0;j<100000;++j)NoteHostEmulation(late);});
 for(auto& w:workers)w.join();
 uint64_t late_count=0,total=0;
 for(int i=0;i<kEmuSites;++i){total+=g_emu_site_count[i].load();if(g_emu_site_pc[i]==late)late_count+=g_emu_site_count[i].load();}
 assert(late_count==400000 && g_host_emulated==400512 && total==400512 && g_emu_untracked==0);
 // Force capacity/probe exhaustion: totals must remain exact even when slots fill.
 for(unsigned i=0;i<8192;++i) NoteHostEmulation(0x7300000000ull+4*i);
 total=0;for(int i=0;i<kEmuSites;++i)total+=g_emu_site_count[i].load();
 assert(g_emu_untracked>0 && total+g_emu_untracked.load()==g_host_emulated.load());
 puts("Host access tracking: PASS late hot site, concurrent counts, bounded overflow accounting");
}
'''
with tempfile.TemporaryDirectory() as d:
    cpp, exe = Path(d)/'test.cpp', Path(d)/'test'
    cpp.write_text(program)
    subprocess.run(['g++','-std=c++20','-O2','-pthread',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
