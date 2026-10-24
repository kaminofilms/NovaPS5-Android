// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <cstdlib>
#include <cstdint>
#include <utility>
namespace NovaUpscale {
inline unsigned Setting(const char* name, unsigned fallback, unsigned maximum) {
    const char* p=std::getenv(name); if(!p||!*p)return fallback;
    char* end=nullptr;const long n=std::strtol(p,&end,10);
    return !end||*end||n<0||unsigned(n)>maximum?fallback:unsigned(n);
}
inline unsigned Height(){static const unsigned value=Setting("NOVA_RENDER_HEIGHT",0,2160);return value;}
// Never supersample an already smaller source. Keep the original aspect ratio.
inline std::pair<unsigned,unsigned> Extent(unsigned w,unsigned h,unsigned target) {
    if(!w||!h||!target||h<=target)return {w,h};
    return {std::max(1u,unsigned((uint64_t(w)*target+h/2)/h)),target};
}
inline unsigned Filter(){static const unsigned value=Setting("NOVA_UPSCALE_FILTER",1,2);return value;}
inline unsigned Sharpness(){static const unsigned value=Setting("NOVA_FSR_SHARPNESS",25,100);return value;}
inline bool Fsr(unsigned iw,unsigned ih,unsigned ow,unsigned oh,bool hdr) {
    return Filter()==2&&!hdr&&iw&&ih&&ow>=iw&&oh>=ih&&(ow>iw||oh>ih);
}
}
