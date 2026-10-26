#!/usr/bin/env python3
"""Instrument the actual ContextPush caller and waits; preserve return/pacing semantics."""
from pathlib import Path
import shutil,sys
root=Path(sys.argv[1]);repo=Path(__file__).resolve().parents[2]
p=root/'src/libs/libAudio2.cpp';s=p.read_text()
a=s.index('int KYTY_SYSV_ABI AudioOut2ContextPush(')
b=s.index('int KYTY_SYSV_ABI AudioOut2ContextGetQueueLevel(',a)
f=s[a:b]
edits=[
 ('{\n\tuint32_t sleep_micros', '{\n\tNovaAudio::GuestGateCostScope attribution(blocking != 0);\n\tuint32_t sleep_micros'),
 ('return OK;', 'return attribution.Finish(OK, NovaAudio::PushResult::Ok);'),
 ('return AUDIO_OUT2_ERROR_INVALID_PARAM;', 'return attribution.Finish(AUDIO_OUT2_ERROR_INVALID_PARAM, NovaAudio::PushResult::Invalid);'),
 ('return AUDIO_OUT2_ERROR_NOT_READY;', 'return attribution.Finish(AUDIO_OUT2_ERROR_NOT_READY, NovaAudio::PushResult::NotReady);'),
 ('\t\tCommon::Thread::SleepMicro(sleep_micros);', '\t\tattribution.BeginWait(sleep_micros);\n\t\tCommon::Thread::SleepMicro(sleep_micros);\n\t\tattribution.EndWait();'),
]
for old,new in edits:
 if f.count(old)!=1:raise SystemExit('0988 changed ContextPush anchor; no source written: '+old)
 f=f.replace(old,new,1)
include='#include "common/novaAudio/GuestGateCost.h"'
if include in s:raise SystemExit('0988 already applied; no source written')
header=repo/'native/audio/GuestGateCost.h'
if not header.is_file():raise SystemExit('0988 missing header; no source written')
dst=root/'src/common/novaAudio/GuestGateCost.h';dst.parent.mkdir(parents=True,exist_ok=True)
shutil.copyfile(header,dst)
p.write_text(include+'\n'+s[:a]+f+s[b:])
print('0988 opt-in ContextPush caller/native CPU/grain wait attribution applied')
