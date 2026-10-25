#!/usr/bin/env python3
"""Apply after 0966: reuse copied PCM storage and reduce queue polling wakeups."""
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1])
p=root/'src/libs/audio.cpp';s=p.read_text()
def edit(old,new):
 global s
 if s.count(old)!=1:raise SystemExit('0974 audio anchor changed; no source written: '+old[:80])
 s=s.replace(old,new,1)
edit('\tstd::vector<uint8_t> prepared_buffer;', '''\t// SDL_PutAudioStreamData copies input before returning. Keep scratch capacity
\t// per calling thread, so concurrent ports never share writable PCM storage.
\tthread_local std::vector<uint8_t> prepared_buffer;
\tprepared_buffer.clear();''')
edit('''\t\t\tCommon::Thread::SleepMicro(1000);
\t\t\tqueued = SDL_GetAudioStreamQueued(port->stream);''','''\t\t\tCommon::Thread::SleepMicro(NovaAudio::QueueWaitMicros(
\t\t\t    queued,min_queued_size,BytesPerSample(port->format)*output_channels,port->freq));
\t\t\tqueued = SDL_GetAudioStreamQueued(port->stream);''')
edit('uint32_t Audio::AudioOutOutputs(OutputParam* params, uint32_t num, bool blocking) {',
     'uint32_t Audio::AudioOutOutputs(OutputParam* params, uint32_t num, bool blocking) {\n\tNovaAudio::OutputScope nova_output_cost;')
s='#include "common/novaAudio/QueueWait.h"\n#include "common/novaAudio/OutputCost.h"\n'+s
shutil.copytree(repo/'native/audio',root/'src/common/novaAudio',dirs_exist_ok=True)
p.write_text(s)
print('NOVA_0974_AUDIO: thread-local PCM scratch, bounded queue sleeps, opt-in CPU attribution; guest samples/rate/deadlines unchanged')
