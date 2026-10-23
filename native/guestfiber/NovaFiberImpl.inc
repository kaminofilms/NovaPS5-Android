// SPDX-License-Identifier: GPL-2.0-or-later
// Included in Libs::Fiber after the shared fiber ABI definitions.
// Contexts are host-owned sidecars: the 256-byte guest FiberObject ABI is unchanged.
#if defined(KYTY_NOVA_FEX)
#include "switchBytes.h"
using FiberResult = uint64_t;
struct NovaFiberContext {
    uint64_t rbx{}, rbp{}, r12{}, r13{}, r14{}, r15{}, rsp{}, rip{}, rdi{}, rsi{};
    uint32_t mxcsr{0x1f80};
    uint16_t fcw{0x037f}, padding{};
    uint64_t rax{};
};
static_assert(sizeof(NovaFiberContext) == 96 && offsetof(NovaFiberContext, rsp) == 48 &&
              offsetof(NovaFiberContext, mxcsr) == 80 && offsetof(NovaFiberContext, rax) == 88);
struct NovaFiberState {
    NovaFiberContext cpu;
    uint64_t* resume_out{};
    bool started{};
};
struct NovaFiberThread {
    FiberThreadContext shared{};
    NovaFiberContext caller;
    uint64_t* result_out{};
};
static thread_local NovaFiberThread g_nova_fiber_thread;
static std::mutex g_nova_fiber_mutex;
static std::unordered_map<FiberObject*, std::shared_ptr<NovaFiberState>> g_nova_fibers;

static void NovaFiberReset(FiberObject* fiber) {
    std::lock_guard lock(g_nova_fiber_mutex);
    g_nova_fibers.erase(fiber);
}
static std::shared_ptr<NovaFiberState> NovaFiberSidecar(FiberObject* fiber) {
    std::lock_guard lock(g_nova_fiber_mutex);
    auto& state = g_nova_fibers[fiber];
    if (!state) state = std::make_shared<NovaFiberState>();
    return state;
}
static uint64_t NovaFiberRedirect(NovaFiberContext& cpu) {
    return reinterpret_cast<uint64_t>(&cpu) | (uint64_t{1} << 63);
}
static void NovaFiberWrite(uint64_t* output, uint64_t value) {
    if (output) NovaGuest::Copy(output, &value, sizeof(value));
}
static bool NovaFiberCapture(NovaFiberContext& cpu) {
    NovaFex::GuestCallContext call{};
    if (!NovaFex::GetGuestCallContext(&call)) return false;
    cpu.rbx=call.rbx; cpu.rbp=call.rbp; cpu.r12=call.r12; cpu.r13=call.r13;
    cpu.r14=call.r14; cpu.r15=call.r15; cpu.rsp=call.rsp; cpu.rip=call.rip;
    cpu.rdi=call.rdi; cpu.rsi=call.rsi; cpu.rax=0;
    // The wrapper stores guest FP control state before entering the native gate.
    NovaGuest::Copy(&cpu.mxcsr, reinterpret_cast<const void*>(call.rsp), sizeof(cpu.mxcsr));
    NovaGuest::Copy(&cpu.fcw, reinterpret_cast<const void*>(call.rsp+4), sizeof(cpu.fcw));
    return true;
}
static uint64_t NovaFiberComplete() {
    auto& thread=g_nova_fiber_thread;
    FiberCompleteSwitch(thread.shared.current_fiber);
    if (!thread.shared.current_fiber) FiberSetThreadContext(nullptr);
    return 0;
}
static uint64_t NovaFiberEntryReturned();

