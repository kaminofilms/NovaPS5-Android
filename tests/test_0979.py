from pathlib import Path
import subprocess,tempfile,os,sys
r=Path(sys.argv[1])/'src'
s=(r/'graphics/guest_gpu/graphicsRun.cpp').read_text();a=s.index('template <typename Scheduler>\nstatic void NovaPeriodicSubmit');b=s.index('\nvoid CommandProcessor::DrawIndex',a);periodic=s[a:b]
s=(r/'kernel/semaphore.cpp').read_text();a=s.index('KernelSemaPrivate::Result KernelSemaPrivate::Signal(');b=s.index('\nvoid KernelSemaPrivate::AddWaiter',a);signal=s[a:b]
a=s.index('bool KernelSemaPrivate::WakeWaiters()');b=s.index('\nKernelSemaPrivate::Result KernelSemaPrivate::Wait',a);wake=s[a:b]
fixture='''#include <algorithm>
#include <cstdint>
#include <vector>
#include <cassert>
namespace NovaSync {uint32_t every=1024;uint32_t SubmitEveryDraws(){return every;}}
struct Buffer {bool active=true;bool NovaRendering(){return active;}};
struct Scheduler {Buffer b;unsigned flushes=0;Buffer& Current(){return b;}void Flush(){++flushes;}};
namespace Common {struct LockGuard {explicit LockGuard(int&) {}};}
struct KernelSemaPrivate {
 enum class Result {Ok,Deleted,InvalCount};enum class Status {Set,Deleted};
 struct Waiter {bool ready=false;int need_count=1;Result result=Result::Deleted;};
 struct Cond {int broadcasts=0;void SignalAll(){++broadcasts;}} m_cond_var;
 int m_mutex=0,m_count=0,m_max_count=100;Status m_status=Status::Set;
 std::vector<Waiter*> m_waiting_threads;
 Result Signal(int);bool WakeWaiters();
};
'''+periodic+signal+wake+'''
int main(){
 Scheduler s;
 for(int i=0;i<4095;++i)NovaPeriodicSubmit(s);assert(s.flushes==0);
 NovaPeriodicSubmit(s);assert(s.flushes==1);
 s.b.active=false;for(int i=0;i<1024;++i)NovaPeriodicSubmit(s);assert(s.flushes==2);
 NovaSync::every=0;for(int i=0;i<10000;++i)NovaPeriodicSubmit(s);assert(s.flushes==2);
 KernelSemaPrivate sem;
 assert(sem.Signal(1)==KernelSemaPrivate::Result::Ok);assert(sem.m_cond_var.broadcasts==0);
 KernelSemaPrivate::Waiter first,second;second.need_count=2;
 sem.m_count=0;sem.m_waiting_threads={&first,&second};
 sem.Signal(1);assert(first.ready&&!second.ready&&sem.m_count==0&&sem.m_cond_var.broadcasts==1);
 sem.Signal(1);assert(!second.ready&&sem.m_count==1&&sem.m_cond_var.broadcasts==1);
 sem.Signal(1);assert(second.ready&&sem.m_count==0&&sem.m_cond_var.broadcasts==2);
 sem.Signal(1);assert(sem.m_cond_var.broadcasts==2);
 sem.m_status=KernelSemaPrivate::Status::Deleted;assert(sem.Signal(1)==KernelSemaPrivate::Result::Deleted);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'test.cpp';p.write_text(fixture);exe=Path(d)/'test'
 subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',str(p),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS="detect_leaks=0"))
print('PASS actual periodic-submit and semaphore Signal/WakeWaiters bodies; sanitizer checks')
