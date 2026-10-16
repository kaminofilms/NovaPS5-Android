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
 assert(ResourceSpecialization::comparisons==(NovaRender::EverProfile()?1:128) && entry.resources.payload==99);
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
schedule_source = (renderer/'commandScheduler.cpp').read_text()
finish = schedule_source[schedule_source.index('void CommandScheduler::Finish() {'):schedule_source.index('\nvoid CommandScheduler::Wait(uint64_t tick)')]
finish_prefix = r'''
#include "novaRenderCosts.h"
#include <cassert>
#include <mutex>
#include <queue>
struct CommandScheduler {
 struct Command { bool invalid=false,m_has_commands=false;bool IsInvalid()const{return invalid;} } m_command;
 struct Master {
  uint64_t current=6,done=5,waited=0;
  bool IsFree(uint64_t tick)const{return tick<=done;}
  void Wait(uint64_t tick){waited=tick;done=tick;}
 }m_master;
 std::mutex m_operation_mutex;
 std::queue<int>m_pending_operations,m_priority_operations;
 bool m_priority_active=false;
 int submits=0,begins=0,pops=0;
 uint64_t CurrentTick()const{return m_master.current;}
 void CheckActive()const{}
 void Submit(){++submits;++m_master.current;m_command.invalid=true;}
 void BeginNext(){++begins;m_command.invalid=false;m_command.m_has_commands=false;}
 void PopPendingOperations(){++pops;}
 void Finish();
};
'''
finish_suffix = r'''
int main(){
 for(unsigned flags=0;flags<32;++flags){
  CommandScheduler s;
  s.m_command.m_has_commands=flags&1;
  if(flags&2)s.m_pending_operations.push(1);
  if(flags&4)s.m_priority_operations.push(1);
  s.m_priority_active=flags&8;
  if(flags&16)s.m_master.done=4;
  const bool elide=NovaRender::EverProfile()&&flags==0;
  s.Finish();
  assert(s.submits==(elide?0:1));
  assert(s.begins==(elide?0:1) && s.pops==(elide?0:1));
  assert(s.CurrentTick()==(elide?6:7));
  assert(s.m_master.done==(elide?5:6));
 }
 std::puts("NOVA_FINISH_TEST: completed-empty-only elision, real work/callbacks/incomplete ticks retain submit+wait PASS");
}
'''
graphics_source = (root/'src/graphics/guest_gpu/graphicsRun.cpp').read_text()
label_profile = 'GpuLabelProfile' if 'inline bool GpuLabelProfile()' in (renderer/'novaRenderCosts.h').read_text() else 'EverProfile'
assert f'if (!NovaRender::{label_profile}()) (void)command.Handle();' in graphics_source
assert 'if (with_interrupt) m_renderer.TriggerInterrupt' in graphics_source
ring_declarations = graphics_source[graphics_source.index('struct NovaGpuWrite {'):graphics_source.index('std::atomic<uint64_t> g_nova_watch_addr')]
ring_start = graphics_source.index('\tconst auto a = reinterpret_cast<uint64_t>(addr);', graphics_source.index('void NovaNoteGpuWrite'))
ring_body = graphics_source[ring_start:graphics_source.index('\tconst auto watch =', ring_start)]
ring_test = '#include "novaRenderCosts.h"\n#include <cassert>\n#include <mutex>\n#include <vector>\n#include <thread>\n#include <atomic>\n#include <algorithm>\n' + ring_declarations + '\nvoid Note(const void* addr,uint64_t value,uint32_t queue,char kind){\n' + ring_body + r'''
}
int main(){
 const char* title=std::getenv("NOVA_CACHE_TITLE_ID");
 const bool enabled=title&&std::string_view(title)=="PPSA15552";
 for(uint64_t i=0;i<4096+17;++i)Note(reinterpret_cast<void*>(0x1000+i*8),i,3,'E');
 assert(g_nova_write_pos==(enabled?4096+17:0));
 if(enabled){const auto& last=g_nova_writes[(g_nova_write_pos-1)%NOVA_WRITES];assert(last.value==4096+16&&last.kind=='E'&&last.queue==3);}
 std::atomic<bool> stop=false;
 std::thread reader([&]{while(!stop){auto s=NovaSnapshotGpuWrites(4096);assert(s.recent.size()<=4096);for(const auto& w:s.recent){assert(w.addr==0x1000+w.value*8&&w.queue==3&&w.kind=='E');}}});
 std::thread writer([&]{for(uint64_t i=0;i<20000;++i)Note(reinterpret_cast<void*>(0x1000+i*8),i,3,'E');});
 writer.join();stop=true;reader.join();
 assert(g_nova_write_pos==(enabled?4096+17+20000:0));
 std::puts("NOVA_LABEL_HISTORY_TEST: title-scoped bounded producer history/wrap/concurrent snapshots PASS");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p = Path(directory)
    (p/'test.cpp').write_text(prefix + method + suffix)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('SANITIZE') == '1' else []
    subprocess.run(['c++', '-std=c++20', '-O1', '-g', '-pthread', *flags, '-I'+str(renderer),
                    str(p/'test.cpp'), '-o', str(p/'test')], check=True)
    for title in ('PPSA04703', 'PPSA15552', ''):
        env = dict(os.environ, NOVA_CACHE_TITLE_ID=title)
        result = subprocess.run([str(p/'test')], text=True, capture_output=True, env=env)
        print(title or 'no-title', result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        result.check_returncode()
        assert 'scope=shader calls=1' in result.stderr and 'scope=draw calls=2' in result.stderr
    for name, text in [('finish',finish_prefix+finish+finish_suffix),('ring',ring_test)]:
        (p/(name+'.cpp')).write_text(text)
        subprocess.run(['c++','-std=c++20','-O1','-pthread',*flags,'-I'+str(renderer),str(p/(name+'.cpp')),'-o',str(p/name)],check=True)
        for title in ('PPSA04703','PPSA15552',''):
            subprocess.run([str(p/name)],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True)
