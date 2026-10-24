// Nova PS5 - native ARM64 host with FEXCore running only the guest (PS5 x86-64) code.
// SPDX-License-Identifier: GPL-2.0-or-later
//
// The emulator itself is native AArch64. Guest code runs in FEXCore's JIT, sharing the host
// address space (guest pointers are host pointers). Two bridges connect them:
//
//  guest -> host   Every host function the guest may call (HLE exports, import stubs, ...)
//                  is reached through an x86-64 "gate": a few guest instructions that spill
//                  the SysV argument registers to the guest stack and execute FEX's THUNK
//                  opcode. The host side reloads them into AAPCS64 registers and calls the
//                  function, so no per-function signature table is needed.
//
//  host -> guest   CallGuest() loads SysV registers and runs the target through FEXCore's
//                  callback entry until it returns. Guest code is never host-executable, so
//                  a plain C++ call through a guest function pointer faults at the target;
//                  HandleHostFault() turns that fault into a CallGuest() transparently.
//
// libnovafex.so contains FEXCore and its dependencies with only this API exported, so they
// cannot clash with the emulator's own libraries (fmt, xxhash, ...).
//
// Register mapping (both directions): the k-th integer argument and the k-th vector
// argument keep their position (rdi,rsi,rdx,rcx,r8,r9 <-> x0..x5; xmm0-7 <-> v0-7; SysV
// stack slots 0,1 <-> x6,x7; further stack slots are copied). This is exact for every
// signature made of integers, pointers, float/double and 16-byte vectors with up to eight
// arguments of each class, which covers the HLE surface.
#pragma once

#include <cstddef>
#include <cstdint>
#include <csignal>

#define NOVAFEX_API __attribute__((visibility("default")))

