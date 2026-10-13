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

namespace NovaFex {

struct Vec128 {
	uint64_t lo, hi;
};

struct CallArgs {
	uint64_t gpr[8] {};   // integer args 1..8 (7 and 8 go to the guest stack)
	Vec128   vec[8] {};   // vector args
	uint64_t ret_gpr[2] {};
	Vec128   ret_vec[2] {};
};

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

// Guest code ranges: never host-executable; host jumps into them become guest calls.
NOVAFEX_API void RegisterGuestCodeRange(uint64_t start, uint64_t size);
NOVAFEX_API void UnregisterGuestCodeRange(uint64_t start);
NOVAFEX_API bool IsGuestCode(uint64_t address);

// Pointer to the SysV stack arguments of the gate call currently executing on this
// thread (what a variadic HLE function's va_list overflow area must point to).
NOVAFEX_API uint64_t CurrentGateStackArgs();
// Guest RSP / RIP at the current gate call (for diagnostics and HLE helpers that need them).
NOVAFEX_API uint64_t CurrentGuestRsp();

// Signal handler hook. Call first from the process SIGSEGV/SIGBUS handler. Returns true if
// the fault was a host->guest call (or FEX alignment fault) and the context was redirected.
NOVAFEX_API bool HandleHostFault(int signal, siginfo_t* info, void* ucontext);

// Invalidates translated guest code (after the guest or the loader modifies code bytes).
NOVAFEX_API void InvalidateGuestCode(uint64_t start, uint64_t size);

} // namespace NovaFex
