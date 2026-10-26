#pragma once
#include <algorithm>
#include <cstdint>
#if defined(__aarch64__)
#include <arm_neon.h>
#endif
namespace NovaAudio {
inline void Float12Stereo(const float* input,float* output,uint32_t frames,const double* scales) {
 float left[12]{},right[12]{};
 const float lw[12]={1,0,.7071f,0,.7071f,0,.7071f,0,.5f,0,.5f,0};
 const float rw[12]={0,1,.7071f,0,0,.7071f,0,.7071f,0,.5f,0,.5f};
 for(unsigned i=0;i<12;++i){left[i]=float(scales[i])*lw[i];right[i]=float(scales[i])*rw[i];}
#if defined(__aarch64__)
 const auto l0=vld1q_f32(left),l1=vld1q_f32(left+4),l2=vld1q_f32(left+8);
 const auto r0=vld1q_f32(right),r1=vld1q_f32(right+4),r2=vld1q_f32(right+8);
 const auto z=vdupq_n_f32(0);
 const auto lm0=vcgtq_f32(vld1q_f32(lw),z),lm1=vcgtq_f32(vld1q_f32(lw+4),z),lm2=vcgtq_f32(vld1q_f32(lw+8),z);
 const auto rm0=vcgtq_f32(vld1q_f32(rw),z),rm1=vcgtq_f32(vld1q_f32(rw+4),z),rm2=vcgtq_f32(vld1q_f32(rw+8),z);
#endif
 for(uint32_t f=0;f<frames;++f){const float* p=input+size_t(f)*12;float l=0,r=0;
#if defined(__aarch64__)
 const auto a=vld1q_f32(p),b=vld1q_f32(p+4),c=vld1q_f32(p+8);
 l=vaddvq_f32(vaddq_f32(vaddq_f32(vmulq_f32(vbslq_f32(lm0,a,z),l0),vmulq_f32(vbslq_f32(lm1,b,z),l1)),vmulq_f32(vbslq_f32(lm2,c,z),l2)));
 r=vaddvq_f32(vaddq_f32(vaddq_f32(vmulq_f32(vbslq_f32(rm0,a,z),r0),vmulq_f32(vbslq_f32(rm1,b,z),r1)),vmulq_f32(vbslq_f32(rm2,c,z),r2)));
#else
 for(unsigned i=0;i<12;++i){if(lw[i]!=0)l+=p[i]*left[i];if(rw[i]!=0)r+=p[i]*right[i];}
#endif
 output[size_t(f)*2]=std::clamp(l,-1.f,1.f);output[size_t(f)*2+1]=std::clamp(r,-1.f,1.f);
 }
}
}
