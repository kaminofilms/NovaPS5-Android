#include "cpu_block.h"
#include "probe.h"
#include "kyty/padData.h"
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <vector>
using Bytes=std::vector<uint8_t>;
void test(Bytes code,uint64_t expected){auto b=Nova::TranslateBlock(code.data(),code.size());assert(b.ok);assert(b.reference[0]==expected);std::cout<<std::hex<<expected<<" ";for(auto byte:code)std::cout<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(byte);std::cout<<" ";for(uint32_t word:b.arm64)std::cout<<std::setw(8)<<std::setfill('0')<<word;std::cout<<"\n";}
void reject(Bytes code){auto b=Nova::TranslateBlock(code.data(),code.size());assert(!b.ok);assert(!b.error.empty());}
int main(){
    static_assert(sizeof(Libs::Controller::PadData)==120);
    static_assert(offsetof(Libs::Controller::PadData,touch_data)==52);
    static_assert(offsetof(Libs::Controller::PadData,timestamp)==80);
    test({0x48,0xb8,40,0,0,0,0,0,0,0,0x48,0x83,0xc0,2,0xc3},42);
    test({0xb8,0xff,0xff,0xff,0xff,0x83,0xc0,1,0xc3},0);
    test({0x48,0xc7,0xc0,0xff,0xff,0xff,0xff,0x48,0x83,0xc0,1,0xc3},0);
    test({0x48,0xb8,0,0,0,0,1,0,0,0,0x89,0xc0,0xc3},0);
    test({0x49,0xb8,11,0,0,0,0,0,0,0,0x4c,0x89,0xc0,0xc3},11);
    test({0x49,0xbf,13,0,0,0,0,0,0,0,0x49,0x8b,0xc7,0xc3},13);
    test({0xb8,12,0,0,0,0xb9,3,0,0,0,0x29,0xc8,0xc3},9);
    test({0xb8,12,0,0,0,0xb9,3,0,0,0,0x2b,0xc1,0xc3},9);
    test({0xb8,12,0,0,0,0xb9,3,0,0,0,0x31,0xc8,0xc3},15);
    test({0xb8,12,0,0,0,0xb9,3,0,0,0,0x33,0xc1,0xc3},15);
    test({0xb8,12,0,0,0,0xb9,3,0,0,0,0x01,0xc8,0xc3},15);
    test({0xb8,12,0,0,0,0xb9,3,0,0,0,0x03,0xc1,0xc3},15);
    test({0x48,0xc7,0xc0,0,0,0,0,0x48,0x83,0xe8,1,0xc3},UINT64_MAX);
    test({0x48,0xc7,0xc0,0,0,0,0,0x48,0x83,0xc0,0xff,0xc3},UINT64_MAX);
    test({0xb8,0x78,0x56,0x34,0x12,0x81,0xf0,0x78,0x56,0x34,0x12,0xc3},0);
    test({0x48,0xc7,0xc0,42,0,0,0,0x48,0x31,0xc0,0x90,0xc3},0);
    for(unsigned r=0;r<16;++r){Bytes code;code.push_back(r>=8?0x49:0x48);code.push_back(0xb8+(r&7));uint64_t value=0x12345678abcdef00ull+r;for(unsigned i=0;i<8;++i)code.push_back(value>>(i*8));code.push_back(r>=8?0x4c:0x48);code.push_back(0x89);code.push_back(0xc0+((r&7)<<3));code.push_back(0xc3);test(code,value);}
    for(unsigned i=0;i<128;++i){uint32_t v=i*10000019u;Bytes code={0xb8};for(unsigned j=0;j<4;++j)code.push_back(v>>(j*8));code.insert(code.end(),{0x83,0xc0,0xff,0xc3});test(code,static_cast<uint32_t>(v-1));}
    reject({0x48});reject({0x48,0xb8,1});reject({0x0f,0x05,0xc3});reject({0xeb,0xfe});reject({0x48,0x89,0x00,0xc3});reject({0xc3,0x90});reject({0x83,0xf8,0,0xc3});reject({0x49,0x90,0xc3});reject({0xc7,0xc8,0,0,0,0,0xc3});reject({0x90});assert(!Nova::TranslateBlock(nullptr,0).ok);
    std::vector<uint8_t> elf(120,0);std::memcpy(elf.data(),"\x7f" "ELF",4);elf[4]=2;elf[5]=1;elf[6]=1;elf[16]=2;elf[18]=62;elf[20]=1;elf[32]=64;elf[52]=64;elf[54]=56;elf[56]=1;
    assert(Nova::InspectElf(elf.data(),elf.size()).valid);elf[18]=183;assert(!Nova::InspectElf(elf.data(),elf.size()).valid);elf[18]=62;elf[32]=121;assert(!Nova::InspectElf(elf.data(),elf.size()).valid);assert(!Nova::InspectElf(elf.data(),30).valid);
    std::cerr<<"PASS: native parser bounds, decoder rejection, integer semantics and Kyty pad ABI\n";
}
