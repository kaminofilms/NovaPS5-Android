#!/usr/bin/env python3
"""Port KytyPS5 d58aefd changed-range BDA sync, gated to Ever Forward."""
from pathlib import Path
import subprocess,sys
root=Path(sys.argv[1]); repo=Path(__file__).resolve().parents[2]
patch=repo/'patches/kyty-ever-bda-sync.patch'
subprocess.run(['git','apply','--check',str(patch)],cwd=root,check=True)
subprocess.run(['git','apply',str(patch)],cwd=root,check=True)
# Account for time spent sleeping while every PM4 queue is blocked. Do not
# change the wait interval or the completion/readback conditions.
p=root/'src/graphics/host_gpu/renderer/novaRenderCosts.h';s=p.read_text()
a='EopLabelPoll, EopLabelSuspend, Count'; b='EopLabelPoll, EopLabelSuspend, QueuePollWait, Count'
assert s.count(a)==1;s=s.replace(a,b)
a='"eop_label_poll", "eop_label_suspend"};'; b='"eop_label_poll", "eop_label_suspend", "queue_poll_wait"};'
assert s.count(a)==1;s=s.replace(a,b);p.write_text(s)
p=root/'src/graphics/guest_gpu/graphicsRun.cpp';s=p.read_text()
a='\t\t\t\t\tgpu->m_work_available.WaitFor(&gpu->m_queue_mutex, 100);'
b='\t\t\t\t\t{\n\t\t\t\t\t\tNovaRender::Scope wait_cost(NovaRender::Cost::QueuePollWait);\n'+a+'\n\t\t\t\t\t}'
assert s.count(a)==1;s=s.replace(a,b);p.write_text(s)
print('Ever Forward: changed-range BDA sync + suballocation; original path for other titles; queue polling unchanged')