namespace NovaFexWatchpoint { struct TraceRecord; }
namespace NovaFex {

// Caller must prove the object type and pin both field mappings for this process
// lifetime. No speculative memory read or automatic candidate registration.
NOVAFEX_API bool RegisterVerifiedCheckpointObject(uint64_t guest_base);
NOVAFEX_API bool ReadWatchpointTrace(size_t index, NovaFexWatchpoint::TraceRecord* out);
// Call before any main-module execution. Validates known Luna code/metadata
// spans in already mapped guest memory; rejects unknown versions without arming.
NOVAFEX_API bool ConfigureLunaWatchpointProfile(uint64_t module_base, uint64_t module_size);
NOVAFEX_API bool IsVerifiedCheckpointObject(uint64_t guest_base);

struct Vec128 {
	uint64_t lo, hi;
};

struct CallArgs {
	uint64_t gpr[8] {};   // integer args 1..8 (7 and 8 go to the guest stack)
	Vec128   vec[8] {};   // vector args
	uint64_t ret_gpr[2] {};
	Vec128   ret_vec[2] {};
};

// Actual translated RDTSC, RDTSCP and CPUID leaf 0x15, not inferred host values.
struct ClockCounters { uint64_t rdtsc,rdtscp;uint32_t eax,ebx,ecx,edx; };
NOVAFEX_API bool ReadClockCounters(ClockCounters* out);

// One-time initialisation. Returns false (and logs) if FEXCore cannot start.
NOVAFEX_API bool Init();
NOVAFEX_API bool IsInitialized();

// Runs guest code at `target` on the calling host thread and returns when it returns.
NOVAFEX_API void CallGuest(uint64_t target, CallArgs* args);

// Convenience for up to six integer arguments.
NOVAFEX_API uint64_t CallGuest(uint64_t target, uint64_t a0 = 0, uint64_t a1 = 0, uint64_t a2 = 0,
                   uint64_t a3 = 0, uint64_t a4 = 0, uint64_t a5 = 0);

// Returns a guest-callable x86-64 address that forwards to native `host_function`.
// Repeated calls for the same function return the same gate.
NOVAFEX_API uint64_t MakeGate(const void* host_function);
NOVAFEX_API bool     IsGate(uint64_t address);

// Guest stack of the calling host thread (outermost guest calls start below `top`).
NOVAFEX_API void SetThreadGuestStack(uint64_t top);
NOVAFEX_API uint64_t GetThreadGuestStack();
// Guest FS base (FreeBSD TLS) of the calling thread.
NOVAFEX_API void SetThreadFsBase(uint64_t base);
NOVAFEX_API uint64_t GetThreadFsBase();

// Called when a host thread first runs guest code without an explicit FS base (e.g. a host
// worker invoking a guest callback); returns that thread's guest TLS pointer.
NOVAFEX_API void SetFsBaseProvider(uint64_t (*provider)());
// Forget nested guest calls on this thread after the host unwound past them with longjmp
// (guest pthread_exit). Only valid when no guest frame of this thread will be resumed.
NOVAFEX_API void AbandonGuestCalls();

// Guest code ranges: never host-executable; host jumps into them become guest calls.
NOVAFEX_API void RegisterGuestCodeRange(uint64_t start, uint64_t size);
NOVAFEX_API void UnregisterGuestCodeRange(uint64_t start);
NOVAFEX_API bool IsGuestCode(uint64_t address);

// Pointer to the SysV stack arguments of the gate call currently executing on this
// thread (what a variadic HLE function's va_list overflow area must point to).
NOVAFEX_API uint64_t CurrentGateStackArgs();
// Guest RSP / RIP at the current gate call (for diagnostics and HLE helpers that need them).
NOVAFEX_API uint64_t CurrentGuestRsp();

// Guest register state at the gate call currently executing on this thread, as the guest will
// see it right after the call returns (rip = return address, rsp = caller's rsp). Callee-saved
// registers are exact; rdi..r9 are the call arguments. Returns false outside a gate call.
struct GuestCallContext {
	uint64_t rax, rbx, rcx, rdx, rsi, rdi, rbp, rsp;
	uint64_t r8, r9, r10, r11, r12, r13, r14, r15;
	uint64_t rip, rflags;
};
NOVAFEX_API bool GetGuestCallContext(GuestCallContext* out);
// Safe-point hook run on a thread whenever one of its gate calls returns to guest code while
// the hook is armed (arm count > 0). The emulator uses it to deliver asynchronous guest signals
// (sceKernelRaiseException) to threads that are executing guest code.
NOVAFEX_API void SetGateExitHook(void (*hook)());
NOVAFEX_API void ArmGateExitHook(int delta);

// Signal handler hook. Call first from the process SIGSEGV/SIGBUS handler. Returns true if
// the fault was a host->guest call (or FEX alignment fault) and the context was redirected.
NOVAFEX_API bool HandleHostFault(int signal, siginfo_t* info, void* ucontext);
// Prints the guest view of a fault inside JIT code: guest registers, block rip, the host
// function this thread called last and guest-code-looking values on the guest stack.
NOVAFEX_API void ReportGuestFault(void* ucontext);
// 0.9.57: print this thread's last 16 guest->host calls (name, first two arguments, return
// value), newest first, each line prefixed with tag. Used when a guest exits on its own.
NOVAFEX_API void DumpRecentHostCalls(const char* tag);
// Called during a freeze report (no frame for seconds) so the emulator can add its own state.
NOVAFEX_API void SetFreezeReportHook(void (*hook)());
// Names a host function for crash/freeze reports when the dynamic symbol table cannot (static
// or internal HLE functions). `name` must stay valid for the life of the process.
NOVAFEX_API void NameHostFunction(const void* function, const char* name);

// Guest addresses above the host address space (see FEXCore/Core/NovaGuestVA.h). Must be enabled
// before guest code is translated (NOVA_GUEST_VA=1 at Init, or EnableGuestVA() before the first
// CallGuest). A slot is 1 GiB of guest space; MapGuestVASlot backs it with host memory starting
// at host_base (any address; the caller reserves 1 GiB there).
NOVAFEX_API void EnableGuestVA();
NOVAFEX_API bool GuestVAEnabled();
NOVAFEX_API void MapGuestVASlot(uint64_t guest_slot_base, uint64_t host_base);
NOVAFEX_API void UnmapGuestVASlot(uint64_t guest_slot_base);
// Host address for a guest address (identity below the host limit or for unmapped slots).
NOVAFEX_API uint64_t TranslateGuestVA(uint64_t guest);

// Invalidates translated guest code (after the guest or the loader modifies code bytes).
NOVAFEX_API void InvalidateGuestCode(uint64_t start, uint64_t size);

// Called by the emulator once per presented frame. The watchdog uses it to detect a frozen game
// (no frame for several seconds) and writes a report of every thread to stderr.
NOVAFEX_API void NoteFrame();
// Called when the game itself flipped a frame (NoteFrame also counts vblank-only presents). The
// watchdog reports a black screen (no game frame for 20 s) and freezes by these.
NOVAFEX_API void NoteGameFrame();

} // namespace NovaFex

