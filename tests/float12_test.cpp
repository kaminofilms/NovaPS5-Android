#include "native/audio/Float12Stereo.h"
#include <random>
#include <cassert>
#include <cmath>
#include <array>
int main(){std::mt19937 gen(978);std::uniform_real_distribution<float> random(-1,1);
 for(unsigned n: {0,1,3,256,512,513}){
 std::vector<float> in(n*12),out(n*2+2,42);std::array<double,12>s;
 for(auto&v:in)v=random(gen);for(auto&v:s)v=.8+random(gen)*.2;
 NovaAudio::Float12Stereo(in.data(),out.data(),n,s.data());
 for(unsigned f=0;f<n;++f){auto a=[&](unsigned c){return in[f*12+c]*s[c];};
 double l=a(0)+.7071*(a(2)+a(4)+a(6))+.5*(a(8)+a(10));
 double r=a(1)+.7071*(a(2)+a(5)+a(7))+.5*(a(9)+a(11));
 assert(std::abs(out[f*2]-std::clamp(l,-1.,1.))<1e-6);
 assert(std::abs(out[f*2+1]-std::clamp(r,-1.,1.))<1e-6);
 }assert(out[n*2]==42&&out[n*2+1]==42);
 }
}
