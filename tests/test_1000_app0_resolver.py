#!/usr/bin/env python3
"""Host test of patch 1000: the cached /app0 resolver (extracted from the patched fileSystem.cpp)
gives the same result as the uncached case-insensitive resolver for hits, case variants, misses,
paths through a file and '..' paths, and keeps a directory listing once taken."""
from pathlib import Path
import subprocess, sys, tempfile
s = (Path(sys.argv[1]) / 'src/kernel/fileSystem.cpp').read_text()
body = s[s.index('// Resolve guest paths case-insensitively on case-sensitive hosts.'):s.index('#else\nstatic bool HasWindowsForbiddenFilenameCharacter(')]
HEAD = r'''#include <filesystem>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <fstream>
namespace Common { inline bool EqualNoCase(std::string_view a, std::string_view b){ if(a.size()!=b.size())return false; for(size_t i=0;i<a.size();i++) if(std::tolower((unsigned char)a[i])!=std::tolower((unsigned char)b[i]))return false; return true;} }
'''
MAIN = r'''int main(){
 namespace fs=std::filesystem; auto r=fs::temp_directory_path()/"nova1000"; fs::remove_all(r);
 fs::create_directories(r/"HellbladeGame/Config"); std::ofstream(r/"HellbladeGame/Config/DefaultGame.ini")<<"x";
 std::ofstream(r/"Exact.txt")<<"y";
 auto ok=[&](const char* rel, fs::path want){ auto got=NovaResolveReadOnly(r,rel); auto ref=ResolvePathIgnoringCase(r/rel); assert(got==want); assert(got==ref); };
 ok("hellbladegame/config/defaultgame.ini", r/"HellbladeGame/Config/DefaultGame.ini");
 ok("Exact.txt", r/"Exact.txt");
 ok("hellbladegame/config/missing.ini", r/"HellbladeGame/Config/missing.ini");
 ok("nothere/a/b.ini", r/"nothere/a/b.ini");
 ok("exact.txt/below", r/"Exact.txt/below");
 assert(NovaResolveReadOnly(r,"hellbladegame/../Exact.txt")==ResolvePathIgnoringCase(r/"hellbladegame/../Exact.txt"));
 // Listing is cached: a file added afterwards to a listed directory is not seen (read-only /app0 contract).
 std::ofstream(r/"HellbladeGame/Config/Late.ini")<<"z";
 assert(NovaResolveReadOnly(r,"hellbladegame/config/late.ini")==r/"HellbladeGame/Config/late.ini");
 std::puts("PASS app0 cached resolver matches the uncached resolver for hits, misses, files-as-dirs and ..");
}
'''
with tempfile.TemporaryDirectory() as d:
    src = Path(d) / 't.cpp'
    src.write_text(HEAD + body + MAIN)
    subprocess.run(['c++', '-std=c++20', '-Wall', str(src), '-o', str(Path(d) / 't')], check=True)
    subprocess.run([str(Path(d) / 't')], check=True)
