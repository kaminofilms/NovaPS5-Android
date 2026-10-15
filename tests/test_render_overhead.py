#!/usr/bin/env python3
from pathlib import Path
import subprocess,tempfile,sys
root=Path(sys.argv[1])/'src/graphics/host_gpu/renderer'
def extract(s,signature):
    start=s.index(signature);pos=s.index('{',start);depth=1;end=pos+1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return s[start:end]
flush=extract((root/'commandScheduler.cpp').read_text(),'void CommandScheduler::Flush(SubmitInfo& submit)')
bind=extract((root/'context.cpp').read_text(),'void CommandBuffer::BindPipeline(')
cpp=r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <mutex>
#include <queue>
#include <cstdio>
namespace vk {enum class PipelineBindPoint{eGraphics,eCompute};using Pipeline=uint64_t;}
struct CommandBuffer {
 bool m_has_commands=false;bool invalid=false;int binds=0;
 std::array<vk::Pipeline,2> m_bound_pipelines{};
 bool IsInvalid(){return invalid;}
 CommandBuffer& Handle(){m_has_commands=true;return *this;}
 void bindPipeline(vk::PipelineBindPoint,vk::Pipeline){++binds;}
 void BindPipeline(vk::PipelineBindPoint point,vk::Pipeline pipeline);
};
struct SubmitInfo {unsigned num_wait_semaphores=0,num_signal_semaphores=0;};
struct CommandScheduler {
 CommandBuffer m_command;std::mutex m_operation_mutex;
 std::queue<int> m_pending_operations,m_priority_operations;bool m_priority_active=false;
 int submits=0,begins=0;
 void Submit(SubmitInfo&){++submits;}
 void BeginNext(){++begins;}
 void Flush(SubmitInfo& submit);
};
'''+flush+'\n'+bind+r'''
int main(){
 for(unsigned bits=0;bits<64;++bits){
  CommandScheduler s;SubmitInfo info;
  s.m_command.m_has_commands=bits&1;info.num_wait_semaphores=bool(bits&2);info.num_signal_semaphores=bool(bits&4);
  if(bits&8)s.m_pending_operations.push(1);if(bits&16)s.m_priority_operations.push(1);s.m_priority_active=bits&32;
  s.Flush(info);assert(s.submits==(bits?1:0));assert(s.begins==s.submits);
 }
 CommandBuffer b;
 for(unsigned i=0;i<1000;++i)b.BindPipeline(vk::PipelineBindPoint::eGraphics,1);
 assert(b.binds==1);b.BindPipeline(vk::PipelineBindPoint::eGraphics,2);assert(b.binds==2);
 b.BindPipeline(vk::PipelineBindPoint::eCompute,2);assert(b.binds==3);
 b.BindPipeline(vk::PipelineBindPoint::eGraphics,2);assert(b.binds==3);
 b.m_bound_pipelines={};b.BindPipeline(vk::PipelineBindPoint::eGraphics,2);assert(b.binds==4);
 std::puts("RENDER_OVERHEAD_TEST: all 64 submit-boundary combinations and pipeline bind isolation PASS");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(cpp)
 subprocess.run(['c++','-std=c++20','-O2','-fsanitize=undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
