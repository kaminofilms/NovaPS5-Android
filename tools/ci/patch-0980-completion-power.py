#!/usr/bin/env python3
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);pending={}
def edit(name,old,new):
 p=root/name;s=pending.get(p,p.read_text())
 if s.count(old)!=1:raise SystemExit('0980 incompatible anchor '+name+' '+old[:70])
 pending[p]=s.replace(old,new,1)
s='src/graphics/host_gpu/renderer/commandScheduler.cpp'
edit(s,'\t\tif (priority) {\n\t\t\tm_operation_available.notify_one();\n\t\t}','\t\tif (priority) {\n\t\t\t// Shared CV: wake every predicate owner; completion still waits for its real timeline.\n\t\t\tm_operation_available.notify_all();\n\t\t}')
g='src/graphics/guest_gpu/graphicsRun.cpp'
for signature in ['void CommandProcessor::DrawIndex(DrawIndexArgs args) {','void CommandProcessor::DrawIndexAuto(DrawAutoArgs args) {']:
 edit(g,signature,signature+'\n\tNovaPower::Current().Begin();')
edit(g,'\tEXIT_NOT_IMPLEMENTED((draw_initiator & ~0x20u) != (indexed ? 0u : 2u));','\tNovaPower::Current().Begin();\n\tEXIT_NOT_IMPLEMENTED((draw_initiator & ~0x20u) != (indexed ? 0u : 2u));')
for signature in ['void CommandProcessor::Flip() {','void CommandProcessor::Flip(void* dst_gpu_addr, uint32_t value) {', 'void CommandProcessor::FlipWithInterrupt(uint32_t eop_event_type, uint32_t cache_action,\n                                         void* dst_gpu_addr, uint32_t value) {']:
 edit(g,signature,signature+'\n\tNovaPower::Current().End();')
p='src/kernel/pthread.cpp'
edit(p,'\tthread->host_thread_id = os_thread_id;','\tthread->host_thread_id = os_thread_id;\n\tNovaPower::ApplyWorkerAffinity(thread->name);\n\tNovaPower::CriticalGuest nova_critical_guest(thread->name);')
for name in [g,p]:
 path=root/name;pending[path]='#include "common/novaPower/FrameHints.h"\n#include "common/novaPower/WorkerAffinity.h"\n'+pending[path]
for p,s in pending.items():p.write_text(s)
(root/'src/common/novaPower').mkdir(parents=True,exist_ok=True)
for name in ['FrameHints.h','WorkerPolicy.h','WorkerAffinity.h']:shutil.copyfile(repo/'native/power'/name,root/'src/common/novaPower'/name)
print('0980: completion wakeup hardening; opt-in ADPF and topology-aware worker affinity')
