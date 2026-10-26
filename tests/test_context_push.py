from pathlib import Path
import subprocess,tempfile,sys,os
s=(Path(sys.argv[1])/'src/libs/libAudio2.cpp').read_text();a=s.index('int KYTY_SYSV_ABI AudioOut2ContextPush(');b=s.index('int KYTY_SYSV_ABI AudioOut2ContextGetQueueLevel(',a)
attribution = '#include "common/novaAudio/GuestGateCost.h"\n' if 'GuestGateCostScope attribution' in s else ''
fixture=attribution+'''
#include <cstdint>
#include <mutex>
#include <cassert>
#define KYTY_SYSV_ABI
constexpr int OK=0,AUDIO_OUT2_ERROR_NOT_READY=-8,AUDIO_OUT2_ERROR_INVALID_PARAM=-1;
using AudioOut2ContextHandle=uint64_t;
struct Mutex {std::mutex value;void Lock(){value.lock();}void Unlock(){value.unlock();}} g_audioout2_state_mutex;
struct State {uint32_t num_grains=256,queued=0,queue_depth=4;uint64_t last_update=0;} state;
bool alive=false,device=false,destroyOnSleep=false;int sleeps=0,outputs=0;
uint32_t audioout2_grain_micros(uint32_t n){return n*1000000ull/48000;}
State* audioout2_find_context_locked(uint64_t h){return alive&&h==1?&state:nullptr;}
bool audioout2_context_has_queueable_device(const State&){return device;}
void audioout2_update_context_locked(State*){}
void audioout2_queue_context_audio(uint64_t,bool){assert(g_audioout2_state_mutex.value.try_lock());g_audioout2_state_mutex.value.unlock();++outputs;}
namespace LibKernel {uint64_t KernelGetProcessTime(){return 42;}}
namespace Common {struct Thread {static void SleepMicro(uint32_t n){assert(n==audioout2_grain_micros(state.num_grains));assert(++sleeps==1);if(destroyOnSleep)alive=false;}};}
'''+s[a:b]+'''
int main(){
 assert(AudioOut2ContextPush(999,1)==AUDIO_OUT2_ERROR_INVALID_PARAM&&sleeps==0);
 assert(AudioOut2ContextPush(999,0)==AUDIO_OUT2_ERROR_INVALID_PARAM&&outputs==0);
 alive=true;state.queued=4;assert(AudioOut2ContextPush(1,0)==AUDIO_OUT2_ERROR_NOT_READY&&sleeps==0);
 destroyOnSleep=true;assert(AudioOut2ContextPush(1,1)==AUDIO_OUT2_ERROR_INVALID_PARAM&&sleeps==1&&outputs==0);
 alive=true;device=true;assert(AudioOut2ContextPush(1,1)==OK&&outputs==1&&state.queued==4);
 device=false;state.queued=0;assert(AudioOut2ContextPush(1,1)==OK&&outputs==2&&state.queued==1&&state.last_update==42);
 assert(g_audioout2_state_mutex.value.try_lock());g_audioout2_state_mutex.value.unlock();
}
'''
with tempfile.TemporaryDirectory() as d:
 d=Path(d);(d/'test.cpp').write_text(fixture)
 subprocess.run(['c++','-I'+str(Path(sys.argv[1])/'src'),'-std=c++20','-pthread','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(d/'test.cpp'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual ContextPush: invalid handles, destroy while waiting, async full queue, device and grain pacing')

