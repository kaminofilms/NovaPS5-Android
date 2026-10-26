#include "native/render/UploadCopies.h"
#include <vector>
#include <cassert>
#include <random>
struct Copy {uint64_t srcOffset,dstOffset,size;};
int main(){
 std::mt19937 rng(976);
 for(int trial=0;trial<10000;++trial){
  std::vector<Copy> copies;std::vector<uint64_t> expected,actual;uint64_t src=0,dst=0;
  for(int i=0;i<32;++i){dst+=rng()%3;uint64_t n=1+rng()%32;
   NovaRender::AppendUploadCopy(copies,src,dst,n);
   for(uint64_t j=0;j<n;++j)expected.push_back(dst+j);
   src+=n;dst+=n;
  }
  uint64_t cursor=0;
  for(auto c:copies){assert(c.srcOffset==cursor);for(uint64_t j=0;j<c.size;++j)actual.push_back(c.dstOffset+j);cursor+=c.size;}
  assert(actual==expected && cursor==src);
 }
 std::vector<Copy> c;
 for(int i=0;i<256;++i)NovaRender::AppendUploadCopy(c,i*4096,i*4096,4096);
 assert(c.size()==1 && c[0].size==1048576);
 NovaRender::AppendUploadCopy(c,1048576,1048580,4);assert(c.size()==2);
 std::vector<Copy> overflow{{UINT64_MAX-1,0,4}};
 NovaRender::AppendUploadCopy(overflow,2,4,4);assert(overflow.size()==2);
}
