// Host test of patch-0994 (absolute render-target height). Build: c++ -std=c++20 -I<kyty>/src
#include "common/novaRescale.h"
#include <cassert>
#include <cstdio>
int main(){ using namespace NovaRescale;
 assert(PermilleForHeight(2160,1080)==500 && Dimension(3840,500)==1920 && Dimension(2160,500)==1080);
 assert(PermilleForHeight(2160,720)==333 && Dimension(2160,333)==720);
 assert(PermilleForHeight(1080,1080)==1000 && PermilleForHeight(720,1080)==1000);
 assert(PermilleForHeight(1080,720)==666 && PermilleForHeight(4320,360)==250 && PermilleForHeight(2160,0)==1000);
 setenv("NOVA_RESCALE_TARGET_HEIGHT","1080",1); assert(Enabled() && PermilleFor(2160)==500 && PermilleFor(1080)==1000);
 std::puts("PASS 0994 target-height permille"); }
