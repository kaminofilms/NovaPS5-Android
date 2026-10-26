#!/usr/bin/env python3
"""Bounded table accounting and opt-in guest capture, with actual production header."""
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1]
core=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='nova-0988-') as tmp:
 tmp=Path(tmp)
 # Match the production GetGuestCallContext call contract. This simulates a gate;
 # it does not execute FEX or validate its live register/stack capture.
 (tmp/'novafex.h').write_text('''#pragma once
#include <cstdint>
namespace NovaFex {struct GuestCallContext {uint64_t rip;};bool GetGuestCallContext(GuestCallContext*);}
''')
 exe=tmp/'test'
 subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
  '-DKYTY_NOVA_FEX=1','-I'+str(tmp),'-I'+str(core/'src'),
  str(repo/'tests/test_0988_cri_attribution.cpp'),'-o',str(exe)],check=True)
 for enabled in ('0','1'):
  env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',NOVA_CRI_ATTRIBUTION=enabled)
  result=subprocess.run([str(exe)]+(['enabled'] if enabled=='1' else []),env=env,capture_output=True,text=True,check=True)
  rows=[line for line in result.stderr.splitlines() if line.startswith('NOVA_AUDIO2_GATE:')]
  assert len(rows)==9,result.stderr
  assert 'mixed=1 calls=3' in rows[-1],result.stderr
  assert 'ok=1' in rows[0] and 'invalid=1' in rows[0]
print('PASS 0988 bounded caller accounting, overflow retention, timer reset, opt-in capture and return values')
