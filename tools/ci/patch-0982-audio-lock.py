#!/usr/bin/env python3
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);p=root/'src/libs/libAudio2.cpp';s=p.read_text()
def replace(old,new):
 global s
 if s.count(old)!=1:raise SystemExit('0982 incompatible audio anchor: '+old[:80])
 s=s.replace(old,new,1)
replace('#include <vector>','#include <vector>\n#include <memory>\n#include <mutex>\n#include "common/novaAudio/HandleLeases.h"')
replace('\tstd::vector<float>     object_mix;','\tstd::vector<float>     object_mix;\n\tstd::shared_ptr<std::mutex> output_mutex;')
a=s.index('static void audioout2_queue_context_audio(');b=s.index('int KYTY_SYSV_ABI AudioOut2Initialize()',a)
old=s[a:b]
new='''static NovaAudio::HandleLeases& audioout2_leases() {
\t// Port retirement is the normal cleanup path. AudioOutClose also checks
\t// whether the backend has already shut down.
\tstatic NovaAudio::HandleLeases leases;
\treturn leases;
}
static void audioout2_queue_context_audio(AudioOut2ContextHandle ctx, bool blocking) {
\tstd::shared_ptr<std::mutex> serializer;
\t{
\t\tCommon::LockGuard lock(g_audioout2_state_mutex);
\t\tauto* context=audioout2_find_context_locked(ctx);
\t\tif(!context)return;
\t\tif(!context->output_mutex)context->output_mutex=std::make_shared<std::mutex>();
\t\tserializer=context->output_mutex;
\t}
\t// Only submissions to THIS context serialize. Never wait for it under the
\t// global registry mutex, and keep it alive through concurrent context destroy.
\tstd::unique_lock submit_lock(*serializer);
\tstruct Snapshot {
\t\tstd::array<std::vector<uint8_t>,AudioInternal::OUT_PORTS_MAX> pcm;
\t\tstd::array<std::array<float,16>,AudioInternal::OUT_PORTS_MAX> gains;
\t\tstd::array<AudioInternal::OutputParam,AudioInternal::OUT_PORTS_MAX> params;
\t\tstd::array<std::shared_ptr<NovaAudio::HandleLease>,AudioInternal::OUT_PORTS_MAX> leases;
\t\tuint32_t count=0;
\t};
\t// Capacity reuse without exposing writable PCM to another thread or a nested call.
\tthread_local Snapshot scratch;
\tthread_local bool scratch_busy=false;
\tSnapshot nested;
\tSnapshot& batch=scratch_busy?nested:scratch;
\tstruct Busy {bool& value;bool previous;Busy(bool& v):value(v),previous(v){value=true;}~Busy(){value=previous;}} busy(scratch_busy);
\tstruct Release {Snapshot& batch;~Release(){for(auto& lease:batch.leases)lease.reset();}} release{batch};
\tbatch.count=0;
\t{
\t\tCommon::LockGuard lock(g_audioout2_state_mutex);
\t\tauto* context=audioout2_find_context_locked(ctx);
\t\tif(!context)return;
\t\tcontext->object_mix.clear();
\t\tfor(const auto& state:g_audioout2_ports){
\t\t\tif(!state.used||state.context!=ctx||state.pcm_data.empty())continue;
\t\t\tif(audioout2_port_type_is_object(state.port_type)){
\t\t\t\taudioout2_mix_object(*context,state);
\t\t\t}else if(state.audio_handle>0&&batch.count<AudioInternal::OUT_PORTS_MAX){
\t\t\t\tauto i=batch.count++;batch.pcm[i].assign(state.pcm_data.begin(),state.pcm_data.end());
\t\t\t\tbatch.gains[i]=state.gains;
\t\t\t\tbatch.leases[i]=audioout2_leases().Acquire(state.audio_handle,AudioInternal::AudioOutClose);
\t\t\t\tbatch.params[i]={state.audio_handle,batch.pcm[i].data(),batch.gains[i].data()};
\t\t\t}
\t\t}
\t\tif(!context->object_mix.empty()&&context->object_audio_handle>0&&batch.count<AudioInternal::OUT_PORTS_MAX){
\t\t\tauto i=batch.count++;auto bytes=context->object_mix.size()*sizeof(float);
\t\t\tbatch.pcm[i].resize(bytes);std::memcpy(batch.pcm[i].data(),context->object_mix.data(),bytes);
\t\t\tbatch.leases[i]=audioout2_leases().Acquire(context->object_audio_handle,AudioInternal::AudioOutClose);
\t\t\tbatch.params[i]={context->object_audio_handle,batch.pcm[i].data(),nullptr};
\t\t}
\t}
\tif(batch.count)AudioInternal::AudioOutOutputs(batch.params.data(),batch.count,blocking);
}
static void audioout2_close_audio_handle(int audio_handle) {
\taudioout2_leases().Retire(audio_handle,AudioInternal::AudioOutClose);
}

'''
s=s[:a]+new+s[b:]
p.write_text(s);(root/'src/common/novaAudio').mkdir(parents=True,exist_ok=True)
shutil.copyfile(repo/'native/audio/HandleLeases.h',root/'src/common/novaAudio/HandleLeases.h')
print('0982: owned AudioOut2 snapshots, per-context submission serialization, deferred native-handle close')
