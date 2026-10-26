#!/usr/bin/env python3
"""Reject an absent/destroyed context instead of waiting forever in ContextPush."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'src/libs/libAudio2.cpp';s=p.read_text()
a=s.index('int KYTY_SYSV_ABI AudioOut2ContextPush(')
b=s.index('int KYTY_SYSV_ABI AudioOut2ContextGetQueueLevel(',a)
f=s[a:b]
old='''		}
		g_audioout2_state_mutex.Unlock();

		if (blocking == 0) {'''
new='''		} else {
			// ContextDestroy may run during the unlocked grain sleep. There is
			// no queue or device clock to wait for once its context is gone.
			g_audioout2_state_mutex.Unlock();
			return AUDIO_OUT2_ERROR_INVALID_PARAM;
		}
		g_audioout2_state_mutex.Unlock();

		if (blocking == 0) {'''
if f.count(old)!=1:raise SystemExit('0984 changed ContextPush anchor; no source written')
p.write_text(s[:a]+f.replace(old,new,1)+s[b:])
print('0984: invalid/destroyed AudioOut2 push returns error; valid sample-clock pacing unchanged')
