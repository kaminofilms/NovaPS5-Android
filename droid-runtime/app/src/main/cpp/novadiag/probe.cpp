#include "probe.h"
#include <cstring>
namespace Nova {
template<typename T> static T Read(const uint8_t* p){T v;std::memcpy(&v,p,sizeof(T));return v;}
ElfProbe InspectElf(const uint8_t* data,size_t size){
    ElfProbe p;size_t base=0;bool self=false;
    if(size<32){p.message="Executable header is truncated";return p;}
    if((data[0]==0x4f&&data[1]==0x15&&data[2]==0x3d&&data[3]==0x1d)||(data[0]==0x54&&data[1]==0x14&&data[2]==0xf5&&data[3]==0xee)){
        self=true;uint16_t segments=Read<uint16_t>(data+24);if(segments>512){p.message="SELF segment table is too large";return p;}base=32+size_t(segments)*32;
        if(base>size||size-base<64){p.message="SELF recognized, but its embedded ELF header is outside the inspected prefix. The full Kyty loader will validate it during launch.";return p;}
    }
    if(size-base<64){p.message="Executable header is truncated";return p;}const uint8_t* h=data+base;
    if(std::memcmp(h,"\x7f" "ELF",4)!=0){p.message=self?"SELF recognized; no readable ELF header found in its expected header location. Full Kyty validation is required. This check does not determine payload encryption.":"Not a recognized ELF64 or SELF executable";return p;}
    if(h[4]!=2||h[5]!=1||h[6]!=1||Read<uint32_t>(h+20)!=1){p.message="Unsupported ELF format";return p;}
    p.type=Read<uint16_t>(h+16);p.machine=Read<uint16_t>(h+18);p.entry=Read<uint64_t>(h+24);p.segments=Read<uint16_t>(h+56);
    uint64_t offset=Read<uint64_t>(h+32);uint16_t stride=Read<uint16_t>(h+54);
    if(p.machine!=62||Read<uint16_t>(h+52)!=64||p.segments==0||p.segments>512||stride!=56){p.message="Invalid or unsupported x86-64 executable header";return p;}
    if(offset>size-base||uint64_t(p.segments)*stride>size-base-offset){p.message="Program headers exceed the inspected prefix";return p;}
    p.valid=true;p.message=self?"SELF container with readable x86-64 ELF headers. SELF does not by itself mean encrypted. The full Kyty loader is used by Play; payload and game compatibility still need validation.":"x86-64 ELF headers recognized. Play uses the full Kyty runtime through ARM64 Proton/FEX.";return p;
}
}