// Each export enters the ordinary NovaFEX gate, then switches guest registers in
// translated x86-64 instructions. No suspended native C++ frame is migrated.
static uint64_t NovaFiberWrap(uint64_t host) {
    static std::mutex mutex;
    static std::unordered_map<uint64_t,uint64_t> wrappers;
    std::lock_guard lock(mutex);
    if (auto it=wrappers.find(host); it!=wrappers.end()) return it->second;
    auto* code=static_cast<unsigned char*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE,
                                               MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
    if (code==MAP_FAILED) std::abort();
    std::memcpy(code,kNovaFiberSwitch,sizeof(kNovaFiberSwitch));
    uint64_t gate=NovaFex::MakeGate(reinterpret_cast<const void*>(host));
    uint64_t complete=NovaFex::MakeGate(reinterpret_cast<const void*>(&NovaFiberComplete));
    std::memcpy(code+kNovaFiberHostOffset,&gate,8);
    std::memcpy(code+kNovaFiberCompleteOffset,&complete,8);
    NovaFex::RegisterGuestCodeRange(reinterpret_cast<uint64_t>(code),4096);
#ifdef NOVA_FIBER_NATIVE_TEST
    if(mprotect(code,4096,PROT_READ|PROT_EXEC)!=0) std::abort();
#else
    if(mprotect(code,4096,PROT_READ)!=0) std::abort();
#endif
    auto address=reinterpret_cast<uint64_t>(code);
    wrappers.emplace(host,address);
    std::fprintf(stderr,"NOVA_FIBER: translated guest context switching active\n");
    return address;
}
static uint64_t NovaFiberReturnGate() {
    static const uint64_t stub=[] {
        uint64_t target=NovaFiberWrap(reinterpret_cast<uint64_t>(&NovaFiberEntryReturned));
        auto* code=static_cast<unsigned char*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE,
                                                   MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
        if(code==MAP_FAILED) std::abort();
        // A returning entry pops its return address; recreate ABI entry alignment.
        const unsigned char prefix[]={0x48,0x83,0xec,0x08,0x48,0xb8};
        std::memcpy(code,prefix,sizeof(prefix));std::memcpy(code+6,&target,8);
        code[14]=0xff;code[15]=0xe0;
        NovaFex::RegisterGuestCodeRange(reinterpret_cast<uint64_t>(code),4096);
#ifdef NOVA_FIBER_NATIVE_TEST
        if(mprotect(code,4096,PROT_READ|PROT_EXEC)!=0) std::abort();
#else
        if(mprotect(code,4096,PROT_READ)!=0) std::abort();
#endif
        return reinterpret_cast<uint64_t>(code);
    }();
    return stub;
}
static void NovaFiberPrepare(FiberObject* fiber, NovaFiberState& state, uint64_t argument, const NovaFiberContext& parent) {
    fiber->arg_on_run=argument;
    fiber->arg_on_return=0;
    if (!state.started) {
        state.cpu={};
        if (!(fiber->flags & FIBER_FLAG_SET_FPU_REGS)) {
            state.cpu.mxcsr=parent.mxcsr;state.cpu.fcw=parent.fcw;
        }
        state.cpu.rip=reinterpret_cast<uint64_t>(fiber->entry);
        state.cpu.rsp=((reinterpret_cast<uint64_t>(fiber->addr_context)+fiber->size_context)&~uint64_t{15})-8;
        state.cpu.rdi=fiber->arg_on_initialize;state.cpu.rsi=argument;
        auto ret=NovaFiberReturnGate();
        NovaGuest::Copy(reinterpret_cast<void*>(state.cpu.rsp),&ret,8);
        state.started=true;
    } else {
        NovaFiberWrite(state.resume_out,argument);
    }
}
static uint64_t NovaFiberRun(FiberObject* fiber,uint64_t argument,uint64_t* result) {
    if(!FiberIsValid(fiber)) return uint32_t(FIBER_ERROR_INVALID);
    if(FiberGetThreadContext()) return uint32_t(FIBER_ERROR_PERMISSION);
    if(!fiber->addr_context || fiber->size_context<FIBER_CONTEXT_MIN_SIZE)
        return uint32_t(FIBER_ERROR_INVALID);
    auto& thread=g_nova_fiber_thread;
    // Capturing before ownership changes also rejects accidental direct host calls.
    if(!NovaFiberCapture(thread.caller)) return uint32_t(FIBER_ERROR_PERMISSION);
    if(!FiberCompareExchangeState(fiber,FIBER_STATE_IDLE,FIBER_STATE_RUNNING))
        return uint32_t(FIBER_ERROR_STATE);
    auto state=NovaFiberSidecar(fiber);
    NovaFiberPrepare(fiber,*state,argument,thread.caller);
    thread.shared={};thread.shared.current_fiber=fiber;thread.result_out=result;
    FiberSetThreadContext(&thread.shared);
    return NovaFiberRedirect(state->cpu);
}
static uint64_t NovaFiberSwitch(FiberObject* target,uint64_t argument,uint64_t* result) {
    if(!FiberIsValid(target)) return uint32_t(FIBER_ERROR_INVALID);
    auto* thread=FiberGetThreadContext();
    if(!thread || !thread->current_fiber) return uint32_t(FIBER_ERROR_PERMISSION);
    if(!target->addr_context || target->size_context<FIBER_CONTEXT_MIN_SIZE)
        return uint32_t(FIBER_ERROR_INVALID);
    if(!FiberCompareExchangeState(target,FIBER_STATE_IDLE,FIBER_STATE_RUNNING))
        return uint32_t(FIBER_ERROR_STATE);
    auto* caller=thread->current_fiber;
    auto from=NovaFiberSidecar(caller);
    if(!NovaFiberCapture(from->cpu)) {
        FiberStoreState(target,FIBER_STATE_IDLE);return uint32_t(FIBER_ERROR_PERMISSION);
    }
    from->resume_out=result;FiberSetContextValid(caller,true);
    auto to=NovaFiberSidecar(target);NovaFiberPrepare(target,*to,argument,from->cpu);
    thread->pending_idle_fiber=caller;thread->current_fiber=target;
    return NovaFiberRedirect(to->cpu);
}
static uint64_t NovaFiberReturn(uint64_t result,uint64_t* resume) {
    auto* thread=FiberGetThreadContext();
    if(!thread || !thread->current_fiber) return uint32_t(FIBER_ERROR_PERMISSION);
    auto* fiber=thread->current_fiber;auto state=NovaFiberSidecar(fiber);
    if(!NovaFiberCapture(state->cpu)) return uint32_t(FIBER_ERROR_PERMISSION);
    state->resume_out=resume;FiberSetContextValid(fiber,true);
    fiber->arg_on_return=result;
    NovaFiberWrite(g_nova_fiber_thread.result_out,result);
    thread->pending_idle_fiber=fiber;thread->current_fiber=nullptr;
    g_nova_fiber_thread.caller.rax=0;
    return NovaFiberRedirect(g_nova_fiber_thread.caller);
}
static uint64_t NovaFiberEntryReturned() {
    auto* thread=FiberGetThreadContext();
    if(!thread || !thread->current_fiber) std::abort();
    auto* fiber=thread->current_fiber;
    FiberSetContextValid(fiber,false);FiberStoreState(fiber,FIBER_STATE_TERMINATED);
    fiber->arg_on_return=0;NovaFiberWrite(g_nova_fiber_thread.result_out,0);
    thread->current_fiber=nullptr;
    g_nova_fiber_thread.caller.rax=uint32_t(FIBER_ERROR_STATE);
    return NovaFiberRedirect(g_nova_fiber_thread.caller);
}
#else
using FiberResult = int32_t;
#endif
