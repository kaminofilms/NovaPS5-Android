#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]);pending={}
def edit(name,old,new):
 p=root/name;s=pending.get(p,p.read_text())
 if s.count(old)!=1:raise SystemExit('0979 changed anchor '+name+' '+old[:60])
 pending[p]=s.replace(old,new,1)
g='src/graphics/guest_gpu/graphicsRun.cpp'
edit(g,'''\tif (every != 0 && ++work >= every) {
\t\twork = 0;
\t\tscheduler.Flush();
\t}''','''\tif (every == 0) return;
\t// Only the opportunistic draw-count flush may be delayed. Explicit waits,
\t// flips, guest barriers, ring-wrap retirement and readbacks retain their path.
\t++work;
\tconst uint32_t budget = scheduler.Current().NovaRendering()
\t    ? std::max<uint32_t>(every,4096u) : every;
\tif (work >= budget) { work=0; scheduler.Flush(); }''')
im='src/graphics/host_gpu/renderer/image/image.cpp'
edit(im,'''\t\t\t\tif (subresource_state.layout != destination_layout ||''','''\t\t\t\tif (NovaReadToRead(subresource_state,destination_layout,destination_access)) {
\t\t\t\t\tsubresource_state.pl_stage |= destination_stage;
\t\t\t\t\tsubresource_state.access_mask |= destination_access;
\t\t\t\t\tNovaCountImageBarrier(true);
\t\t\t\t\tcontinue;
\t\t\t\t}
\t\t\t\tif (subresource_state.layout != destination_layout ||''')
# Preserve reader stages even when merging is explicitly disabled.
edit(im,'''\t\t\t\t\tsubresource_state = {destination_stage, destination_access, destination_layout};
\t\t\t\t}
''','''\t\t\t\t\tsubresource_state = {destination_stage, destination_access, destination_layout};
\t\t\t\t} else { subresource_state.pl_stage |= destination_stage; }
''')
se='src/kernel/semaphore.cpp'
edit(se,'\tvoid WakeWaiters();','\tbool WakeWaiters();')
edit(se,'''\tWakeWaiters();

\tm_cond_var.SignalAll();''','''\t// A signal with no newly satisfied waiter needs no condition-variable broadcast.
\t// Keep the broadcast for multiple ready waiters: SignalOne could wake the wrong one.
\tif (WakeWaiters()) m_cond_var.SignalAll();''')
edit(se,'''void KernelSemaPrivate::WakeWaiters() {
\tfor''','''bool KernelSemaPrivate::WakeWaiters() {
\tbool changed = false;
\tfor''')
edit(se,'''\t\t\twaiter->result = Result::Ok;
\t\t\twaiter->ready  = true;
\t\t}
\t}
}

KernelSemaPrivate::Result KernelSemaPrivate::Wait''','''\t\t\twaiter->result = Result::Ok;
\t\t\twaiter->ready  = true;
\t\t\tchanged = true;
\t\t}
\t}
\treturn changed;
}

KernelSemaPrivate::Result KernelSemaPrivate::Wait''')
h='src/graphics/host_gpu/renderer/commandScheduler.h'
edit(h,'\tvoid           Flush();','\tvoid           Flush(std::source_location where = std::source_location::current());')
edit(h,'\tvoid           Flush(SubmitInfo& submit);','\tvoid           Flush(SubmitInfo& submit, std::source_location where = std::source_location::current());')
edit(h,'uint64_t       Submit(SubmitInfo submit = {});','uint64_t       Submit(SubmitInfo submit = {}, std::source_location where = std::source_location::current());')
s='src/graphics/host_gpu/renderer/commandScheduler.cpp'
edit(s,'void CommandScheduler::Flush() {','void CommandScheduler::Flush(std::source_location where) {')
edit(s,'\tFlush(submit);','\tFlush(submit,where);')
edit(s,'void CommandScheduler::Flush(SubmitInfo& submit) {','void CommandScheduler::Flush(SubmitInfo& submit, std::source_location where) {')
edit(s,'\tSubmit(submit);','\tSubmit(submit,where);')
edit(s,'uint64_t CommandScheduler::Submit(SubmitInfo submit) {','''uint64_t CommandScheduler::Submit(SubmitInfo submit, std::source_location where) {
\t// Bounded, opt-in call-site accounting. This reports the reason for submitting,
\t// not the timestamp hook that happens to end rendering during every Submit.
\tstatic const bool trace=[] {const char* v=std::getenv("NOVA_SUBMIT_REASONS");return v&&v[0]=='1';}();
\tif(trace){
\t struct Site {const void* scheduler=nullptr;const char* file=nullptr;uint32_t line=0;uint64_t calls=0;};
\t static std::mutex mutex;static std::array<Site,64> sites{};
\t static uint64_t overflow=0;static auto start=std::chrono::steady_clock::now();
\t std::lock_guard lock(mutex);bool found=false;
\t for(auto& site:sites){if(site.file==nullptr||(site.scheduler==this&&site.file==where.file_name()&&site.line==where.line())){
\t  site.scheduler=this;site.file=where.file_name();site.line=where.line();++site.calls;found=true;break;}}
\t if(!found)++overflow;
\t const auto now=std::chrono::steady_clock::now();
\t if(now-start>=std::chrono::seconds(5)){
\t  for(auto& site:sites)if(site.calls){std::fprintf(stderr,"NOVA_SUBMIT_REASON: scheduler=%p file=%s line=%u calls=%llu\\n",site.scheduler,site.file,site.line,(unsigned long long)site.calls);site.calls=0;}
\t  std::fprintf(stderr,"NOVA_SUBMIT_REASON: overflow=%llu\\n",(unsigned long long)overflow);overflow=0;start=now;
\t }
\t}''')
for p,s in pending.items():p.write_text(s)
print('0979: periodic pass budget, subresource reader stages, selective semaphore wake, opt-in submit reasons')
