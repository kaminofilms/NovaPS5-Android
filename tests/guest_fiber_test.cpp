// SPDX-License-Identifier: GPL-2.0-or-later
// Harness for the production fiber implementation and its exact guest assembly.
#include <array>
#include <atomic>
#include <cassert>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <pthread.h>
#include <sys/mman.h>
#include <xmmintrin.h>
#define KYTY_NOVA_FEX 1
#define NOVA_FIBER_NATIVE_TEST 1
#define KYTY_SYSV_ABI
#define KYTY_PLATFORM 0
#define KYTY_PLATFORM_WINDOWS 1
#define LIB_VERSION(...)
#define PRINT_NAME() ((void)0)
#define LOGF(...) ((void)0)
#define EXIT(...) std::abort()
constexpr int OK=0;
namespace NovaGuest { inline void Copy(void* d,const void* s,uint64_t n){std::memcpy(d,s,n);} }
struct GateFrame {uint64_t args[6],rbx,rbp,r12,r13,r14,r15,target;};
static thread_local GateFrame* gateFrame;
namespace NovaFex {
struct GuestCallContext {uint64_t rbx{},rbp{},r12{},r13{},r14{},r15{},rsp{},rip{},rdi{},rsi{};};
static bool GetGuestCallContext(GuestCallContext* c) {
 if(!gateFrame)return false;
 auto* f=gateFrame;
 *c={f->rbx,f->rbp,f->r12,f->r13,f->r14,f->r15,
     reinterpret_cast<uint64_t>(f)+208,*reinterpret_cast<uint64_t*>(reinterpret_cast<char*>(f)+200),f->args[0],f->args[1]};
 return true;
}
static void RegisterGuestCodeRange(uint64_t,uint64_t){}
static uint64_t MakeGate(const void*);
}
extern "C" uint64_t NovaTestDispatch(GateFrame* f) {
 auto* old=gateFrame;gateFrame=f;
 using Function=uint64_t(*)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
 auto ret=reinterpret_cast<Function>(f->target)(f->args[0],f->args[1],f->args[2],f->args[3],f->args[4],f->args[5]);
 gateFrame=old;return ret;
}
extern "C" void NovaTestGate();
asm(R"(
.text
.global NovaTestGate
.type NovaTestGate,@function
NovaTestGate:
 sub $200,%rsp
 mov %rdi,0(%rsp)
 mov %rsi,8(%rsp)
 mov %rdx,16(%rsp)
 mov %rcx,24(%rsp)
 mov %r8,32(%rsp)
 mov %r9,40(%rsp)
 mov %rbx,48(%rsp)
 mov %rbp,56(%rsp)
 mov %r12,64(%rsp)
 mov %r13,72(%rsp)
 mov %r14,80(%rsp)
 mov %r15,88(%rsp)
 mov %r11,96(%rsp)
 mov %rsp,%rdi
 call NovaTestDispatch
 add $200,%rsp
 ret
.size NovaTestGate,.-NovaTestGate
)");
uint64_t NovaFex::MakeGate(const void* host) {
 static std::mutex mutex;static std::unordered_map<const void*,uint64_t> gates;
 std::lock_guard lock(mutex);
 if(auto it=gates.find(host);it!=gates.end())return it->second;
 auto* p=static_cast<unsigned char*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));assert(p!=MAP_FAILED);
 p[0]=0x49;p[1]=0xbb;std::memcpy(p+2,&host,8);
 uint64_t target=reinterpret_cast<uint64_t>(&NovaTestGate);p[10]=0x48;p[11]=0xb8;std::memcpy(p+12,&target,8);p[20]=0xff;p[21]=0xe0;
 assert(mprotect(p,4096,PROT_READ|PROT_EXEC)==0);
 auto address=reinterpret_cast<uint64_t>(p);gates.emplace(host,address);return address;
}
#include "fiber-under-test.inc"
using RunFn=uint32_t(*)(FiberObject*,uint64_t,uint64_t*);
using ReturnFn=uint32_t(*)(uint64_t,uint64_t*);
static RunFn runFiber, switchFiber;
static ReturnFn returnThread;
static FiberObject a{},b{},migrating{};
static std::atomic<int> phase{};
static void entryA(uint64_t init,uint64_t arg) {
 assert(init==11&&arg==22);
 FiberObject* self=nullptr;assert(FiberGetSelf(&self)==0&&self==&a);
 assert(runFiber(&b,0,nullptr)==uint32_t(FIBER_ERROR_PERMISSION));
 assert(switchFiber(&a,0,nullptr)==uint32_t(FIBER_ERROR_STATE));
 _mm_setcsr(0x3f80);
 uint64_t from=0;
 assert(switchFiber(&b,33,&from)==0&&from==44);
 assert(_mm_getcsr()==0x3f80);
 assert(FiberGetSelf(&self)==0&&self==&a);
 assert(returnThread(55,&from)==0&&from==66);
 assert(_mm_getcsr()==0x3f80);
 phase.fetch_add(1);
 // Returning the entry terminates the fiber and returns STATE to its runner.
}
static void entryB(uint64_t init,uint64_t arg) {
 assert(init==12&&arg==33);_mm_setcsr(0x5f80);
 uint64_t value=0;assert(switchFiber(&a,44,&value)==0&&value==77);
 assert(_mm_getcsr()==0x5f80);
 assert(returnThread(88,nullptr)==0);
 std::abort();
}
static void entryMigration(uint64_t init,uint64_t arg) {
 assert(init==123&&arg==1);
 register uint64_t saved asm("r12")=0x123456789abcdef0;
 asm volatile("" : "+r"(saved));
 _mm_setcsr(0x7f80);
 uint64_t next=0;
 assert(returnThread(2,&next)==0&&next==3);
 asm volatile("" : "+r"(saved));assert(saved==0x123456789abcdef0);
 assert(_mm_getcsr()==0x7f80);
 FiberObject* self=nullptr;assert(FiberGetSelf(&self)==0&&self==&migrating);
 phase.fetch_add(1);
}
static void initFiber(FiberObject& f,const char* name,FiberEntry entry,uint64_t arg,void* stack,size_t size) {
 assert(FiberInitialize(&f,name,entry,arg,stack,size,nullptr,0x03500000)==0);
}
int main() {
 runFiber=reinterpret_cast<RunFn>(NovaFiberWrap(reinterpret_cast<uint64_t>(&FiberRun)));
 switchFiber=reinterpret_cast<RunFn>(NovaFiberWrap(reinterpret_cast<uint64_t>(&FiberSwitch)));
 returnThread=reinterpret_cast<ReturnFn>(NovaFiberWrap(reinterpret_cast<uint64_t>(&FiberReturnToThread)));
 alignas(16) static unsigned char sa[131072],sb[131072],sm[131072];
 initFiber(a,"A",entryA,11,sa,sizeof(sa));initFiber(b,"B",entryB,12,sb,sizeof(sb));
 assert(runFiber(nullptr,0,nullptr)==uint32_t(FIBER_ERROR_INVALID));
 assert(returnThread(0,nullptr)==uint32_t(FIBER_ERROR_PERMISSION));
 assert(switchFiber(&a,0,nullptr)==uint32_t(FIBER_ERROR_PERMISSION));
 assert(NovaFiberRun(&a,0,nullptr)==uint32_t(FIBER_ERROR_PERMISSION)); // no gate
 _mm_setcsr(0x1f80);
 uint64_t result=0;assert(runFiber(&a,22,&result)==0&&result==55);
 assert(_mm_getcsr()==0x1f80);
 assert(FiberLoadState(&a)==FIBER_STATE_IDLE&&FiberLoadState(&b)==FIBER_STATE_IDLE);
 assert(runFiber(&a,66,&result)==uint32_t(FIBER_ERROR_STATE)&&result==0&&phase.load()==1);
 assert(runFiber(&a,66,&result)==uint32_t(FIBER_ERROR_STATE));
 assert(runFiber(&b,77,&result)==0&&result==88);
 assert(FiberFinalize(&b)==0);
 for(int i=0;i<64;i++) {
  initFiber(migrating,"migration",entryMigration,123,sm,sizeof(sm));
  std::thread first([&]{uint64_t value=0;assert(runFiber(&migrating,1,&value)==0&&value==2);assert(_mm_getcsr()==0x1f80);});first.join();
  std::thread second([&]{assert(runFiber(&migrating,3,nullptr)==uint32_t(FIBER_ERROR_STATE));assert(_mm_getcsr()==0x1f80);});second.join();
 }
 assert(phase.load()==65);
 assert(gateFrame==nullptr&&FiberGetThreadContext()==nullptr);
 std::puts("PASS: guest Run/Switch/yield/resume, arguments, termination, errors, FP controls, callee-save and 64 thread migrations");
}
