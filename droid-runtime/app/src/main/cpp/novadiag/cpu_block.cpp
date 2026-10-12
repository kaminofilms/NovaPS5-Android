#include "cpu_block.h"
#include <cstring>
#include <sstream>
#if defined(__aarch64__)
#include <sys/mman.h>
#include <unistd.h>
#endif
namespace Nova {
namespace {
void Const(std::vector<uint32_t>& out, unsigned reg, uint64_t value, bool wide) {
    out.push_back((wide?0xD2800000u:0x52800000u)|((value&0xffff)<<5)|reg);
    for(unsigned h=1;h<(wide?4u:2u);++h)
        out.push_back((wide?0xF2800000u:0x72800000u)|(h<<21)|(((value>>(h*16))&0xffff)<<5)|reg);
}
}
Block TranslateBlock(const uint8_t* code,size_t size) {
    Block b;
    if(!code || size==0 || size>512){b.error="Block must contain 1–512 bytes";return b;}
    for(unsigned r=0;r<16;++r)Const(b.arm64,r,0,true);
    size_t p=0;
    auto fail=[&](const char* msg){b.error=std::string(msg)+" at byte "+std::to_string(p);return b;};
    auto need=[&](size_t count){return p<=size && count<=size-p;};
    while(p<size && b.instructions<64) {
        uint8_t rex=0;
        if((code[p]&0xf0)==0x40){rex=code[p++];if(!need(1))return fail("Truncated REX prefix");}
        if(rex&2)return fail("REX.X requires unsupported memory addressing");
        const bool wide=(rex&8)!=0;
        const uint8_t op=code[p++];
        ++b.instructions;
        if(op==0xc3){
            if(rex)return fail("Prefixed RET is unsupported");
            if(p!=size)return fail("Trailing bytes after RET");
            b.arm64.push_back(0xd65f03c0);b.guest_bytes=p;b.ok=true;return b;
        }
        if(op==0x90){if(rex)return fail("Prefixed NOP/XCHG is unsupported");continue;}
        auto assign=[&](unsigned d,uint64_t v){b.reference[d]=wide?v:static_cast<uint32_t>(v);};
        if(op>=0xb8 && op<=0xbf){
            unsigned d=(op-0xb8)+((rex&1)?8:0);size_t bytes=wide?8:4;
            if(!need(bytes))return fail("Truncated MOV immediate");
            uint64_t v=0;std::memcpy(&v,code+p,bytes);p+=bytes;
            assign(d,v);Const(b.arm64,d,v,wide);continue;
        }
        if(op==0x89 || op==0x8b || op==0x31 || op==0x33 || op==0x01 || op==0x03 || op==0x29 || op==0x2b || op==0xc7 || op==0x81 || op==0x83){
            if(!need(1))return fail("Truncated ModRM");
            uint8_t m=code[p++];if((m&0xc0)!=0xc0)return fail("Memory operands are not implemented");
            unsigned d=(m&7)+((rex&1)?8:0),s=((m>>3)&7)+((rex&4)?8:0);
            if(op==0x8b || op==0x33 || op==0x03 || op==0x2b)std::swap(d,s);
            if(op==0x89 || op==0x8b){assign(d,b.reference[s]);b.arm64.push_back((wide?0xaa0003e0u:0x2a0003e0u)|(s<<16)|d);continue;}
            char action='?';
            if(op==0xc7 || op==0x81 || op==0x83){
                if(rex&4)return fail("Invalid opcode group extension");
                unsigned group=(m>>3)&7;size_t n=op==0x83?1:4;
                if(!need(n))return fail("Truncated immediate");
                int64_t signed_value;
                if(n==1){signed_value=static_cast<int8_t>(code[p]);}else{int32_t value;std::memcpy(&value,code+p,4);signed_value=value;}
                p+=n;
                if(op==0xc7){if(group!=0)return fail("Unsupported C7 group");assign(d,static_cast<uint64_t>(signed_value));Const(b.arm64,d,b.reference[d],wide);continue;}
                if(group==0)action='+';else if(group==5)action='-';else if(group==6)action='^';else return fail("Unsupported arithmetic opcode group");
                s=16;Const(b.arm64,s,static_cast<uint64_t>(signed_value),wide);
                uint64_t v=static_cast<uint64_t>(signed_value);
                if(action=='+')assign(d,b.reference[d]+v);else if(action=='-')assign(d,b.reference[d]-v);else assign(d,b.reference[d]^v);
            }else{
                if(op==0x31||op==0x33)action='^';else if(op==0x01||op==0x03)action='+';else action='-';
                if(action=='+')assign(d,b.reference[d]+b.reference[s]);else if(action=='-')assign(d,b.reference[d]-b.reference[s]);else assign(d,b.reference[d]^b.reference[s]);
            }
            uint32_t base=action=='+'?(wide?0x8b000000:0x0b000000):action=='-'?(wide?0xcb000000:0x4b000000):(wide?0xca000000:0x4a000000);
            b.arm64.push_back(base|(s<<16)|(d<<5)|d);continue;
        }
        return fail("Unsupported x86 opcode");
    }
    return fail("RET is required within 64 instructions");
}
std::string RunCpuSmokeTest(){
    const uint8_t code[]={0x48,0xb8,0x28,0,0,0,0,0,0,0,0x48,0x83,0xc0,0x02,0xc3};
    const auto b=TranslateBlock(code,sizeof(code));
    if(!b.ok||b.reference[0]!=42)return "FAIL: translator regression";
#if defined(__aarch64__)
    size_t page=static_cast<size_t>(sysconf(_SC_PAGESIZE));
    size_t bytes=b.arm64.size()*sizeof(uint32_t),allocation=((bytes+page-1)/page)*page;
    void* memory=mmap(nullptr,allocation,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(memory==MAP_FAILED)return "FAIL: JIT allocation unavailable";
    std::memcpy(memory,b.arm64.data(),bytes);
    __builtin___clear_cache(static_cast<char*>(memory),static_cast<char*>(memory)+bytes);
    if(mprotect(memory,allocation,PROT_READ|PROT_EXEC)!=0){munmap(memory,allocation);return "FAIL: executable JIT memory unavailable";}
    const auto run=reinterpret_cast<uint64_t(*)()>(memory);uint64_t result=run();munmap(memory,allocation);
    return result==42?"PASS: x86-64 MOV + ADD + RET translated to ARM64; result = 42. This is a CPU smoke test, not game execution.":"FAIL: ARM64 JIT returned wrong value";
#else
    return "PASS: x86-64 decoder/reference result = 42. Native ARM64 execution requires an ARM64 device.";
#endif
}
}
