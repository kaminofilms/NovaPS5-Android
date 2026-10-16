#!/usr/bin/env python3
"""Execute the production priority queue and stream reuse methods with a controlled
timeline. This is host ordering coverage, not Vulkan/Turnip/device validation.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root=Path(sys.argv[1])/'src/graphics/host_gpu/renderer'
s=(root/'commandScheduler.cpp').read_text()
methods=s[s.index('void CommandScheduler::DeferPriorityOperation('):s.index('\nbool CommandScheduler::IsFree(')]
stream=(root/'cache/streamBuffer.cpp').read_text()
reuse=stream[stream.index('bool StreamBuffer::WaitPendingOperations('):stream.index('\n} // namespace Libs::Graphics')]
pre=r'''
#include "novaRenderCosts.h"
#include <cassert>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <optional>
#include <queue>
#include <thread>
#include <vector>
#include <atomic>
#include <stdexcept>
#define EXIT_IF(c) do { if(c) throw std::runtime_error("invalid operation"); } while(0)
namespace Common {template<class R> using UniqueFunction = std::move_only_function<R()>;}
class CommandScheduler;
thread_local CommandScheduler* g_deferred_callback_scheduler=nullptr;
struct Master {
 std::mutex lock; std::condition_variable cv; uint64_t tick=0;
 void Wait(uint64_t t){std::unique_lock l(lock);cv.wait(l,[&]{return tick>=t;});}
 void Complete(uint64_t t){{std::lock_guard l(lock);tick=t;}cv.notify_all();}
 bool Free(uint64_t t){std::lock_guard l(lock);return tick>=t;}
};
class CommandScheduler {
public:
 enum class OperationState {Open,Draining,Closed};
 struct PendingOperation {Common::UniqueFunction<void> callback;uint64_t tick=0;NovaRender::ReadbackTicket telemetry {};};
 Master m_master;
 std::mutex m_operation_mutex;
 std::condition_variable m_operation_available;
 std::queue<PendingOperation> m_priority_operations,m_pending_operations;
 bool m_priority_active=false;uint64_t m_priority_active_tick=0;
 OperationState m_operation_state=OperationState::Open;
 uint64_t CurrentTick(){return 1;}
 void CheckActive(){}
 bool IsFree(uint64_t t){return m_master.Free(t);}
 void Wait(uint64_t t){m_master.Wait(t);}
 void DeferPriorityOperation(Common::UniqueFunction<void>&&,NovaRender::ReadbackTicket = {});
 void QueueOperation(Common::UniqueFunction<void>&&,bool,NovaRender::ReadbackTicket = {});
 bool HasPendingPriorityOperations();
 void PriorityOperationsThread(std::stop_token);
 void DrainPriorityOperations();
 void WaitPriorityOperations(uint64_t);
 void RunOperation(Common::UniqueFunction<void>&&);
};
enum class MemoryUsage {Download,Upload};
struct StreamBuffer {
 struct Watch {uint64_t tick,upper_bound;};
 CommandScheduler& scheduler; MemoryUsage usage=MemoryUsage::Download;
 CommandScheduler& Scheduler(){return scheduler;}
 MemoryUsage Usage(){return usage;}
 bool WaitPendingOperations(const std::vector<Watch>&,std::optional<size_t>,uint64_t,bool,size_t&,uint64_t&);
};
'''
post=r'''
int main(){
 CommandScheduler scheduler;
 std::mutex phase_lock;std::condition_variable phase_cv;
 bool entered=false,allow_publish=false;
 std::atomic<unsigned> guest{0},label{0};
 std::atomic<bool> reused=false,cpu_write_done=false;
 scheduler.DeferPriorityOperation([&]{
   {std::unique_lock l(phase_lock);entered=true;phase_cv.notify_all();phase_cv.wait(l,[&]{return allow_publish;});}
   guest.store(7,std::memory_order_release); // GPU snapshot host-to-guest publication.
 },{NovaRender::ReadbackCaller::GarbageCollection,true});
 scheduler.DeferPriorityOperation([&]{
   assert(guest.load(std::memory_order_acquire)==7);
   label.store(1,std::memory_order_release);
 });
 std::jthread runner([&](std::stop_token stop){scheduler.PriorityOperationsThread(stop);});
 assert(guest==0 && label==0);
 scheduler.m_master.Complete(1); // GPU is done; host publication remains blocked.
 {std::unique_lock l(phase_lock);phase_cv.wait(l,[&]{return entered;});}
 assert(guest==0 && label==0 && scheduler.HasPendingPriorityOperations());
 StreamBuffer ring{scheduler};
 std::thread allocator([&]{size_t cursor=0;uint64_t bound=0;
   assert(ring.WaitPendingOperations({{1,64}},1,64,true,cursor,bound));
   assert(guest.load(std::memory_order_acquire)==7 && bound==64 && cursor==1);
   reused.store(true,std::memory_order_release);
 });
 // Simulate the CPU-write caller's production WaitPriorityOperations barrier.
 // The surrounding memory tracker/fault manager is covered by source contracts.
 std::thread cpu([&]{scheduler.WaitPriorityOperations(1);
   guest.store(9,std::memory_order_release);cpu_write_done.store(true,std::memory_order_release);
 });
 // Deterministic state check while the publication callback is paused.
 assert(!reused && !cpu_write_done && label==0);
 {std::lock_guard l(phase_lock);allow_publish=true;}phase_cv.notify_all();
 allocator.join();cpu.join();scheduler.DrainPriorityOperations();
 assert(label.load(std::memory_order_acquire)==1 && guest.load(std::memory_order_acquire)==9);
 runner.request_stop();scheduler.m_operation_available.notify_all();runner.join();
 puts("NOVA_READBACK_ORDER: production queue active/queued barriers, GPU-before-memcpy-before-label, allocator reuse and later CPU write PASS");
}
'''
# Ring reuse and CPU write may race *after* completion; the allocator observes only
# completion, never the particular guest value after a subsequent authorized write.
post=post.replace('guest.load(std::memory_order_acquire)==7 && bound==64 && cursor==1',
                  'label.load(std::memory_order_acquire)==1 && bound==64 && cursor==1')
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'ordering.cpp';p.write_text(pre+methods+reuse+post)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
    subprocess.run(['g++','-std=c++23','-O1','-g','-pthread','-Wall','-Wextra','-Werror',*flags,
                    '-I'+str(root),str(p),'-o',str(Path(d)/'ordering')],check=True)
    for _ in range(10):subprocess.run([str(Path(d)/'ordering')],check=True,timeout=20)
