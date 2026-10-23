#!/usr/bin/env python3
"""Compile and exercise the actual production PCM conversion and FG size policy."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
repo = Path(__file__).resolve().parents[1]
audio = (root / 'src/libs/audio.cpp').read_text()
start = audio.index('const void* Audio::PrepareOutputBuffer(')
end = audio.index('\nbool Audio::QueueSdlAudio(', start)
production = audio[start:end]
harness = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>
#include "novaFrameExtent.h"
#define EXIT_IF(x) assert(!(x))
enum class Format { FloatStereo, Float8Ch, Float8ChStd, Float12Ch, S16_8Ch };
struct Audio {
 struct PortOut { uint32_t samples_num=3; int channels_num=8; Format format=Format::Float8Ch;
                  int volume[12]{}; bool stereo_fold=true; };
 static bool FormatIsFloat(Format f) { return f!=Format::S16_8Ch; }
 static bool FormatIsStd(Format f) { return f==Format::Float8ChStd || f==Format::FloatStereo; }
 static uint32_t BytesPerSample(Format f) { return FormatIsFloat(f)?4:2; }
 static uint32_t OutputChannels(const PortOut& p) { return p.stereo_fold?2u:std::min(p.channels_num,8); }
 static const void* PrepareOutputBuffer(const PortOut&, const void*, std::vector<uint8_t>*, float, const float*);
};
'''
harness += production
harness += r'''
int main() {
 Audio::PortOut p; for(auto& v:p.volume)v=32768;
 std::vector<uint8_t> out;
 for(auto format:{Format::Float8Ch,Format::Float8ChStd,Format::Float12Ch}) {
  p.format=format; p.channels_num=format==Format::Float12Ch?12:8;
  for(int ch=0;ch<p.channels_num;++ch) {
   std::vector<float> samples(p.samples_num*p.channels_num);
   samples[ch]=0.25f;
   auto* result=static_cast<const float*>(Audio::PrepareOutputBuffer(p,samples.data(),&out,1,nullptr));
   assert(out.size()==p.samples_num*2*sizeof(float));
   const double weight=ch<2?1:(ch==3?0:(ch>=8?0.5:0.7071));
   const bool left=ch==0||ch==2||ch==4||ch==6||ch==8||ch==10;
   const bool right=ch==1||ch==2||ch==5||ch==7||ch==9||ch==11;
   assert(std::abs(result[0]-(left?weight*0.25:0))<1e-6);
   assert(std::abs(result[1]-(right?weight*0.25:0))<1e-6);
   for(unsigned i=2;i<p.samples_num*2;++i)assert(result[i]==0);
  }
 }
 p.channels_num=8; p.format=Format::Float8Ch;
 std::vector<float> samples(24,0); samples[0]=0.5f;
 float gains[12];std::fill_n(gains,12,1);gains[0]=0.25f;p.volume[0]=16384;
 auto* result=static_cast<const float*>(Audio::PrepareOutputBuffer(p,samples.data(),&out,0.5f,gains));
 assert(std::abs(result[0]-0.03125f)<1e-7);
 p.volume[0]=32768; std::fill(samples.begin(),samples.end(),1);
 result=static_cast<const float*>(Audio::PrepareOutputBuffer(p,samples.data(),&out,1,nullptr));
 assert(result[0]==1&&result[1]==1);
 p.format=Format::S16_8Ch;std::vector<int16_t> s16(24,0);s16[0]=16384;
 auto* pcm=static_cast<const int16_t*>(Audio::PrepareOutputBuffer(p,s16.data(),&out,1,nullptr));
 assert(pcm[0]==16384&&pcm[1]==0&&out.size()==12);
 std::fill(s16.begin(),s16.end(),-32768);
 pcm=static_cast<const int16_t*>(Audio::PrepareOutputBuffer(p,s16.data(),&out,1,nullptr));
 assert(pcm[0]==-32768&&pcm[1]==-32768);
 p.stereo_fold=false;p.channels_num=2;p.format=Format::FloatStereo;
 assert(Audio::PrepareOutputBuffer(p,samples.data(),&out,1,nullptr)==samples.data());
 using Libs::Graphics::NovaFramegen::WorkingSize;
 auto size=WorkingSize(3840,2160);assert(size.width==1920&&size.height==1080);
 size=WorkingSize(1280,720);assert(size.width==1280&&size.height==720);
 size=WorkingSize(1080,1920);assert(size.width<=1080&&size.height==1080);
 for(uint32_t w=1;w<8200;w+=53)for(uint32_t h=1;h<4400;h+=61){
  size=WorkingSize(w,h);assert(size.width&&size.height&&size.width<=1920&&size.height<=1080);
 }
}
'''
with tempfile.TemporaryDirectory(prefix='nova-0966-') as temp:
    cpp=Path(temp)/'test.cpp';cpp.write_text(harness)
    binary=Path(temp)/'test'
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                    '-I',str(repo/'native/novalsfg'),str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('PASS: production surround fold, channel isolation/gains/clipping, S16, stereo bypass and FG extent bounds')
