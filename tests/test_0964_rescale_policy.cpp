#include "native/novarescale/policy.h"
#include <cassert>
#include <limits>

int main() {
    using namespace NovaRescale;
    static_assert(ParsePermille(nullptr) == 1000);
    static_assert(ParsePermille("500") == 500);
    static_assert(ParsePermille("330") == 330);
    static_assert(ParsePermille("0") == 1000);
    static_assert(ParsePermille("-1") == 1000);
    static_assert(ParsePermille("500garbage") == 1000);
    static_assert(ParsePermille("99999999999999999999999") == 1000);
    static_assert(Dimension(1920, 500) == 960);
    static_assert(Dimension(1080, 500) == 540);
    static_assert(Dimension(1921, 500) == 961);
    static_assert(Dimension(1920, 330) == 634);
    static_assert(Dimension(UINT32_MAX, 1000) == UINT32_MAX);
    Candidate c{1920,1080,1,1,1,1,true,false,false,false};
    assert(Eligible(c,500));
    for (int i=0;i<7;i++) {
        auto bad=c;
        switch(i) {
            case 0:bad.samples=4;break;
            case 1:bad.levels=2;break;
            case 2:bad.layers=2;break;
            case 3:bad.depth=2;break;
            case 4:bad.storage=true;break;
            case 5:bad.cpu_upload=true;break;
            case 6:bad.block_compressed=true;break;
        }
        assert(!Eligible(bad,500));
    }
    assert(Compatible(960,540,1920,1080,1920,1080,3840,2160));
    assert(!Compatible(960,540,1920,1080,1920,1080,1920,1080));
    assert(!Compatible(0,0,0,0,960,540,1920,1080));
    assert(!Compatible(961,540,1921,1080,960,540,1920,1080));
    // Every supported slider value: never overflow, round down or allocate zero.
    for (uint32_t p : {330u,500u,750u,1000u})
        for (uint32_t w=1;w<=16384;w++) {
            auto h=Dimension(w,p);
            assert(h>=1 && h<=w);
            assert(uint64_t(h)*1000>=uint64_t(w)*p);
            assert(uint64_t(h-1)*1000<uint64_t(w)*p);
        }
}
