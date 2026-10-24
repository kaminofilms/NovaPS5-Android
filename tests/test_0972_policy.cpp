#include "policy.h"
#include <cassert>
#include <iostream>
int main(){
 using NovaUpscale::Extent;
 assert((Extent(1920,1080,720)==std::pair<unsigned,unsigned>{1280,720}));
 assert((Extent(3840,2160,720)==std::pair<unsigned,unsigned>{1280,720}));
 assert((Extent(1920,1080,540)==std::pair<unsigned,unsigned>{960,540}));
 assert((Extent(1920,1080,360)==std::pair<unsigned,unsigned>{640,360}));
 assert((Extent(960,540,720)==std::pair<unsigned,unsigned>{960,540}));
 assert((Extent(1920,1080,0)==std::pair<unsigned,unsigned>{1920,1080}));
 assert((Extent(1440,1080,720)==std::pair<unsigned,unsigned>{960,720}));
 assert((Extent(0,0,720)==std::pair<unsigned,unsigned>{0,0}));
 std::cout<<"PASS exact resolution targets, aspect ratio, native and smaller-source preservation\n";
}
