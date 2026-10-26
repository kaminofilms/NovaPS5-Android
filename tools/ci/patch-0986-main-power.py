#!/usr/bin/env python3
"""Register the initial guest thread, which bypasses the RunThread worker hook."""
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);p=root/'src/kernel/pthread.cpp';s=p.read_text()
old='\tg_pthread_main                 = g_pthread_self;'
if s.count(old)!=1:raise SystemExit('0986 main-thread anchor changed; no source written')
p.write_text(s.replace(old,old+'\n\tNovaPower::RegisterMainGuest();',1))
shutil.copyfile(repo/'native/power/FrameHints.h',root/'src/common/novaPower/FrameHints.h')
print('0986: initial guest-main TID registered with TLS cleanup; power remains opt-in')
