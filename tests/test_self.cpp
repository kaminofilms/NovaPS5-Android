// SPDX-License-Identifier: GPL-3.0-only
#include "probe.h"
#include <cassert>
#include <cstring>
#include <vector>
#include <iostream>
std::vector<uint8_t> elf(){std::vector<uint8_t> x(120);std::memcpy(x.data(),"\x7f" "ELF",4);x[4]=2;x[5]=1;x[6]=1;x[16]=2;x[18]=62;x[20]=1;x[32]=64;x[52]=64;x[54]=56;x[56]=1;return x;}
int main(){auto flat=elf();auto p=Nova::InspectElf(flat.data(),flat.size());assert(p.valid&&p.machine==62);std::vector<uint8_t> self(184);self[0]=0x4f;self[1]=0x15;self[2]=0x3d;self[3]=0x1d;self[24]=1;std::memcpy(self.data()+64,flat.data(),flat.size());p=Nova::InspectElf(self.data(),self.size());assert(p.valid&&p.machine==62&&p.message.find("SELF")!=std::string::npos);self[0]=0x54;self[1]=0x14;self[2]=0xf5;self[3]=0xee;assert(Nova::InspectElf(self.data(),self.size()).valid);self[24]=0xff;self[25]=0xff;assert(!Nova::InspectElf(self.data(),self.size()).valid);assert(!Nova::InspectElf(self.data(),16).valid);flat[18]=183;assert(!Nova::InspectElf(flat.data(),flat.size()).valid);std::cout<<"PASS: ELF/SELF recognition and malformed-header rejection\n";}
