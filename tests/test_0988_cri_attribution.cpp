// SPDX-License-Identifier: GPL-2.0-or-later
#include "common/novaAudio/GuestGateCost.h"
#include <cassert>
#include <type_traits>

#if defined(KYTY_NOVA_FEX)
static unsigned captures=0;
namespace NovaFex {
bool GetGuestCallContext(GuestCallContext* context) {
    ++captures;*context={};context->rip=0x900001234;return true;
}
}
#endif

int main(int argc,char**) {
    using namespace NovaAudio;
    static_assert(!std::is_copy_constructible_v<GuestGateCostScope>);
    // Same caller deduplicates; a ninth caller remains accounted for without allocation.
    GateTotals totals;
    GateSample sample;sample.caller=0;sample.wall=20;sample.cpu=7;
    sample.waitWall=12;sample.waits=1;sample.requestedUs=10;
    sample.blocking=true;sample.result=PushResult::Ok;
    totals.Add(sample,100);
    sample.result=PushResult::Invalid;totals.Add(sample,120);
    assert(totals.buckets[0].caller==0&&totals.buckets[0].calls==2);
    assert(totals.buckets[0].results[1]==1&&totals.buckets[0].results[3]==1);
    assert(totals.buckets[0].wall==40&&totals.buckets[0].cpu==14);
    assert(totals.buckets[0].waits==2&&totals.buckets[0].waitWall==24);
    for(unsigned i=1;i<=10;++i){sample.caller=i;totals.Add(sample,130+i);}
    assert(totals.overflow.calls==3&&totals.overflow.cpu==21);
    totals.Report(99,1);assert(totals.buckets[0].calls==2); // clock rollback
    totals.Report(1000,1);assert(totals.buckets[0].calls==2); // below report period
    totals.Report(5000000100ull,1);assert(totals.start==0&&totals.overflow.calls==0);
    {
        GuestGateCostScope scope(true);
        scope.BeginWait(1);scope.BeginWait(2);scope.EndWait();scope.EndWait();
        assert(scope.Finish(-123,PushResult::NotReady)==-123);
    }
#if defined(KYTY_NOVA_FEX)
    assert(captures==(argc>1?1u:0u));
#else
    (void)argc;
#endif
}
