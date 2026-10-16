#!/usr/bin/env python3
"""Exercise production MRU lookup, bounded writer, and inclusive timing scopes."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
renderer = root / 'src/graphics/host_gpu/renderer'
source = (renderer / 'pipeline/pipelineCache.cpp').read_text()
begin = source.index('\t\ttemplate <bool HasCalls>')
end = source.index('\n\t\tstd::unique_ptr<ShaderRecompiler::ShaderSource>', begin)
method = source[begin:end]
assert 'MaterializeResources' in method and 'last_permutation = index' in method
assert 'entry->second.last_permutation = entry->second.permutations.size() - 1;' in source
begin = source.index('\tauto write = [path = m_driver_cache_path')
end = source.index('\n\t};', begin)
writer_body = source[begin:end]
assert 'm_graphics' not in writer_body and 'this' not in writer_body
assert 'file.Flush()' in writer_body and 'RenameFile' in writer_body
assert source.index('m_snapshot_writer.Drain()') < source.index('auto write = [path =')

prefix = r'''
#include "novaLatestTask.h"
#include "novaRenderCosts.h"
#include <algorithm>
#include <cassert>
#include <future>
#include <vector>
#include <iostream>
#define EXIT_IF(x) assert(!(x))
namespace ShaderRecompiler::IR {
struct SrtRuntime { int key, payload; };
struct ResourceSnapshot { int payload = 0; };
struct ResourceSpecialization {
 int key = 0;
 static inline int comparisons = 0;
 bool operator!=(const ResourceSpecialization& other) const {
  ++comparisons; return key != other.key;
 }
};
struct PushData { static unsigned StartFor(unsigned start, unsigned words) {return start + words;} };
bool MaterializeResources(int, const SrtRuntime& runtime, ResourceSnapshot& resources,
                          ResourceSpecialization& specialization) {
 resources.payload = runtime.payload; specialization.key = runtime.key; return true;
}
}
struct Bindings { unsigned push_data_start_dword = 0; unsigned ShaderDataDwords() const {return 0;} };
struct Permutation {
 struct { Bindings bindings; } program;
 ShaderRecompiler::IR::ResourceSpecialization specialization;
 std::vector<int> function_code;
};
struct SourceEntry {
 int resource_plan = 0;
 ShaderRecompiler::IR::ResourceSnapshot resources;
 ShaderRecompiler::IR::ResourceSpecialization specialization;
 std::vector<Permutation> permutations;
 size_t last_permutation = 0;
 std::vector<int> function_code;
 const auto& FunctionCode() const { return function_code; }
'''
suffix = r'''
};
int main() {
 using namespace ShaderRecompiler::IR;
 SourceEntry entry;
 assert(!entry.FindPermutation<false>({0,1},0));
 for (int i=0; i<128; ++i) entry.permutations.push_back({{}, {i}, {i}});
 // First lookup at the tail still checks every candidate. A stable repeat
 // checks one but must materialize the current runtime resource payload.
 assert(entry.FindPermutation<false>({127,7},0)==&entry.permutations[127]);
 assert(entry.resources.payload==7);
 ResourceSpecialization::comparisons=0;
 assert(entry.FindPermutation<false>({127,99},0)==&entry.permutations[127]);
 assert(ResourceSpecialization::comparisons==1 && entry.resources.payload==99);
 for(int i=0;i<128;++i) {
  auto* p=entry.FindPermutation<false>({i,100+i},0);
  assert(p==&entry.permutations[i] && entry.last_permutation==size_t(i));
 }
 assert(!entry.FindPermutation<false>({999,0},0));
 assert(!entry.FindPermutation<false>({127,0},1)); // push-data layout still checked
 entry.function_code={126};
 assert(!entry.FindPermutation<true>({127,0},0)); // callee code still checked
 entry.function_code={127};
 assert(entry.FindPermutation<true>({127,0},0)==&entry.permutations[127]);
 for (int i=128;i<2048;++i) entry.permutations.push_back({{}, {i}, {i}});
 assert(entry.FindPermutation<false>({127,42},0)==&entry.permutations[127]);
 assert(entry.resources.payload==42); // vector reallocation cannot stale the MRU

 std::promise<void> executing, release;
 auto allowed=release.get_future().share();
 std::vector<int> results;
 {
  NovaRender::LatestTask writer;
  writer.Post([&] { executing.set_value(); allowed.wait(); results.push_back(0); });
  executing.get_future().wait();
  for(int i=1;i<=100;++i) writer.Post([&,i] {results.push_back(i);});
  auto draining=std::async(std::launch::async,[&] {writer.Drain();});
  assert(draining.wait_for(std::chrono::milliseconds(10))==std::future_status::timeout);
  release.set_value(); draining.get();
  assert((results==std::vector<int>{0,100}));
  writer.Post([&] {results.push_back(101);});
 } // shutdown must drain final work before destroying captures
 assert((results==std::vector<int>{0,100,101}));
 {
  NovaRender::Scope outer(NovaRender::Cost::Draw);
  { NovaRender::Scope inner(NovaRender::Cost::Shader); }
  assert(NovaRender::costs.depth==1);
 }
 assert(NovaRender::costs.depth==0);
 assert(NovaRender::costs.entries[unsigned(NovaRender::Cost::Shader)].calls==1);
 NovaRender::costs.begin-=std::chrono::seconds(6);
 { NovaRender::Scope s(NovaRender::Cost::Draw); }
 assert(NovaRender::costs.entries[unsigned(NovaRender::Cost::Draw)].calls==0);
 std::puts("NOVA_EVER_TEST: exact lookup/reallocation/resources/callees, bounded latest writer/drain, timing PASS");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p = Path(directory)
    (p/'test.cpp').write_text(prefix + method + suffix)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('SANITIZE') == '1' else []
    subprocess.run(['c++', '-std=c++20', '-O1', '-g', '-pthread', *flags, '-I'+str(renderer),
                    str(p/'test.cpp'), '-o', str(p/'test')], check=True)
    result = subprocess.run([str(p/'test')], text=True, capture_output=True)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    result.check_returncode()
    assert 'scope=shader calls=1' in result.stderr and 'scope=draw calls=2' in result.stderr
