from pathlib import Path
import subprocess,tempfile,os,sys
repo=Path(__file__).resolve().parents[1];core=Path(sys.argv[1])
s=(core/'src/libs/libAudio2.cpp').read_text();a=s.index('static NovaAudio::HandleLeases& audioout2_leases()');b=s.index('int KYTY_SYSV_ABI AudioOut2Initialize()',a)
fixture='''#include "native/audio/HandleLeases.h"
#include <array>
#include <vector>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <thread>
#include <latch>
#include <atomic>
namespace Common {using LockGuard=std::lock_guard<std::mutex>;}
namespace AudioInternal {
constexpr int OUT_PORTS_MAX=32;
struct OutputParam{int handle=0;const void* data=nullptr;const float* gains=nullptr;};
void AudioOutClose(int);uint32_t AudioOutOutputs(const OutputParam*,uint32_t,bool);
}
using AudioOut2ContextHandle=uint64_t;
struct Context {bool used=false;uint64_t handle=0;int object_audio_handle=0;std::vector<float> object_mix;std::shared_ptr<std::mutex> output_mutex;};
struct Port {bool used=false;uint64_t context=0;uint16_t port_type=0;int audio_handle=0;std::vector<uint8_t> pcm_data;std::array<float,16> gains{};};
std::mutex g_audioout2_state_mutex;
std::array<Context,2> contexts;std::array<Port,4> g_audioout2_ports;
Context* audioout2_find_context_locked(uint64_t id){for(auto& c:contexts)if(c.used&&c.handle==id)return &c;return nullptr;}
bool audioout2_port_type_is_object(uint16_t type){return type==256;}
void audioout2_mix_object(Context& c,const Port&){c.object_mix={.25f,.5f};}
std::array<std::atomic<int>,64> closes{};std::atomic<int> secondCalls{0};std::latch ready(1),resume(1);
void AudioInternal::AudioOutClose(int h){assert(h>0&&h<64);++closes[h];}
uint32_t AudioInternal::AudioOutOutputs(const OutputParam* p,uint32_t n,bool blocking){
 assert(n==1&&blocking);
 // Never block output under the global context/port state lock.
 assert(g_audioout2_state_mutex.try_lock());g_audioout2_state_mutex.unlock();
 if(p[0].handle==10){assert(static_cast<const uint8_t*>(p[0].data)[0]==1&&p[0].gains[0]==.5f);ready.count_down();resume.wait();assert(static_cast<const uint8_t*>(p[0].data)[0]==1&&p[0].gains[0]==.5f);}
 else {assert(p[0].handle==20&&static_cast<const uint8_t*>(p[0].data)[0]==3);++secondCalls;}
 return 256;
}
'''+s[a:b]+'''
int main(){
 contexts[0].used=true;contexts[0].handle=1;contexts[1].used=true;contexts[1].handle=2;
 auto& p=g_audioout2_ports[0];p.used=true;p.context=1;p.audio_handle=10;p.pcm_data={1,1,1,1};p.gains.fill(.5f);
 auto& q=g_audioout2_ports[1];q.used=true;q.context=2;q.audio_handle=20;q.pcm_data={3,3,3,3};q.gains.fill(1.f);
 std::thread output([]{audioout2_queue_context_audio(1,true);});ready.wait();
 {std::lock_guard lock(g_audioout2_state_mutex);p.pcm_data.assign(4096,2);p.gains.fill(.9f);p.used=false;contexts[0]=Context{};}
 audioout2_close_audio_handle(10);assert(closes[10]==0); // native handle survives context destruction
 audioout2_queue_context_audio(2,true);assert(secondCalls==1); // another context progresses
 resume.count_down();output.join();assert(closes[10]==1);
 audioout2_close_audio_handle(20);assert(closes[20]==1);
 audioout2_close_audio_handle(30);assert(closes[30]==1); // never submitted
 audioout2_queue_context_audio(999,true);assert(secondCalls==1);
}
'''
with tempfile.TemporaryDirectory() as d:
 d=Path(d);(d/'test.cpp').write_text(fixture)
 subprocess.run(['c++','-std=c++20','-pthread','-fsanitize=address,undefined','-I'+str(repo),str(d/'test.cpp'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual snapshot function: global-lock release, concurrent context progress, PCM/gain ownership, deferred close on context destroy')
