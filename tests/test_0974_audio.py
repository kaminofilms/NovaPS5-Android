#!/usr/bin/env python3
"""Run the patched QueueSdlAudio function against a deterministic SDL queue."""
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1];root=Path(sys.argv[1])
s=(root/'src/libs/audio.cpp').read_text()
start=s.index('bool Audio::QueueSdlAudio(');end=s.index('\nAudio::Id Audio::AudioOutOpen(',start)
body=s[start:end]
assert 'thread_local std::vector<uint8_t> prepared_buffer;' in body
assert 'NovaAudio::OutputScope nova_output_cost;' in s
fixture=r'''
#include "QueueWait.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#define EXIT_IF(x) assert(!(x))
#define LOGF(...) ((void)0)
constexpr uint64_t AUDIO_OUT_TARGET_LATENCY_US=40000;
static uint64_t now=1;static unsigned sleeps=0,clears=0,puts=0;static bool stalled=false;
struct SDL_AudioStream {int queued=0;std::vector<uint8_t> copy;};
static SDL_AudioStream* active=nullptr;
int SDL_GetAudioStreamQueued(SDL_AudioStream* s){return s->queued;}
void SDL_ClearAudioStream(SDL_AudioStream* s){s->queued=0;++clears;}
bool SDL_PutAudioStreamData(SDL_AudioStream* s,const void* data,int size){
 s->copy.assign(static_cast<const uint8_t*>(data),static_cast<const uint8_t*>(data)+size);
 s->queued+=size;++puts;return true;
}
const char* SDL_GetError(){return "fake failure";}
namespace LibKernel {uint64_t KernelGetProcessTime(){return now;}}
namespace Common {struct Thread {static void SleepMicro(uint32_t us){
 assert(us>0&&us<=5000);now+=us;++sleeps;
 if(!stalled&&active)active->queued=std::max(0,active->queued-int(uint64_t(us)*8*48000/1000000));
}};}
struct Audio {
 struct PortOut {SDL_AudioStream* stream=nullptr;uint32_t samples_num=128,freq=48000;int format=0,clock=0;bool queue_primed=false;};
 static uint32_t OutputChannels(const PortOut&){return 2;}
 static uint32_t BytesPerSample(int){return 4;}
 static const void* PrepareOutputBuffer(const PortOut& p,const void*,std::vector<uint8_t>* b,float,const float*){
  b->resize(p.samples_num*8);std::fill(b->begin(),b->end(),uint8_t(puts));return b->data();
 }
 static bool QueueSdlAudio(PortOut*,const void*,bool,float,const float*);
};
'''+body+r'''
int main(){
 SDL_AudioStream stream;active=&stream;Audio::PortOut port;port.stream=&stream;int input=1;
 assert(Audio::QueueSdlAudio(&port,&input,true,1,nullptr));assert(puts==1&&sleeps==0);
 auto first=stream.copy;
 assert(Audio::QueueSdlAudio(&port,&input,false,1,nullptr));assert(first!=stream.copy&&first[0]==0);
 assert(sleeps==0); // nonblocking submit never waits
 stream.queued=30720;sleeps=0;
 assert(Audio::QueueSdlAudio(&port,&input,true,1,nullptr));
 assert(sleeps<=9&&stream.queued>=15360&&stream.queued<=17408&&port.queue_primed);
 stream.queued=30720;stalled=true;sleeps=0;
 const auto before=now;assert(Audio::QueueSdlAudio(&port,&input,true,1,nullptr));
 assert(clears==1&&now-before>200000&&now-before<=205000&&!port.queue_primed);
 assert(!Audio::QueueSdlAudio(&port,nullptr,true,1,nullptr));
 port.stream=nullptr;assert(!Audio::QueueSdlAudio(&port,&input,true,1,nullptr));
}
'''
with tempfile.TemporaryDirectory() as td:
 t=Path(td);compiler=os.environ.get('CXX','c++')
 for name,source in [('policy',(repo/'tests/audio_work_test.cpp').read_text()),('queue',fixture)]:
  cpp=t/(name+'.cpp');cpp.write_text(source);exe=t/name
  subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-pthread','-I',str(repo/'native/audio'),str(cpp),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual QueueSdlAudio: copied PCM lifetime, blocking/nonblocking, queue target, stalled-device timeout, null inputs')
