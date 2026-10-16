#include "novaReadbackTelemetry.h"
#include <cassert>
#include <thread>
#include <vector>

using namespace NovaRender;
int main() {
    assert(ReadbackIntersects(UINT64_MAX, 1, UINT64_MAX, 1));
    assert(ReadbackIntersects(UINT64_MAX-15, 16, UINT64_MAX, 1));
    assert(!ReadbackIntersects(0, 1, UINT64_MAX, 1));
    assert(!ReadbackIntersects(100, 16, 116, 1));
    assert(!ReadbackIntersects(100, 0, 100, 1));
    assert(ReadbackContains(UINT64_MAX-15, 16, UINT64_MAX, 1));
    for (uint64_t a=0; a<32; ++a) for (uint64_t n=0; n<16; ++n)
        for (uint64_t b=0; b<32; ++b) for (uint64_t m=0; m<16; ++m)
            assert(ReadbackIntersects(a,n,b,m) == (n && m && a<b+m && b<a+n));
    ReadbackContext fault {ReadbackCaller::HandleFaultRead, 0x10108, 1, true};
    ReadbackClassification a;
    a.Tracker(0x10108,1,0x10000,4096);
    a.Copy(fault,0x10000,0x100,16);
    assert(a.overlap && a.promoted && a.copied_bytes==16 && a.copy_ranges==1);
    fault.fault_addr=0x10200;
    ReadbackClassification b;
    b.Tracker(0x10200,1,0x10000,4096);
    b.Copy(fault,0x10000,0x100,16);
    assert(!b.overlap && b.promoted);
    ReadbackClassification c;
    c.Tracker(0x10000,4096,0x10000,4096);
    c.Copy({ReadbackCaller::ComputeLds,0,0,false},0x10000,0x100,16);
    assert(!c.overlap && !c.promoted); // Sparse dirty bytes alone are not promotion.
    fault.fault_addr=UINT64_MAX;
    ReadbackClassification d;
    d.Copy(fault,UINT64_MAX-15,15,1);
    assert(d.overlap);
    RecordReadback(fault,a);
    auto value=[](ReadbackCaller caller,ReadbackField f){return readback_totals[unsigned(caller)][unsigned(f)].load();};
    assert(value(fault.caller,ReadbackField::Overlap)==1);
    constexpr unsigned threads=8, count=20000;
    std::vector<std::thread> workers;
    for(unsigned i=0;i<threads;++i) workers.emplace_back([&]{
        for(unsigned j=0;j<count;++j) RecordReadback(fault,b);
    });
    for(auto& t:workers)t.join();
    assert(value(fault.caller,ReadbackField::Calls)==1+threads*count);
    assert(value(fault.caller,ReadbackField::Disjoint)==threads*count);
    assert(value(fault.caller,ReadbackField::Promotion)==1+threads*count);
    assert(value(fault.caller,ReadbackField::Bytes)==16*(1+threads*count));
    const auto before=value(fault.caller,ReadbackField::PublishNs);
    {ReadbackTimer timer({fault.caller,false},ReadbackField::PublishNs);}
    assert(value(fault.caller,ReadbackField::PublishNs)==before);
    {ReadbackTimer timer({fault.caller,true},ReadbackField::PublishNs); std::this_thread::yield();}
    assert(value(fault.caller,ReadbackField::PublishNs)>before);
    // Concurrent snapshots cannot reset or lose producer counts.
    std::thread dump([]{for(unsigned i=0;i<100;++i)DumpReadbackCounters();});
    for(unsigned j=0;j<count;++j)RecordReadback(fault,b);
    dump.join();
    assert(value(fault.caller,ReadbackField::Calls)==1+(threads+1)*count);
    std::puts("NOVA_READBACK_SANITIZER: production header boundaries, orthogonal attribution, counters and concurrent sampling PASS");
}
