#include "probe.h"
#include <cstring>
namespace Nova {
template<typename T> static T Read(const uint8_t* p){T v;std::memcpy(&v,p,sizeof(T));return v;}
ElfProbe InspectElf(const uint8_t* data,size_t size){
    ElfProbe p;
    if(size<64){p.message="Executable header is truncated";return p;}
    if(std::memcmp(data,"\x7f" "ELF",4)!=0){
        if(data[0]==0x4f&&data[1]==0x15&&data[2]==0x3d&&data[3]==0x1d)p.message="SELF container detected. Decrypted ELF and PS5 runtime support are required; SELF loading is not implemented.";
        else p.message="Not an ELF64 executable. Encrypted packages and archives cannot be executed by this alpha.";
        return p;
    }
    if(data[4]!=2||data[5]!=1||data[6]!=1){p.message="Only ELF64 little-endian version 1 is recognized";return p;}
    if(Read<uint32_t>(data+20)!=1){p.message="Invalid ELF format version";return p;}
    p.type=Read<uint16_t>(data+16);p.machine=Read<uint16_t>(data+18);p.entry=Read<uint64_t>(data+24);p.segments=Read<uint16_t>(data+56);
    if(p.type!=2&&p.type!=3&&p.type!=0xfe10&&p.type!=0xfe18){p.message="ELF is not an executable or shared module";return p;}
    const uint64_t off=Read<uint64_t>(data+32);const uint16_t stride=Read<uint16_t>(data+54);
    if(Read<uint16_t>(data+52)!=64||p.machine!=62||p.segments==0||p.segments>512||stride!=56){p.message="Invalid or unsupported x86-64 ELF header";return p;}
    if(off>size||static_cast<uint64_t>(p.segments)*stride>size-off){p.message="Program headers exceed the inspected file data";return p;}
    p.valid=true;p.message="x86-64 ELF recognized. Full CPU translation, PS5 imports/relocations and RDNA shader execution are not connected in this alpha.";return p;
}
}
