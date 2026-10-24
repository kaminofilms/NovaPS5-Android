#include "StatTrace.h"
#include <cassert>
#include <string>
#include <cstdio>
std::string snapshot(){FILE* f=tmpfile();assert(f);NovaStartup::StatTrace::Report(f,0);fflush(f);rewind(f);char b[4096]{};size_t n=fread(b,1,sizeof(b),f);fclose(f);return {b,n};}
int main(){
 assert(snapshot().empty());
 {NovaStartup::StatTrace s(true,17,"/app0/file");auto a=snapshot();assert(a.find("stage=resolve")!=a.npos&&a.find("call=17")!=a.npos);s.Native("/storage/UUID/game/file");a=snapshot();assert(a.find("/storage/UUID/game/file")!=a.npos&&a.find("stage=metadata")!=a.npos);}
 assert(snapshot().empty());
 {NovaStartup::StatTrace s(false,18,"disabled");assert(snapshot().empty());}
}
