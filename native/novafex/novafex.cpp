#include <sys/uio.h>
// Nova PS5 - FEXCore embedding for guest-only translation. See novafex.h.
// SPDX-License-Identifier: GPL-2.0-or-later
#include "novafex.h"
#include "runtime_timing.hpp"
#include "watchpoint/NovaFexTraceRing.hpp"
#include "watchpoint/NovaFexLunaProfile.hpp"

#include <FEXCore/Config/Config.h>
#include <FEXCore/Core/Context.h>
#include <FEXCore/Core/CoreState.h>
#include <FEXCore/Core/HostFeatures.h>
#include <FEXCore/Core/SignalDelegator.h>
#include <FEXCore/Core/Thunks.h>
#include <FEXCore/Core/X86Enums.h>
#include <FEXCore/Debug/InternalThreadState.h>
#include <FEXCore/HLE/SyscallHandler.h>
#include <FEXCore/IR/IR.h>
#include <FEXCore/Utils/ArchHelpers/Arm64.h>
#include <FEXCore/Utils/LogManager.h>

#include "Common/Config.h"
#include "Common/HostFeatures.h"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <FEXCore/Core/NovaGuestVA.h>
#include <asm/sigcontext.h>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <ucontext.h>
#include <unordered_map>
#include <unordered_set>
#include <thread>
#include <vector>
#include <cxxabi.h>
#include <dirent.h>
#include <execinfo.h>
#include <sys/syscall.h>
#include <dlfcn.h>
#include <sys/mman.h>
#include <unistd.h>

extern "C" __attribute__((visibility("hidden"))) void nova_call_native(void* block);
extern "C" __attribute__((visibility("hidden"))) void nova_guest_bridge_entry();

namespace NovaFex {

bool ConfigureLunaWatchpointProfile(uint64_t base, uint64_t size) {
  const auto read = [](uint64_t guest, void* out, size_t bytes) {
    // Only profile spans bounded inside the loader's mapped module are read.
    // Kernel copy returns EFAULT rather than dereferencing an unchecked pointer.
    iovec local {out, bytes};
    iovec remote {reinterpret_cast<void*>(TranslateGuestVA(guest)), bytes};
    return process_vm_readv(getpid(), &local, 1, &remote, 1, 0) == static_cast<ssize_t>(bytes);
  };
  if (!NovaFexWatchpoint::VerifyLunaProfile(base, size, read)) {
    std::fprintf(stderr, "NOVA_LUNA_PROFILE: rejected code/class/layout signature at base=0x%llx\n", static_cast<unsigned long long>(base));
    return false;
  }
  auto& ctor = NovaFexWatchpoint::luna_constructor_rip;
  const uint64_t prior = ctor.load(std::memory_order_acquire);
  if (prior && prior != base + NovaFexWatchpoint::kLunaConstructorRVA) return false;
  NovaFexWatchpoint::luna_vtable.store(base + NovaFexWatchpoint::kLunaVTableRVA, std::memory_order_release);
  NovaFexWatchpoint::luna_destructor_rip.store(base + NovaFexWatchpoint::kLunaDestructorRVA, std::memory_order_release);
  ctor.store(base + NovaFexWatchpoint::kLunaConstructorRVA, std::memory_order_release);
  std::fprintf(stderr, "NOVA_LUNA_PROFILE: armed SaveGameInstanceData ctor=0x%llx dtor=0x%llx base=0x%llx\n",
    static_cast<unsigned long long>(ctor.load()), static_cast<unsigned long long>(NovaFexWatchpoint::luna_destructor_rip.load()),
    static_cast<unsigned long long>(base));
  return true;
}

bool RegisterVerifiedCheckpointObject(uint64_t guest_base) {
  if (guest_base < 0x10000 || guest_base > UINT64_MAX - 0x48) return false;
  return NovaFexWatchpoint::RegisterVerifiedObject(guest_base, TranslateGuestVA(guest_base + 0x38),
                                                 TranslateGuestVA(guest_base + 0x40));
}

bool ReadWatchpointTrace(size_t index, NovaFexWatchpoint::TraceRecord* out) {
  return out && NovaFexWatchpoint::TryReadTrace(index, *out);
}

bool IsVerifiedCheckpointObject(uint64_t base) {
  if (base < 0x10000 || base > UINT64_MAX - 0x48) return false;
  return NovaFexWatchpoint::MatchStore(TranslateGuestVA(base + 0x38), 1).base == base;
}

static void DumpWatchpointTrace() {
  NovaFexWatchpoint::TraceRecord record;
  for (size_t i = 0; i < NovaFexWatchpoint::TRACE_CAPACITY; ++i) {
    if (!ReadWatchpointTrace(i, &record)) continue;
    std::fprintf(stderr, "NOVA_STORE_INTENT: seq=%llu object=0x%llx fields=%u guest_rip=0x%llx guest_address=0x%llx width=%u payload=0x%llx host_tid=%u attempted=1 completion=unobserved\n",
      static_cast<unsigned long long>(record.sequence), static_cast<unsigned long long>(record.matched_base),
      unsigned(record.fields), static_cast<unsigned long long>(record.intent.guest_rip),
      static_cast<unsigned long long>(record.intent.guest_address), unsigned(record.intent.width),
      static_cast<unsigned long long>(record.intent.payload), record.intent.host_thread_id);
  }
}
namespace {
std::atomic<void (*)()> g_freeze_hook {nullptr};

using FEXCore::X86State::REG_R8;
using FEXCore::X86State::REG_R9;
using FEXCore::X86State::REG_RAX;
using FEXCore::X86State::REG_RCX;
using FEXCore::X86State::REG_RDI;
using FEXCore::X86State::REG_RDX;
using FEXCore::X86State::REG_RSI;
using FEXCore::X86State::REG_RSP;
using FEXCore::X86State::REG_RBX;
using FEXCore::X86State::REG_RBP;
using FEXCore::X86State::REG_R12;
using FEXCore::X86State::REG_R13;
using FEXCore::X86State::REG_R14;
using FEXCore::X86State::REG_R15;

// Gate argument block, written by the x86 gate on the guest stack (see EmitGate).
struct GateBlock {
	uint64_t gpr[6];        // 0x00 rdi rsi rdx rcx r8 r9
	Vec128   xmm[8];        // 0x30
	uint64_t stack_args;    // 0xb0 guest address of the first SysV stack argument
	uint64_t target;        // 0xb8 host function
	uint64_t ret_gpr[2];    // 0xc0 rax rdx
	Vec128   ret_xmm[2];    // 0xd0 xmm0 xmm1
	uint64_t pad[2];        // 0xf0
};
static_assert(offsetof(GateBlock, xmm) == 0x30 && offsetof(GateBlock, stack_args) == 0xb0 &&
              offsetof(GateBlock, target) == 0xb8 && offsetof(GateBlock, ret_gpr) == 0xc0 &&
              offsetof(GateBlock, ret_xmm) == 0xd0 && sizeof(GateBlock) == 0x100);

// The SHA256 key of Nova's single generic thunk. Any value works; it only has to be unique.
constexpr uint8_t kGateKey[32] = {'N', 'O', 'V', 'A', 'P', 'S', '5', '-', 'G', 'A', 'T', 'E',
                                  '-', 'V', '1', 0x8b, 0x3f, 0x21, 0x5c, 0x77, 0x02, 0xe9, 0x4d,
                                  0x10, 0x6a, 0xc3, 0x55, 0x91, 0x0e, 0xb7, 0x28, 0x64};

struct ThreadData {
	FEXCore::Core::InternalThreadState* fex = nullptr;
	// Heartbeat diagnostics (read racily by the watchdog thread).
	std::atomic<uint64_t> gates {0};
	std::atomic<uint64_t> in_host {0};   // host function currently executing, 0 = guest code
	std::atomic<uint64_t> last_host {0};
	// Last host calls of this thread: target, rdi, rsi, return value (for crash reports).
	struct Recent { uint64_t target, a0, a1, ret; };
	Recent   recent[16] {};
	uint32_t recent_pos = 0;
	int tid = 0;
	~ThreadData();
	uint64_t guest_stack_top = 0;
	uint64_t fs_base = 0;
	uint64_t gate_stack_args = 0;
	uint64_t gate_rsp = 0;
	const uint64_t* gate_saved = nullptr; // rbx rbp r12 r13 r14 r15 rflags at gate entry
	const void*     gate_block = nullptr;
	int      depth = 0;
};

fextl::unique_ptr<FEXCore::Context::Context> g_ctx;
std::atomic<bool> g_initialized {false};
std::mutex g_init_mutex;

// Executable-for-FEX (but not for the host) page holding shared guest stubs and gates.
struct StubArena {
	uint8_t* base = nullptr;
	size_t   size = 0;
	size_t   used = 0;
	uint64_t thunk_op = 0;       // 0F 3F <key>
	uint64_t callback_ret = 0;   // 0F 3E
} g_arena;
std::mutex g_gate_mutex;
std::unordered_map<const void*, uint64_t> g_gates;
std::unordered_set<uint64_t> g_gate_addresses;
bool g_converged_avx = false; // SVE256 host: XMM low halves live in the AVX layout

std::shared_mutex g_code_mutex;
std::map<uint64_t, uint64_t> g_guest_code; // start -> end

thread_local ThreadData t_thread;
std::atomic<uint64_t (*)()> g_fs_provider {nullptr};

uint64_t* Xmm(FEXCore::Core::CPUState& s, int i) {
	return g_converged_avx ? &s.xmm.avx.data[i][0] : &s.xmm.sse.data[i][0];
}

uint8_t* ArenaAlloc(size_t bytes) {
	bytes = (bytes + 15) & ~size_t {15};
	if (g_arena.used + bytes > g_arena.size) {
		// Grow by mapping a new arena; old gates stay valid.
		const size_t size = std::max<size_t>(1u << 20, bytes);
		void* p = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (p == MAP_FAILED) {
			return nullptr;
		}
		g_arena.base = static_cast<uint8_t*>(p);
		g_arena.size = size;
		g_arena.used = 0;
		RegisterGuestCodeRange(reinterpret_cast<uint64_t>(p), size);
	}
	auto* out = g_arena.base + g_arena.used;
	g_arena.used += bytes;
	return out;
}

class Emitter {
public:
	explicit Emitter(uint8_t* p): m_p(p), m_start(p) {}
	void b(std::initializer_list<uint8_t> bytes) {
		for (auto v: bytes) *m_p++ = v;
	}
	void u32(uint32_t v) { std::memcpy(m_p, &v, 4); m_p += 4; }
	void u64(uint64_t v) { std::memcpy(m_p, &v, 8); m_p += 8; }
	uint8_t* pos() const { return m_p; }
	size_t size() const { return static_cast<size_t>(m_p - m_start); }

private:
	uint8_t* m_p;
	uint8_t* m_start;
};

// x86-64 gate:
//   sub  rsp, 0x108                ; rsp was 8 mod 16 after the call -> block 16-aligned
//   mov  [rsp+0x00..0x28], rdi..r9
//   movdqu [rsp+0x30+16*i], xmm0..7
//   lea  rax, [rsp+0x110]          ; first SysV stack argument of the caller
//   mov  [rsp+0xb0], rax
//   mov  rax, imm64(host function)
//   mov  [rsp+0xb8], rax
//   mov  rdi, rsp
//   call thunk_op                  ; 0F 3F <key>: host(rdi), then returns here
//   mov  rax, [rsp+0xc0]
//   mov  rdx, [rsp+0xc8]
//   movdqu xmm0, [rsp+0xd0]
//   movdqu xmm1, [rsp+0xe0]
//   add  rsp, 0x108
//   ret
constexpr size_t kGateSize = 208; // emitted gate is 192 bytes

void EmitGate(uint8_t* p, const void* host_function) {
	Emitter e(p);
	e.b({0x48, 0x81, 0xEC}); e.u32(0x108);
	e.b({0x48, 0x89, 0x3C, 0x24});             // mov [rsp], rdi
	e.b({0x48, 0x89, 0x74, 0x24, 0x08});       // mov [rsp+8], rsi
	e.b({0x48, 0x89, 0x54, 0x24, 0x10});       // mov [rsp+0x10], rdx
	e.b({0x48, 0x89, 0x4C, 0x24, 0x18});       // mov [rsp+0x18], rcx
	e.b({0x4C, 0x89, 0x44, 0x24, 0x20});       // mov [rsp+0x20], r8
	e.b({0x4C, 0x89, 0x4C, 0x24, 0x28});       // mov [rsp+0x28], r9
	for (uint8_t i = 0; i < 8; i++) {
		e.b({0xF3, 0x0F, 0x7F, static_cast<uint8_t>(0x84 | (i << 3)), 0x24});
		e.u32(0x30 + 16u * i);                 // movdqu [rsp+disp32], xmm_i
	}
	e.b({0x48, 0x8D, 0x84, 0x24}); e.u32(0x110); // lea rax, [rsp+0x110]
	e.b({0x48, 0x89, 0x84, 0x24}); e.u32(0xB0);  // mov [rsp+0xb0], rax
	e.b({0x48, 0xB8}); e.u64(reinterpret_cast<uint64_t>(host_function));
	e.b({0x48, 0x89, 0x84, 0x24}); e.u32(0xB8);  // mov [rsp+0xb8], rax
	e.b({0x48, 0x89, 0xE7});                     // mov rdi, rsp
	const auto call_at = reinterpret_cast<uint64_t>(e.pos()) + 5;
	e.b({0xE8}); e.u32(static_cast<uint32_t>(g_arena.thunk_op - call_at));
	e.b({0x48, 0x8B, 0x84, 0x24}); e.u32(0xC0);  // mov rax, [rsp+0xc0]
	e.b({0x48, 0x8B, 0x94, 0x24}); e.u32(0xC8);  // mov rdx, [rsp+0xc8]
	e.b({0xF3, 0x0F, 0x6F, 0x84, 0x24}); e.u32(0xD0); // movdqu xmm0, [rsp+0xd0]
	e.b({0xF3, 0x0F, 0x6F, 0x8C, 0x24}); e.u32(0xE0); // movdqu xmm1, [rsp+0xe0]
	e.b({0x48, 0x81, 0xC4}); e.u32(0x108);       // add rsp, 0x108
	e.b({0xC3});
	if (e.size() > kGateSize) {
		std::abort();
	}
}

std::atomic<uint64_t> g_total_gates {0};
std::atomic<uint64_t> g_total_calls {0};
std::atomic<void (*)()> g_gate_exit_hook {nullptr};
std::atomic<int> g_gate_exit_armed {0};
std::shared_mutex g_host_names_mutex;
std::map<uint64_t, const char*> g_host_names;
const char* HostName(uint64_t address) {
	std::shared_lock lock(g_host_names_mutex);
	auto it = g_host_names.find(address);
	return it != g_host_names.end() ? it->second : nullptr;
}

void GateDispatch(void* block_pointer) {
	Timing::Scope timing(Timing::Domain::HostCall);
	auto* block = static_cast<GateBlock*>(block_pointer);
	auto& t = t_thread;
	t.gates.fetch_add(1, std::memory_order_relaxed);
	g_total_gates.fetch_add(1, std::memory_order_relaxed);
	const auto saved_in_host = t.in_host.load(std::memory_order_relaxed);
	t.in_host.store(block->target, std::memory_order_relaxed);
	t.last_host.store(block->target, std::memory_order_relaxed);
	const auto saved_args = t.gate_stack_args;
	const auto saved_rsp = t.gate_rsp;
	const auto* saved_regs = t.gate_saved;
	const auto* saved_block = t.gate_block;
	uint64_t regs[7] = {};
	if (t.fex != nullptr) {
		// FEX spills the static registers to the frame before a thunk call.
		const auto& st = t.fex->CurrentFrame->State;
		regs[0] = st.gregs[REG_RBX];
		regs[1] = st.gregs[REG_RBP];
		regs[2] = st.gregs[REG_R12];
		regs[3] = st.gregs[REG_R13];
		regs[4] = st.gregs[REG_R14];
		regs[5] = st.gregs[REG_R15];
		regs[6] = 0x202;
	}
	t.gate_saved = regs;
	t.gate_block = block;
	t.gate_stack_args = block->stack_args;
	t.gate_rsp = reinterpret_cast<uint64_t>(block) - 8;
	auto& r = t.recent[t.recent_pos++ % 16];
	r = {block->target, block->gpr[0], block->gpr[1], 0};
	nova_call_native(block);
	r.ret = block->ret_gpr[0];
	if (g_gate_exit_armed.load(std::memory_order_relaxed) > 0) [[unlikely]] {
		if (auto hook = g_gate_exit_hook.load(std::memory_order_acquire); hook != nullptr) {
			// The hook may call guest code; the return values of this call must survive it.
			uint64_t ret[2] = {block->ret_gpr[0], block->ret_gpr[1]};
			Vec128 xret[2];
			std::memcpy(xret, block->ret_xmm, sizeof(xret));
			hook();
			block->ret_gpr[0] = ret[0];
			block->ret_gpr[1] = ret[1];
			std::memcpy(block->ret_xmm, xret, sizeof(xret));
		}
	}
	t.in_host.store(saved_in_host, std::memory_order_relaxed);
	t.gate_stack_args = saved_args;
	t.gate_rsp = saved_rsp;
	t.gate_saved = saved_regs;
	t.gate_block = saved_block;
}

class NovaThunkHandler final : public FEXCore::ThunkHandler {
public:
	FEXCore::ThunkedFunction* LookupThunk(const FEXCore::IR::SHA256Sum& sha256) override {
		return std::memcmp(sha256.data, kGateKey, sizeof(kGateKey)) == 0 ? &GateDispatch : nullptr;
	}
};

class NovaSignalDelegator final : public FEXCore::SignalDelegator {
public:
	uintptr_t GetThunkCallbackRET() const override { return g_arena.callback_ret; }
};

// PS5 titles reach the kernel through libkernel (emulated by the host). A raw guest
// `syscall` is reported and fails with ENOSYS rather than reaching Linux.
class NovaSyscallHandler final : public FEXCore::HLE::SyscallHandler {
public:
	void HandleSyscall(FEXCore::Core::CpuStateFrame* frame) override {
		auto& s = frame->State;
		static std::atomic<int> reported {0};
		if (reported.fetch_add(1) < 32) {
			std::fprintf(stderr, "NOVA_FEX: guest syscall %llu at rip=0x%llx -> ENOSYS\n",
			             static_cast<unsigned long long>(s.gregs[REG_RAX]),
			             static_cast<unsigned long long>(s.rip));
		}
		s.gregs[REG_RAX] = static_cast<uint64_t>(-ENOSYS);
	}
	FEXCore::HLE::ExecutableRangeInfo QueryGuestExecutableRange(FEXCore::Core::InternalThreadState*,
	                                                            uint64_t address) override {
		std::shared_lock lock(g_code_mutex);
		auto it = g_guest_code.upper_bound(address);
		if (it != g_guest_code.begin()) {
			--it;
			if (address < it->second) {
				return {it->first, it->second - it->first, true};
			}
		}
		return {0, UINT64_MAX, true};
	}
	std::optional<FEXCore::ExecutableFileSectionInfo>
	LookupExecutableFileSection(FEXCore::Core::InternalThreadState*, uint64_t) override {
		return std::nullopt;
	}
};

NovaThunkHandler g_thunks;
NovaSignalDelegator g_signals;
NovaSyscallHandler g_syscalls;

std::mutex g_threads_mutex;
std::vector<ThreadData*> g_threads;

ThreadData::~ThreadData() {
	if (tid != 0) {
		std::lock_guard lock(g_threads_mutex);
		std::erase(g_threads, this);
	}
}

std::atomic<uint64_t> g_frames {0};
// Frames the game itself flipped (the presenter also shows frames at vblank without the game).
std::atomic<uint64_t> g_game_frames {0};

// Emulator (host) loads/stores to translated guest addresses that had to be emulated in the
// fault handler: each costs a signal round trip, so a high count names a slow path. The faulting
// host pcs are recorded lock-free here and named by the watchdog thread.
constexpr int kEmuSites = 2048;
constexpr int kEmuProbes = 16;
static_assert(std::atomic<uint64_t>::is_always_lock_free);
std::atomic<uint64_t> g_host_emulated {0};
std::atomic<uint64_t> g_emu_untracked {0};
std::atomic<uint64_t> g_emu_site_pc[kEmuSites] {};
std::atomic<uint64_t> g_emu_site_count[kEmuSites] {};
void NoteHostEmulation(uint64_t pc) {
	g_host_emulated.fetch_add(1, std::memory_order_relaxed);
	// Bounded hashed lookup avoids scanning a full early-boot table on every fault.
	// Keep the exact total, and account explicitly for sites that do not fit.
	const uint64_t key = (pc >> 2) * 0x9e3779b97f4a7c15ull;
	const int first = static_cast<int>((key ^ (key >> 32)) & (kEmuSites - 1));
	for (int probe = 0; probe < kEmuProbes; probe++) {
		const int i = (first + probe) & (kEmuSites - 1);
		uint64_t current = g_emu_site_pc[i].load(std::memory_order_relaxed);
		if (current == 0) {
			if (g_emu_site_pc[i].compare_exchange_strong(current, pc, std::memory_order_relaxed)) {
				current = pc;
			}
		}
		if (current == pc) {
			g_emu_site_count[i].fetch_add(1, std::memory_order_relaxed);
			return;
		}
	}
	g_emu_untracked.fetch_add(1, std::memory_order_relaxed);
}
// Names a host code address as "symbol+0x..", or "library+0x.." without a symbol.
void DescribeHostPc(uint64_t pc, char* out, size_t size) {
	Dl_info info {};
	if (dladdr(reinterpret_cast<void*>(pc), &info) == 0) {
		std::snprintf(out, size, "?");
		return;
	}
	if (info.dli_sname != nullptr) {
		int status = 0;
		char* demangled = abi::__cxa_demangle(info.dli_sname, nullptr, nullptr, &status);
		std::snprintf(out, size, "%.150s+0x%llx", demangled != nullptr ? demangled : info.dli_sname,
		              static_cast<unsigned long long>(pc - reinterpret_cast<uint64_t>(info.dli_saddr)));
		std::free(demangled);
		return;
	}
	const char* lib = info.dli_fname != nullptr ? info.dli_fname : "?";
	if (const char* slash = strrchr(lib, '/'); slash != nullptr) lib = slash + 1;
	std::snprintf(out, size, "%s+0x%llx", lib, static_cast<unsigned long long>(pc - reinterpret_cast<uint64_t>(info.dli_fbase)));
}
// The busiest emulation sites (watchdog thread only).
void ReportHostEmulationSites(int limit) {
	std::fprintf(stderr, "NOVA_FEX: host access tracking total=%llu untracked=%llu capacity=%d\n",
	             static_cast<unsigned long long>(g_host_emulated.load(std::memory_order_relaxed)),
	             static_cast<unsigned long long>(g_emu_untracked.load(std::memory_order_relaxed)), kEmuSites);
	struct Site {
		uint64_t pc, count;
	};
	std::vector<Site> sites;
	for (int i = 0; i < kEmuSites; i++) {
		const uint64_t pc = g_emu_site_pc[i].load(std::memory_order_relaxed);
		if (pc != 0) sites.push_back({pc, g_emu_site_count[i].load(std::memory_order_relaxed)});
	}
	std::sort(sites.begin(), sites.end(), [](const Site& a, const Site& b) { return a.count > b.count; });
	for (int i = 0; i < limit && i < static_cast<int>(sites.size()); i++) {
		char name[200];
		DescribeHostPc(sites[i].pc, name, sizeof(name));
		std::fprintf(stderr, "NOVA_FEX:   hostemu %llu at pc=0x%llx %s\n", static_cast<unsigned long long>(sites[i].count),
		             static_cast<unsigned long long>(sites[i].pc), name);
	}
}

// Stall diagnostics: every host thread prints its own native backtrace on SIGRTMIN+6.
void DumpSelf(int, siginfo_t*, void* ucontext) {
	void* frames[40];
	const int count = backtrace(frames, 40);
	char header[96];
	const int n = std::snprintf(header, sizeof(header), "NOVA_FEX: --- stack of tid %d ---\n", static_cast<int>(gettid()));
	(void)!write(2, header, static_cast<size_t>(n));
	// Android unwinding may stop at the signal trampoline. Preserve the actual
	// interrupted location independently; these are native addresses, not guest RIPs.
	if (const auto* uc = static_cast<const ucontext_t*>(ucontext)) {
		char context[240];
		const int length = std::snprintf(context, sizeof(context),
		    "NOVA_FEX: interrupted tid=%d pc=0x%llx lr=0x%llx sp=0x%llx fp=0x%llx (native)\n",
		    static_cast<int>(gettid()), static_cast<unsigned long long>(uc->uc_mcontext.pc),
		    static_cast<unsigned long long>(uc->uc_mcontext.regs[30]),
		    static_cast<unsigned long long>(uc->uc_mcontext.sp),
		    static_cast<unsigned long long>(uc->uc_mcontext.regs[29]));
		if (length > 0 && static_cast<size_t>(length) < sizeof(context)) {
			(void)!write(2, context, static_cast<size_t>(length));
		}
	}
	backtrace_symbols_fd(frames, count, 2);
}

void ReadSmall(const char* path, char* out, size_t size) {
	out[0] = 0;
	if (FILE* f = std::fopen(path, "r")) {
		if (std::fgets(out, static_cast<int>(size), f) == nullptr) out[0] = 0;
		std::fclose(f);
	}
	out[strcspn(out, "\n")] = 0;
}

// Every task of the process: name, run state (R running, S/D waiting, t stopped by a tracer) and
// the kernel function it waits in. Read from /proc only; the threads are not disturbed.
void ReportTasks() {
	const int self = static_cast<int>(gettid());
	if (DIR* dir = opendir("/proc/self/task")) {
		while (dirent* entry = readdir(dir)) {
			const int tid = atoi(entry->d_name);
			if (tid <= 0 || tid == self) continue;
			char path[64], stat[512], wchan[96];
			std::snprintf(path, sizeof(path), "/proc/self/task/%d/stat", tid);
			ReadSmall(path, stat, sizeof(stat));
			std::snprintf(path, sizeof(path), "/proc/self/task/%d/wchan", tid);
			ReadSmall(path, wchan, sizeof(wchan));
			std::fprintf(stderr, "NOVA_FEX: thread %.60s wchan=%s\n", stat, wchan[0] != 0 ? wchan : "?");
		}
		closedir(dir);
	}
}

// Then each thread prints its own native stack (interrupts every thread once; last resort).
void DumpAllThreads() {
	struct sigaction sa {};
	sa.sa_sigaction = DumpSelf;
	sa.sa_flags = SA_SIGINFO | SA_RESTART;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGRTMIN + 6, &sa, nullptr);
	const int self = static_cast<int>(gettid());
	std::vector<int> tids;
	if (DIR* dir = opendir("/proc/self/task")) {
		while (dirent* entry = readdir(dir)) {
			const int tid = atoi(entry->d_name);
			if (tid > 0 && tid != self) tids.push_back(tid);
		}
		closedir(dir);
	}
	for (const int tid: tids) {
		syscall(SYS_tgkill, getpid(), tid, SIGRTMIN + 6);
		usleep(100000);
	}
}

// Threads that run guest code: the host function each one is in, or the guest address it is at.
void ReportGuestThreads() {
	std::lock_guard lock(g_threads_mutex);
	for (auto* t: g_threads) {
		const auto in_host = t->in_host.load();
		const auto shown = in_host != 0 ? in_host : t->last_host.load();
		Dl_info info {};
		const char* name = "?";
		char* demangled = nullptr;
		if (shown != 0 && dladdr(reinterpret_cast<void*>(shown), &info) != 0 && info.dli_sname != nullptr) {
			int status = 0;
			demangled = abi::__cxa_demangle(info.dli_sname, nullptr, nullptr, &status);
			name = demangled != nullptr ? demangled : info.dli_sname;
		} else if (const char* known = HostName(shown); known != nullptr) {
			name = known;
		}
		char path[64], thread_name[32];
		std::snprintf(path, sizeof(path), "/proc/self/task/%d/comm", t->tid);
		ReadSmall(path, thread_name, sizeof(thread_name));
		const uint64_t rip = t->fex != nullptr ? t->fex->CurrentFrame->State.rip : 0;
		std::fprintf(stderr, "NOVA_FEX:   tid %d %-15s gates=%llu rip=0x%llx %s %.120s\n", t->tid, thread_name,
		             (unsigned long long)t->gates.load(), (unsigned long long)rip,
		             in_host != 0 ? "IN HOST" : "guest (last host)", name);
		std::free(demangled);
	}
}

long ReadKb(const char* path, const char* key) {
	long value = -1;
	if (FILE* f = std::fopen(path, "r")) {
		char line[256];
		const size_t len = strlen(key);
		while (std::fgets(line, sizeof(line), f) != nullptr) {
			if (strncmp(line, key, len) == 0) { value = atol(line + len); break; }
		}
		std::fclose(f);
	}
	return value;
}

int EnvInt(const char* name, int fallback) {
	const char* value = getenv(name);
	return value != nullptr && value[0] != 0 ? atoi(value) : fallback;
}

void Watchdog() {
	const int report_every = EnvInt("NOVA_FEX_HEARTBEAT", 15);
	const int freeze_after = EnvInt("NOVA_FREEZE_SECONDS", 4);
	// The Nova launcher that started this process. Kyty may run outside the session's process
	// tree (outside proot); when the launcher is gone the session has ended.
	const pid_t launcher = static_cast<pid_t>(EnvInt("NOVA_LAUNCHER_PID", 0));
	uint64_t last_frames = 0, report_frames = 0, report_gates = 0, last_gates = 0;
	uint64_t report_game_frames = 0, report_emulated = 0;
	int frozen_for = 0, quiet_for = 0, freeze_episodes = 0;
	bool stall_dumped = false;
	const auto report_start = Timing::Now();
	uint64_t last_report_ns = report_start.wall;
	Timing::Snapshot last_timing{};
	timespec process_stamp{};
	bool process_valid = clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &process_stamp) == 0;
	uint64_t process_ns = uint64_t(process_stamp.tv_sec) * 1000000000u + uint64_t(process_stamp.tv_nsec);
	for (int tick = 1;; tick++) {
		sleep(1);
		if (getppid() == 1 || (launcher > 0 && kill(launcher, 0) != 0 && errno == ESRCH)) {
			std::fprintf(stderr, "NOVA_FEX: launcher gone, exiting\n");
			_exit(0);
		}
		const auto presented = g_frames.load(std::memory_order_relaxed);
		const auto game_frames = g_game_frames.load(std::memory_order_relaxed);
		const auto emulated = g_host_emulated.load(std::memory_order_relaxed);
		// The presenter keeps showing frames at vblank while the game shows nothing, so a freeze is
		// judged by the game's own flips once it has made any (presented frames otherwise).
		const auto frames = game_frames != 0 ? game_frames : presented;
		const auto gates = g_total_gates.load(std::memory_order_relaxed);
		const auto calls = g_total_calls.load(std::memory_order_relaxed);
		if (frames != last_frames) {
			last_frames = frames;
			frozen_for = 0;
		} else if (frames != 0) {
			frozen_for++;
		}
		// Black screen from the start: the game never flipped. Report where every thread is.
		if (game_frames == 0 && presented != 0 && (tick == 20 || tick == 45)) {
			std::fprintf(stderr, "NOVA_FREEZE: no game frame after %d s (presented=%llu gates=%llu guest_calls=%llu hostemu=%llu rss=%ldMB avail=%ldMB)\n",
			             tick, (unsigned long long)presented, (unsigned long long)gates, (unsigned long long)calls,
			             (unsigned long long)emulated, ReadKb("/proc/self/status", "VmRSS:") / 1024,
			             ReadKb("/proc/meminfo", "MemAvailable:") / 1024);
			ReportGuestThreads();
			ReportTasks();
			ReportHostEmulationSites(12);
			if (tick == 45) DumpAllThreads();
			if (auto hook = g_freeze_hook.load(); hook != nullptr) hook();
			std::fprintf(stderr, "NOVA_FREEZE: end of report\n");
		}
		// The game had been presenting frames and stopped: report where every thread is. Loading
		// screens can pause presentation for a while, so the first reports only read /proc; the
		// stacks (which interrupt each thread) come only if it stays frozen.
		if (freeze_after > 0 && frames != 0 && freeze_episodes <= 3 &&
		    (frozen_for == freeze_after || frozen_for == freeze_after * 3 || frozen_for == freeze_after * 5)) {
			if (frozen_for == freeze_after) freeze_episodes++;
			std::fprintf(stderr, "NOVA_FREEZE: no frame for %d s (frames=%llu gates=%llu guest_calls=%llu hostemu=%llu rss=%ldMB avail=%ldMB)\n",
			             frozen_for, (unsigned long long)frames, (unsigned long long)gates, (unsigned long long)calls,
			             (unsigned long long)emulated, ReadKb("/proc/self/status", "VmRSS:") / 1024,
			             ReadKb("/proc/meminfo", "MemAvailable:") / 1024);
			ReportGuestThreads();
			ReportTasks();
			ReportHostEmulationSites(12);
			if (frozen_for == freeze_after * 5) DumpAllThreads();
			if (auto hook = g_freeze_hook.load(); hook != nullptr) hook();
			std::fprintf(stderr, "NOVA_FREEZE: end of report\n");
		}
		// Before the first frame: (almost) no guest->host traffic for 15 s.
		quiet_for = (frames == 0 && gates - last_gates < 400) ? quiet_for + 1 : 0;
		last_gates = gates;
		if (quiet_for == 15 && !stall_dumped) {
			stall_dumped = true;
			std::fprintf(stderr, "NOVA_FEX: no guest progress for 15 s, dumping host threads\n");
			ReportGuestThreads();
			ReportTasks();
			DumpAllThreads();
		}
		if (report_every > 0 && (tick == 5 || tick % report_every == 0)) {
			const auto report_now = Timing::Now();
			if (!report_now.valid || report_now.wall <= last_report_ns) continue;
			const double span = static_cast<double>(report_now.wall - last_report_ns) / 1e9;
			last_report_ns = report_now.wall;
			size_t thread_count;
			{ std::lock_guard lock(g_threads_mutex); thread_count = g_threads.size(); }
			std::fprintf(stderr, "NOVA_FEX: heartbeat fps=%.1f game_fps=%.1f frames=%llu game_frames=%llu gates=%llu (+%llu) guest_calls=%llu hostemu=%llu (+%llu) threads=%zu rss=%ldMB avail=%ldMB\n",
			             static_cast<double>(presented - report_frames) / span,
			             static_cast<double>(game_frames - report_game_frames) / span, (unsigned long long)presented,
			             (unsigned long long)game_frames, (unsigned long long)gates, (unsigned long long)(gates - report_gates),
			             (unsigned long long)calls, (unsigned long long)emulated, (unsigned long long)(emulated - report_emulated),
			             thread_count, ReadKb("/proc/self/status", "VmRSS:") / 1024,
			             ReadKb("/proc/meminfo", "MemAvailable:") / 1024);
			timespec process_now{};
			if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &process_now) == 0) {
				const auto next_ns = uint64_t(process_now.tv_sec) * 1000000000u + uint64_t(process_now.tv_nsec);
				if (process_valid && next_ns >= process_ns) {
					std::fprintf(stderr, "NOVA_PROCESS_CPU: elapsed_s=%.6f cpu_ms=%.3f average_busy_cores=%.3f scope=all_process_threads\n",
					    span, (next_ns - process_ns) / 1e6, (next_ns - process_ns) / (span * 1e9));
				}
				process_ns = next_ns;
				process_valid = true;
			} else {
				process_valid = false;
			}
			if (Timing::Enabled()) {
				const auto current = Timing::Read();
				const auto gw = current.guest_wall - last_timing.guest_wall;
				const auto gc = current.guest_cpu - last_timing.guest_cpu;
				const auto hw = current.host_wall - last_timing.host_wall;
				const auto hc = current.host_cpu - last_timing.host_cpu;
				std::fprintf(stderr, "NOVA_FEX_TIME: elapsed_s=%.6f guest_runtime_cpu_ms=%.3f guest_runtime_offcpu_ms=%.3f host_call_cpu_ms=%.3f host_call_offcpu_ms=%.3f invalid=%llu accounting=exclusive_completed_slices offcpu=blocked_or_descheduled guest_runtime=execution_plus_jit_and_faults\n",
				    span, gc / 1e6, Timing::OffCpu(gw, gc) / 1e6,
				    hc / 1e6, Timing::OffCpu(hw, hc) / 1e6,
				    static_cast<unsigned long long>(current.invalid - last_timing.invalid));
				last_timing = current;
			}
			if (emulated - report_emulated > 1000) ReportHostEmulationSites(6);
			report_frames = presented;
			report_game_frames = game_frames;
			report_emulated = emulated;
			report_gates = gates;
		}
	}
}

#if defined(__aarch64__)
// Android's app seccomp policy answers system calls it does not allow with SIGSYS, which would end
// the process. Answer ENOSYS instead, as an older kernel would; callers that probe for a newer
// call then fall back. (glibc blocks signals around clone3 and is unaffected either way.)
void SigsysHandler(int, siginfo_t* info, void* context) {
	auto* uc = static_cast<ucontext_t*>(context);
	uc->uc_mcontext.regs[0] = static_cast<uint64_t>(-ENOSYS);
	static std::atomic<int> reported {0};
	if (reported.fetch_add(1, std::memory_order_relaxed) < 16) {
		char text[64] = "NOVA_FEX: seccomp denied syscall ";
		size_t n = strlen(text);
		char digits[16];
		int d = 0;
		unsigned value = static_cast<unsigned>(info->si_syscall);
		do { digits[d++] = static_cast<char>('0' + value % 10); value /= 10; } while (value != 0 && d < 15);
		while (d > 0 && n < sizeof(text) - 12) text[n++] = digits[--d];
		std::memcpy(text + n, " -> ENOSYS\n", 11);
		(void)!write(2, text, n + 11);
	}
}

__attribute__((constructor)) void InstallSigsysHandler() {
	if (const char* off = getenv("NOVA_NO_SIGSYS_HANDLER"); off != nullptr && off[0] == '1') {
		return;
	}
	struct sigaction sa {};
	sa.sa_sigaction = SigsysHandler;
	sa.sa_flags = SA_SIGINFO;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGSYS, &sa, nullptr);
}
#endif

ThreadData& Current() {
	auto& t = t_thread;
	if (t.fex == nullptr) {
		t.tid = static_cast<int>(gettid());
		{
			std::lock_guard lock(g_threads_mutex);
			g_threads.push_back(&t);
		}
		t.fex = g_ctx->CreateThread(nullptr);
		if (t.guest_stack_top == 0) {
			constexpr size_t kStack = 2u << 20;
			void* p = mmap(nullptr, kStack, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
			if (p != MAP_FAILED) {
				t.guest_stack_top = reinterpret_cast<uint64_t>(p) + kStack;
			}
		}
		// Call-ret prediction stack (FEX's Linux frontend allocates it per thread). Mapped RW with a
		// page of slack on both sides so a short underflow/overflow stays inside the mapping.
		{
			constexpr size_t kSize = FEXCore::Core::InternalThreadState::CALLRET_STACK_SIZE;
			constexpr size_t kSlack = 0x10000;
			void* p = mmap(nullptr, kSize + 2 * kSlack, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
			if (p == MAP_FAILED) {
				std::fprintf(stderr, "NOVA_FEX: call-ret stack allocation failed\n");
				std::abort();
			}
			t.fex->CallRetStackBase = static_cast<uint8_t*>(p) + kSlack;
			t.fex->CurrentFrame->State.callret_sp = reinterpret_cast<uint64_t>(t.fex->CallRetStackBase) + kSize / 4;
		}
		// Per-thread GDT with a 64-bit user code segment (the decoder reads the mode from CS).
		{
			using FEXCore::Core::CPUState;
			auto* gdt = new CPUState::gdt_segment[32] {};
			auto& st = t.fex->CurrentFrame->State;
			st.segment_arrays[CPUState::SEGMENT_ARRAY_INDEX_GDT] = gdt;
			st.segment_arrays[CPUState::SEGMENT_ARRAY_INDEX_LDT] = gdt;
			st.cs_idx = CPUState::DEFAULT_USER_CS << 3;
			auto* cs = CPUState::GetSegmentFromIndex(st, st.cs_idx);
			CPUState::SetGDTBase(cs, 0);
			CPUState::SetGDTLimit(cs, 0xF'FFFFU);
			cs->L = 1;
			cs->D = 0;
			st.cs_cached = CPUState::CalculateGDTBase(*cs);
		}
		// ExecuteThread() normally sets this; Nova only ever enters through callbacks.
		t.fex->CurrentFrame->Pointers.ThunkCallbackRet = g_arena.callback_ret;
		auto& s = t.fex->CurrentFrame->State;
		s.gregs[REG_RSP] = (t.guest_stack_top - 512) & ~uint64_t {15};
		if (t.fs_base == 0) {
			if (auto provider = g_fs_provider.load(); provider != nullptr) {
				t.fs_base = provider();
			}
		}
		s.fs_cached = t.fs_base;
		s.mxcsr = 0x1F80;
	}
	return t;
}

void LogHandler(LogMan::DebugLevels level, const char* message) {
	if (level <= LogMan::DebugLevels::INFO) {
		std::fprintf(stderr, "FEX[%d]: %s\n", static_cast<int>(level), message);
	}
}

void ThrowHandler(const char* message) {
	std::fprintf(stderr, "NOVA_FEX: FEXCore assertion: %s\n", message);
	std::abort();
}

void SetDefault(FEXCore::Config::ConfigOption option, const char* value) {
	// FEX_* environment variables (debugging) win over Nova's defaults.
	if (!FEXCore::Config::Exists(option)) {
		FEXCore::Config::Set(option, value);
	}
}

} // namespace

bool Init() {
	std::lock_guard lock(g_init_mutex);
	if (g_initialized) {
		return true;
	}
	if (const char* va = getenv("NOVA_GUEST_VA"); va != nullptr && va[0] == '1') {
		FEXCore::Nova::GuestVAEnabled = true;
		std::fprintf(stderr, "NOVA_FEX: guest addresses above 2^39 are translated (NOVA_GUEST_VA)\n");
	}
	LogMan::Msg::InstallHandler(LogHandler);
	LogMan::Throw::InstallHandler(ThrowHandler);
	FEXCore::Config::Initialize();
	FEXCore::Config::AddLayer(FEX::Config::CreateEnvironmentLayer(environ));
	FEXCore::Config::Load();
	// ReloadMetaLayer rebuilds the merged view from the layers; Nova's values go on top of it.
	FEXCore::Config::ReloadMetaLayer();
	FEXCore::Config::Set(FEXCore::Config::CONFIG_IS64BIT_MODE, "1");
	// Guest code is not modified at run time once loaded (no title JITs); invalidation is
	// explicit through InvalidateGuestCode(). No signal-based SMC tracking is installed.
	FEXCore::Config::Set(FEXCore::Config::CONFIG_SMCCHECKS, "0");
	SetDefault(FEXCore::Config::CONFIG_TSOENABLED, "1");
	SetDefault(FEXCore::Config::CONFIG_MULTIBLOCK, "1");
	// Guest rdtsc returns the raw generic timer (CNTVCT_EL0); the HLE reports CNTFRQ_EL0.
	FEXCore::Config::Set(FEXCore::Config::CONFIG_SMALLTSCSCALE, "0");
	if (const char* strict = getenv("NOVA_FEX_STRICT_TSO"); strict != nullptr && strict[0] == '1') {
		FEXCore::Config::Set(FEXCore::Config::CONFIG_VECTORTSOENABLED, "1");
		FEXCore::Config::Set(FEXCore::Config::CONFIG_MEMCPYSETTSOENABLED, "1");
	}

	// Shared stubs first: gates reference thunk_op.
	auto* stubs = ArenaAlloc(64);
	if (stubs == nullptr) {
		return false;
	}
	g_arena.thunk_op = reinterpret_cast<uint64_t>(stubs);
	stubs[0] = 0x0F;
	stubs[1] = 0x3F;
	std::memcpy(stubs + 2, kGateKey, sizeof(kGateKey));
	g_arena.callback_ret = g_arena.thunk_op + 48;
	stubs[48] = 0x0F;
	stubs[49] = 0x3E;

	auto features = FEX::FetchHostFeatures();
	g_converged_avx = features.SupportsAVX && features.SupportsSVE256;
	std::fprintf(stderr, "NOVA_FEX: host AVX=%d SVE256=%d AFP=%d RCPC=%d\n", features.SupportsAVX ? 1 : 0,
	             features.SupportsSVE256 ? 1 : 0, features.SupportsAFP ? 1 : 0, features.SupportsRCPC ? 1 : 0);
	g_ctx = FEXCore::Context::Context::CreateNewContext(features);
	if (!g_ctx) {
		std::fprintf(stderr, "NOVA_FEX: CreateNewContext failed\n");
		return false;
	}
	g_ctx->SetSignalDelegator(&g_signals);
	g_ctx->SetSyscallHandler(&g_syscalls);
	g_ctx->SetThunkHandler(&g_thunks);
	if (!g_ctx->InitCore()) {
		std::fprintf(stderr, "NOVA_FEX: InitCore failed\n");
		return false;
	}
	g_initialized = true;
	std::thread(Watchdog).detach();
	return true;
}

bool IsInitialized() {
	return g_initialized;
}

void CallGuest(uint64_t target, CallArgs* args) {
	if (!g_initialized && !Init()) {
		std::abort();
	}
	auto& t = Current();
	auto& s = t.fex->CurrentFrame->State;
	const uint64_t saved_rsp = s.gregs[REG_RSP];
	const uint64_t saved_rip = s.rip;

	// SysV: integer args 7 and 8 are the first two stack slots above the return address.
	// FEX's callback entry stores the return address at RSP-16, so the callee sees
	// [entry_rsp+8] = RSP-8 and [entry_rsp+16] = RSP: place arg7 at RSP-8, arg8 at RSP.
	uint64_t rsp = saved_rsp;
	if (t.depth == 0) {
		rsp = (t.guest_stack_top - 512) & ~uint64_t {15};
	}
	rsp = (rsp - 64) & ~uint64_t {15};
	rsp -= 8; // entry RSP (rsp-16) must be 8 mod 16 like after a call
	auto* slots = reinterpret_cast<uint64_t*>(rsp - 8);
	slots[0] = args->gpr[6];
	slots[1] = args->gpr[7];
	s.gregs[REG_RSP] = rsp;
	s.gregs[REG_RDI] = args->gpr[0];
	s.gregs[REG_RSI] = args->gpr[1];
	s.gregs[REG_RDX] = args->gpr[2];
	s.gregs[REG_RCX] = args->gpr[3];
	s.gregs[REG_R8] = args->gpr[4];
	s.gregs[REG_R9] = args->gpr[5];
	s.gregs[REG_RAX] = 8; // vector-register count for variadic callees
	for (int i = 0; i < 8; i++) {
		Xmm(s, i)[0] = args->vec[i].lo;
		Xmm(s, i)[1] = args->vec[i].hi;
	}
	s.fs_cached = t.fs_base;

	t.depth++;
	g_total_calls.fetch_add(1, std::memory_order_relaxed);
	{
		Timing::Scope timing(Timing::Domain::GuestRuntime);
		g_ctx->HandleCallback(t.fex, target);
	}
	t.depth--;

	args->ret_gpr[0] = s.gregs[REG_RAX];
	args->ret_gpr[1] = s.gregs[REG_RDX];
	args->ret_vec[0] = {Xmm(s, 0)[0], Xmm(s, 0)[1]};
	args->ret_vec[1] = {Xmm(s, 1)[0], Xmm(s, 1)[1]};
	s.gregs[REG_RSP] = saved_rsp;
	s.rip = saved_rip;
}

uint64_t CallGuest(uint64_t target, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4,
                   uint64_t a5) {
	CallArgs args;
	args.gpr[0] = a0;
	args.gpr[1] = a1;
	args.gpr[2] = a2;
	args.gpr[3] = a3;
	args.gpr[4] = a4;
	args.gpr[5] = a5;
	CallGuest(target, &args);
	return args.ret_gpr[0];
}

uint64_t MakeGate(const void* host_function) {
	if (host_function == nullptr) {
		return 0;
	}
	if (!g_initialized && !Init()) {
		std::abort();
	}
	std::lock_guard lock(g_gate_mutex);
	if (auto it = g_gates.find(host_function); it != g_gates.end()) {
		return it->second;
	}
	auto* p = ArenaAlloc(kGateSize);
	if (p == nullptr) {
		return 0;
	}
	EmitGate(p, host_function);
	const auto address = reinterpret_cast<uint64_t>(p);
	g_gates.emplace(host_function, address);
	g_gate_addresses.insert(address);
	return address;
}

bool IsGate(uint64_t address) {
	std::lock_guard lock(g_gate_mutex);
	return g_gate_addresses.contains(address);
}

void SetThreadGuestStack(uint64_t top) {
	t_thread.guest_stack_top = top;
	if (t_thread.fex != nullptr && t_thread.depth == 0) {
		t_thread.fex->CurrentFrame->State.gregs[REG_RSP] = (top - 512) & ~uint64_t {15};
	}
}

uint64_t GetThreadGuestStack() {
	return t_thread.guest_stack_top;
}

void SetThreadFsBase(uint64_t base) {
	t_thread.fs_base = base;
	if (t_thread.fex != nullptr) {
		t_thread.fex->CurrentFrame->State.fs_cached = base;
	}
}

void SetFsBaseProvider(uint64_t (*provider)()) {
	g_fs_provider = provider;
}

void AbandonGuestCalls() {
	auto& t = t_thread;
	if (t.fex != nullptr) {
		t.fex->CurrentFrame->SignalHandlerRefCounter = 0;
		t.fex->CurrentFrame->State.callret_sp =
		    reinterpret_cast<uint64_t>(t.fex->CallRetStackBase) + FEXCore::Core::InternalThreadState::CALLRET_STACK_SIZE / 4;
	}
	t.depth = 0;
	t.gate_stack_args = 0;
	t.gate_rsp = 0;
}

uint64_t GetThreadFsBase() {
	return t_thread.fs_base;
}

void RegisterGuestCodeRange(uint64_t start, uint64_t size) {
	std::unique_lock lock(g_code_mutex);
	g_guest_code[start] = start + size;
}

void UnregisterGuestCodeRange(uint64_t start) {
	std::unique_lock lock(g_code_mutex);
	g_guest_code.erase(start);
}

bool IsGuestCode(uint64_t address) {
	std::shared_lock lock(g_code_mutex);
	auto it = g_guest_code.upper_bound(address);
	if (it == g_guest_code.begin()) return false;
	--it;
	return address < it->second;
}

uint64_t CurrentGateStackArgs() {
	return t_thread.gate_stack_args;
}

uint64_t CurrentGuestRsp() {
	return t_thread.gate_rsp;
}

bool GetGuestCallContext(GuestCallContext* out) {
	const auto& t = t_thread;
	if (out == nullptr || t.gate_block == nullptr || t.gate_saved == nullptr) {
		return false;
	}
	const auto* block = static_cast<const GateBlock*>(t.gate_block);
	const auto base = reinterpret_cast<uint64_t>(block);
	*out = {};
	out->rdi = block->gpr[0];
	out->rsi = block->gpr[1];
	out->rdx = block->gpr[2];
	out->rcx = block->gpr[3];
	out->r8 = block->gpr[4];
	out->r9 = block->gpr[5];
	out->rax = block->ret_gpr[0];
	out->rbx = t.gate_saved[0];
	out->rbp = t.gate_saved[1];
	out->r12 = t.gate_saved[2];
	out->r13 = t.gate_saved[3];
	out->r14 = t.gate_saved[4];
	out->r15 = t.gate_saved[5];
	out->rflags = t.gate_saved[6];
	// Gate frame: block (0x108 bytes) then the caller's return address.
	std::memcpy(&out->rip, reinterpret_cast<const void*>(base + 0x108), 8);
	out->rsp = base + 0x110;
	return true;
}

void SetGateExitHook(void (*hook)()) {
	g_gate_exit_hook.store(hook, std::memory_order_release);
}

void ArmGateExitHook(int delta) {
	g_gate_exit_armed.fetch_add(delta, std::memory_order_acq_rel);
}

void InvalidateGuestCode(uint64_t start, uint64_t size) {
	if (g_ctx) {
		// FEXCore requires the caller to hold the invalidation mutex exclusively; its check is a
		// try_lock() that is evaluated even in release builds, so calling without the lock takes
		// the mutex and never releases it (every later block compile then waits forever).
		std::unique_lock lk(g_ctx->GetCodeInvalidationMutex());
		g_ctx->InvalidateCodeBuffersCodeRange(start, size);
	}
}

void NoteFrame() {
	g_frames.fetch_add(1, std::memory_order_relaxed);
}

void NoteGameFrame() {
	g_game_frames.fetch_add(1, std::memory_order_relaxed);
}

void EnableGuestVA() {
	FEXCore::Nova::GuestVAEnabled = true;
}

bool GuestVAEnabled() {
	return FEXCore::Nova::GuestVAEnabled;
}

void MapGuestVASlot(uint64_t guest_slot_base, uint64_t host_base) {
	const uint64_t slot = guest_slot_base >> FEXCore::Nova::kGuestVASlotShift;
	if (slot >= FEXCore::Nova::kGuestVASlots) return;
	const uint64_t base = slot << FEXCore::Nova::kGuestVASlotShift;
	__atomic_store_n(&FEXCore::Nova::GuestVATable[slot], host_base - base, __ATOMIC_RELEASE);
}

void UnmapGuestVASlot(uint64_t guest_slot_base) {
	const uint64_t slot = guest_slot_base >> FEXCore::Nova::kGuestVASlotShift;
	if (slot >= FEXCore::Nova::kGuestVASlots) return;
	__atomic_store_n(&FEXCore::Nova::GuestVATable[slot], uint64_t {0}, __ATOMIC_RELEASE);
}

uint64_t TranslateGuestVA(uint64_t guest) {
	if (guest < FEXCore::Nova::kGuestVALowLimit) return guest;
	const uint64_t slot = (guest >> FEXCore::Nova::kGuestVASlotShift) & (FEXCore::Nova::kGuestVASlots - 1);
	return guest + __atomic_load_n(&FEXCore::Nova::GuestVATable[slot], __ATOMIC_ACQUIRE);
}

void NameHostFunction(const void* function, const char* name) {
	if (function == nullptr || name == nullptr) return;
	std::unique_lock lock(g_host_names_mutex);
	g_host_names.emplace(reinterpret_cast<uint64_t>(function), name);
}

void SetFreezeReportHook(void (*hook)()) {
	g_freeze_hook.store(hook);
}

void ReportGuestFault(void* ucontext) {
	DumpWatchpointTrace();
	auto* uc = static_cast<ucontext_t*>(ucontext);
	if (uc == nullptr) return;
	const uint64_t pc = uc->uc_mcontext.pc;
	const bool in_jit = g_initialized && t_thread.fex != nullptr && g_ctx->IsAddressInCodeBuffer(t_thread.fex, pc);
	std::fprintf(stderr, "NOVA_FAULT: host pc=0x%llx %s\n", (unsigned long long)pc, in_jit ? "(guest JIT code)" : "(host code)");
	if (t_thread.fex != nullptr) {
		const auto& st = t_thread.fex->CurrentFrame->State;
		std::fprintf(stderr, "NOVA_FAULT: guest block rip=0x%llx\n", (unsigned long long)st.rip);
		// Precise guest instruction from the JIT's per-instruction RIP table.
		uint64_t rip = st.rip;
		if (in_jit) {
			const uint64_t exact = g_ctx->RestoreRIPFromHostPC(t_thread.fex, pc);
			if (exact != 0) rip = exact;
			std::fprintf(stderr, "NOVA_FAULT: guest rip=0x%llx (exact)\n", (unsigned long long)exact);
		}
		// Guest code around the faulting instruction (x86-64, from rip-0x40), read safely.
		uint8_t code[160] {};
		iovec local {code, sizeof(code)};
		iovec remote {reinterpret_cast<void*>(TranslateGuestVA(rip - 0x40)), sizeof(code)};
		if (process_vm_readv(getpid(), &local, 1, &remote, 1, 0) == static_cast<ssize_t>(sizeof(code))) {
			for (size_t off = 0; off < sizeof(code); off += 32) {
				char line[3 * 32 + 1] {};
				for (size_t i = 0; i < 32; i++) std::snprintf(line + 3 * i, 4, "%02x ", code[off + i]);
				std::fprintf(stderr, "NOVA_FAULT: guest code rip%+lld: %s\n", static_cast<long long>(off) - 0x40, line);
			}
		}
	}
	{
		const uint64_t last = t_thread.last_host.load();
		Dl_info info {};
		const char* name = "?";
		char* demangled = nullptr;
		if (last != 0 && dladdr(reinterpret_cast<void*>(last), &info) != 0 && info.dli_sname != nullptr) {
			int status = 0;
			demangled = abi::__cxa_demangle(info.dli_sname, nullptr, nullptr, &status);
			name = demangled != nullptr ? demangled : info.dli_sname;
		} else if (const char* known = HostName(last); known != nullptr) {
			name = known;
		}
		std::fprintf(stderr, "NOVA_FAULT: last host call %.160s (gates=%llu)\n", name, (unsigned long long)t_thread.gates.load());
		std::free(demangled);
	}
	for (uint32_t i = 0; i < 16 && i < t_thread.recent_pos; i++) {
		const auto& r = t_thread.recent[(t_thread.recent_pos - 1 - i) % 16];
		Dl_info info {};
		const char* name = "?";
		char* demangled = nullptr;
		if (dladdr(reinterpret_cast<void*>(r.target), &info) != 0 && info.dli_sname != nullptr) {
			int status = 0;
			demangled = abi::__cxa_demangle(info.dli_sname, nullptr, nullptr, &status);
			name = demangled != nullptr ? demangled : info.dli_sname;
		} else if (const char* known = HostName(r.target); known != nullptr) {
			name = known;
		}
		std::fprintf(stderr, "NOVA_FAULT:   call -%u: %.110s (0x%llx, 0x%llx) -> 0x%llx\n", i, name,
		             (unsigned long long)r.a0, (unsigned long long)r.a1, (unsigned long long)r.ret);
		std::free(demangled);
	}
	if (!in_jit) return;
	// FEX x86-64 static register allocation (Arm64Emitter.cpp x64::SRA).
	static const char* names[16] = {"rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
	                                "r8 ", "r9 ", "r10", "r11", "r12", "r13", "r14", "r15"};
	static const int host[16] = {4, 7, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 29};
	for (int i = 0; i < 16; i += 4) {
		std::fprintf(stderr, "NOVA_FAULT: %s=%016llx %s=%016llx %s=%016llx %s=%016llx\n",
		             names[i], (unsigned long long)uc->uc_mcontext.regs[host[i]],
		             names[i + 1], (unsigned long long)uc->uc_mcontext.regs[host[i + 1]],
		             names[i + 2], (unsigned long long)uc->uc_mcontext.regs[host[i + 2]],
		             names[i + 3], (unsigned long long)uc->uc_mcontext.regs[host[i + 3]]);
	}
	// Return addresses: guest stack values that point into the low guest image area.
	const uint64_t rsp = uc->uc_mcontext.regs[8];
	if (rsp >= 0x10000 && (rsp & 7) == 0) {
		int shown = 0;
		for (int i = 0; i < 512 && shown < 16; i++) {
			uint64_t v = 0;
			struct iovec local {&v, 8}, remote {reinterpret_cast<void*>(rsp + 8 * i), 8};
			if (process_vm_readv(getpid(), &local, 1, &remote, 1, 0) != 8) break;
			if (v >= 0x800000000ull && v < 0x1000000000ull) {
				std::fprintf(stderr, "NOVA_FAULT:   [rsp+0x%x] 0x%llx\n", i * 8, (unsigned long long)v);
				shown++;
			}
		}
	}
}

namespace {
// ---- Host (emulator) accesses to translated guest addresses (guest VA >= 2^39) -------------
// Emulator code that dereferences such a guest pointer faults: the address does not exist on
// the host. The faulting load/store is emulated on the translated host address and skipped.

uint64_t ReadX(ucontext_t* uc, uint32_t n) {
	return n == 31 ? 0 : uc->uc_mcontext.regs[n];
}
uint64_t ReadBase(ucontext_t* uc, uint32_t n) {
	return n == 31 ? uc->uc_mcontext.sp : uc->uc_mcontext.regs[n];
}
void WriteBase(ucontext_t* uc, uint32_t n, uint64_t v) {
	if (n == 31) {
		uc->uc_mcontext.sp = v;
	} else {
		uc->uc_mcontext.regs[n] = v;
	}
}
void WriteX(ucontext_t* uc, uint32_t n, uint64_t v) {
	if (n != 31) uc->uc_mcontext.regs[n] = v;
}
uint8_t* VReg(ucontext_t* uc, uint32_t n) {
	auto* cursor = reinterpret_cast<uint8_t*>(uc->uc_mcontext.__reserved);
	auto* end = cursor + sizeof(uc->uc_mcontext.__reserved);
	while (cursor + sizeof(_aarch64_ctx) <= end) {
		auto* head = reinterpret_cast<_aarch64_ctx*>(cursor);
		if (head->magic == 0 || head->size < sizeof(_aarch64_ctx) ||
		    head->size > static_cast<size_t>(end - cursor) || (head->size & 15)) break;
		if (head->magic == FPSIMD_MAGIC && head->size >= sizeof(fpsimd_context)) {
			return reinterpret_cast<uint8_t*>(&reinterpret_cast<fpsimd_context*>(head)->vregs[n]);
		}
		cursor += head->size;
	}
	return nullptr;
}
uint8_t* HostOf(uint64_t guest) {
	return reinterpret_cast<uint8_t*>(TranslateGuestVA(guest));
}
int64_t SignExtend(uint64_t v, unsigned bits) {
	const uint64_t m = uint64_t {1} << (bits - 1);
	v &= (bits == 64) ? ~uint64_t {0} : ((uint64_t {1} << bits) - 1);
	return static_cast<int64_t>((v ^ m) - m);
}
uint64_t LoadN(const uint8_t* p, unsigned bytes) {
	uint64_t v = 0;
	std::memcpy(&v, p, bytes);
	return v;
}
void StoreN(uint8_t* p, uint64_t v, unsigned bytes) {
	std::memcpy(p, &v, bytes);
}
template<typename T>
T AtomicOp(T* p, uint32_t op, T v) {
	switch (op) {
	case 0: return __atomic_fetch_add(p, v, __ATOMIC_SEQ_CST);
	case 1: return __atomic_fetch_and(p, static_cast<T>(~v), __ATOMIC_SEQ_CST);
	case 2: return __atomic_fetch_xor(p, v, __ATOMIC_SEQ_CST);
	case 3: return __atomic_fetch_or(p, v, __ATOMIC_SEQ_CST);
	default: return __atomic_exchange_n(p, v, __ATOMIC_SEQ_CST);
	}
}
uint64_t AtomicSized(uint8_t* p, unsigned bytes, uint32_t op, uint64_t v) {
	switch (bytes) {
	case 1: return AtomicOp(reinterpret_cast<uint8_t*>(p), op, static_cast<uint8_t>(v));
	case 2: return AtomicOp(reinterpret_cast<uint16_t*>(p), op, static_cast<uint16_t>(v));
	case 4: return AtomicOp(reinterpret_cast<uint32_t*>(p), op, static_cast<uint32_t>(v));
	default: return AtomicOp(reinterpret_cast<uint64_t*>(p), op, v);
	}
}

// Returns true if the instruction at pc was emulated (pc advanced).
bool EmulateHighAccess(ucontext_t* uc, uint64_t fault) {
	if (!FEXCore::Nova::GuestVAEnabled || fault < FEXCore::Nova::kGuestVALowLimit || TranslateGuestVA(fault) == fault) {
		return false;
	}
	const uint32_t insn = *reinterpret_cast<const uint32_t*>(uc->uc_mcontext.pc);
	const uint32_t rt = insn & 31, rn = (insn >> 5) & 31;
	const uint32_t size = insn >> 30;

	// Bionic's large zero fills use DC ZVA, Xt (including d50b7428: x8).
	// It zeros the whole naturally aligned block, not merely the operand byte.
	if ((insn & 0xffffffe0u) == 0xd50b7420u) {
		uint64_t dczid = 0;
#if defined(__aarch64__)
		asm volatile("mrs %0, dczid_el0" : "=r"(dczid));
#else
		return false; // The synthetic host decoder has no architectural DCZID_EL0.
#endif
		if ((dczid & 16u) != 0 || rt == 31) return false;
		const uint64_t bytes = uint64_t{4} << (dczid & 15u);
		const uint64_t base = ReadX(uc, rt) & ~(bytes - 1);
		const auto host = TranslateGuestVA(base);
		if (base < FEXCore::Nova::kGuestVALowLimit || host == base) return false;
		// Slot boundaries are aligned more coarsely than any architectural ZVA block.
		// Preserve Xt: libc advances its original guest pointer after this instruction.
		std::memset(reinterpret_cast<void*>(host), 0, bytes);
		uc->uc_mcontext.pc += 4;
		return true;
	}

	// Advanced SIMD LD1/ST1 (two contiguous vectors) and LD2/ST2 (interleaved
	// two-structure vectors), not lane or SVE variants. Bit 13 chooses the layout;
	// all other opcode bits are identical for the two-register forms.
	// A real Bionic memcpy faulted on 4c40a021: LD1 {v1.16b, v2.16b}, [x1].
	// Keep the original guest address, vector register wrap, and post-index semantics.
	if ((insn & 0xBF20D000u) == 0x0C008000u) {
		const bool post = (insn >> 23) & 1, load = (insn >> 22) & 1;
		const bool contiguous = (insn & (1u << 13)) != 0;
		const unsigned rm = (insn >> 16) & 31, element = 1u << ((insn >> 10) & 3);
		const unsigned width = (insn & (1u << 30)) ? 16 : 8, total = width * 2;
		if ((!post && rm != 0) || (!contiguous && width == 8 && element == 8)) return false;
		const uint64_t base = ReadBase(uc, rn);
		if (base < FEXCore::Nova::kGuestVALowLimit || base > (uint64_t{1} << 47) - total ||
		    (rn == 31 && (base & 15))) return false;
		uint8_t* vectors[2] = {VReg(uc, rt), VReg(uc, (rt + 1) & 31)};
		if (!vectors[0] || !vectors[1]) return false;
		const uint64_t increment = rm == 31 ? total : ReadX(uc, rm);
		// Resolve every byte before mutation: adjacent guest slots need not be adjacent on host.
		uint8_t* addresses[32];
		iovec remote[32];
		uint8_t data[32];
		for (unsigned i = 0; i < total; ++i) {
			const uint64_t translated = TranslateGuestVA(base + i);
			if (translated == base + i) return false;
			addresses[i] = reinterpret_cast<uint8_t*>(translated);
			remote[i] = {addresses[i], 1};
		}
		// Reject inaccessible backing pages before writing anything. This does not make the
		// operation atomic against concurrent unmapping/protection changes.
		iovec local {data, total};
		if (syscall(SYS_process_vm_readv, getpid(), &local, 1UL, remote, static_cast<unsigned long>(total), 0UL) != total) return false;
		for (unsigned lane = 0; lane < width / element; ++lane) {
			for (unsigned reg = 0; reg < 2; ++reg) {
				for (unsigned byte = 0; byte < element; ++byte) {
					const unsigned offset = contiguous ? reg * width + lane * element + byte
					                                   : (lane * 2 + reg) * element + byte;
					if (load) vectors[reg][lane * element + byte] = data[offset];
					else *addresses[offset] = vectors[reg][lane * element + byte];
				}
			}
		}
		if (load && width == 8) {
			std::memset(vectors[0] + 8, 0, 8);
			std::memset(vectors[1] + 8, 0, 8);
		}
		if (post) WriteBase(uc, rn, base + increment);
		uc->uc_mcontext.pc += 4;
		return true;
	}

	// Load/store exclusive, ordered (LDAR/STLR/LDXR/STXR...) and CAS: xx 001000 ...
	if ((insn & 0x3F000000) == 0x08000000) {
		const bool o2 = (insn >> 23) & 1, l = (insn >> 22) & 1, o1 = (insn >> 21) & 1;
		const uint32_t rs = (insn >> 16) & 31;
		const unsigned bytes = 1u << size;
		uint8_t* p = HostOf(ReadBase(uc, rn));
		if (o2 && o1) { // CAS
			uint64_t expected = ReadX(uc, rs);
			const uint64_t desired = ReadX(uc, rt);
			uint64_t observed = 0;
			switch (bytes) {
			case 1: { uint8_t e = expected; __atomic_compare_exchange_n(p, &e, static_cast<uint8_t>(desired), false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); observed = e; break; }
			case 2: { uint16_t e = expected; __atomic_compare_exchange_n(reinterpret_cast<uint16_t*>(p), &e, static_cast<uint16_t>(desired), false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); observed = e; break; }
			case 4: { uint32_t e = expected; __atomic_compare_exchange_n(reinterpret_cast<uint32_t*>(p), &e, static_cast<uint32_t>(desired), false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); observed = e; break; }
			default: { uint64_t e = expected; __atomic_compare_exchange_n(reinterpret_cast<uint64_t*>(p), &e, desired, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); observed = e; break; }
			}
			WriteX(uc, rs, observed);
		} else if (o1) { // LDXP / STXP (pairs)
			const unsigned eb = size == 3 ? 8 : 4;
			const uint32_t rt2 = (insn >> 10) & 31;
			__atomic_thread_fence(__ATOMIC_SEQ_CST);
			if (l) {
				WriteX(uc, rt, LoadN(p, eb));
				WriteX(uc, rt2, LoadN(p + eb, eb));
			} else {
				StoreN(p, ReadX(uc, rt), eb);
				StoreN(p + eb, ReadX(uc, rt2), eb);
				WriteX(uc, rs, 0);
			}
			__atomic_thread_fence(__ATOMIC_SEQ_CST);
		} else {
			__atomic_thread_fence(__ATOMIC_SEQ_CST);
			if (l) {
				WriteX(uc, rt, LoadN(p, bytes));
			} else {
				StoreN(p, ReadX(uc, rt), bytes);
				if (!o2) WriteX(uc, rs, 0); // STXR: exclusive store always succeeds
			}
			__atomic_thread_fence(__ATOMIC_SEQ_CST);
		}
		uc->uc_mcontext.pc += 4;
		return true;
	}

	// LSE atomics: xx 111 0 00 A R 1 Rs o3 opc 00 Rn Rt
	if ((insn & 0x3F200C00) == 0x38200000) {
		const uint32_t rs = (insn >> 16) & 31;
		const uint32_t o3 = (insn >> 15) & 1, opc = (insn >> 12) & 7;
		if (opc > 3 && !o3) return false; // LDSMAX & co. not handled
		const unsigned bytes = 1u << size;
		const uint64_t old = AtomicSized(HostOf(ReadBase(uc, rn)), bytes, o3 ? 4 : opc, ReadX(uc, rs));
		WriteX(uc, rt, old);
		uc->uc_mcontext.pc += 4;
		return true;
	}

	// Load/store pair: xx 101 V 0 idx(2) L imm7 Rt2 Rn Rt
	if ((insn & 0x3A000000) == 0x28000000) {
		const bool v = (insn >> 26) & 1, l = (insn >> 22) & 1;
		const uint32_t idx = (insn >> 23) & 3, rt2 = (insn >> 10) & 31;
		const uint32_t opc = insn >> 30;
		unsigned bytes;
		bool sign32 = false;
		if (v) {
			bytes = 4u << opc;
		} else {
			bytes = (opc & 2) ? 8 : 4;
			sign32 = opc == 1; // LDPSW
		}
		const int64_t off = SignExtend((insn >> 15) & 0x7F, 7) * static_cast<int64_t>(bytes);
		const uint64_t base = ReadBase(uc, rn);
		const uint64_t ea = idx == 1 ? base : base + off;
		uint8_t* p = HostOf(ea);
		for (int k = 0; k < 2; k++) {
			const uint32_t r = k == 0 ? rt : rt2;
			uint8_t* q = p + k * bytes;
			if (v) {
				uint8_t* vr = VReg(uc, r);
				if (vr == nullptr) return false;
				if (l) {
					std::memset(vr, 0, 16);
					std::memcpy(vr, q, bytes);
				} else {
					std::memcpy(q, vr, bytes);
				}
			} else if (l) {
				const uint64_t val = LoadN(q, bytes);
				WriteX(uc, r, sign32 ? static_cast<uint64_t>(SignExtend(val, 32)) : val);
			} else {
				StoreN(q, ReadX(uc, r), bytes);
			}
		}
		if (idx == 1 || idx == 3) WriteBase(uc, rn, base + off);
		uc->uc_mcontext.pc += 4;
		return true;
	}

	// Load/store register: xx 111 V 0x ...
	if ((insn & 0x3A000000) == 0x38000000) {
		const bool v = (insn >> 26) & 1;
		const uint32_t opc = (insn >> 22) & 3;
		const uint64_t base = ReadBase(uc, rn);
		uint64_t ea = base;
		bool writeback = false;
		uint64_t wb = 0;
		unsigned bytes = 1u << size;
		if (v && (opc & 2)) bytes = 16; // Q register
		if ((insn >> 24) & 1) { // unsigned scaled imm12
			ea = base + (static_cast<uint64_t>((insn >> 10) & 0xFFF) * bytes);
		} else if (((insn >> 21) & 1) && ((insn >> 10) & 3) == 2) { // register offset
			const uint32_t rm = (insn >> 16) & 31, option = (insn >> 13) & 7;
			const bool s = (insn >> 12) & 1;
			uint64_t m = ReadX(uc, rm);
			switch (option) {
			case 2: m = static_cast<uint32_t>(m); break;                        // UXTW
			case 6: m = static_cast<uint64_t>(SignExtend(m, 32)); break;         // SXTW
			default: break;                                                      // LSL / SXTX
			}
			unsigned shift = 0;
			while ((1u << shift) < bytes) shift++;
			ea = base + (s ? (m << shift) : m);
		} else if (!((insn >> 21) & 1)) { // imm9: unscaled / post / pre
			const int64_t imm = SignExtend((insn >> 12) & 0x1FF, 9);
			const uint32_t type = (insn >> 10) & 3;
			if (type == 1) { // post-index
				ea = base;
				writeback = true;
				wb = base + imm;
			} else if (type == 3) { // pre-index
				ea = base + imm;
				writeback = true;
				wb = ea;
			} else {
				ea = base + imm; // unscaled (LDUR/STUR) or unprivileged
			}
		} else {
			return false;
		}
		uint8_t* p = HostOf(ea);
		if (v) {
			uint8_t* vr = VReg(uc, rt);
			if (vr == nullptr) return false;
			if (opc & 1) { // load
				std::memset(vr, 0, 16);
				std::memcpy(vr, p, bytes);
			} else {
				std::memcpy(p, vr, bytes);
			}
		} else {
			if (size == 3 && opc == 2) { // PRFM
				uc->uc_mcontext.pc += 4;
				return true;
			}
			if (opc == 0) {
				StoreN(p, ReadX(uc, rt), bytes);
			} else {
				uint64_t val = LoadN(p, bytes);
				if (opc == 2) val = static_cast<uint64_t>(SignExtend(val, bytes * 8));          // to X
				if (opc == 3) val = static_cast<uint32_t>(SignExtend(val, bytes * 8));          // to W
				WriteX(uc, rt, val);
			}
		}
		if (writeback) WriteBase(uc, rn, wb);
		uc->uc_mcontext.pc += 4;
		return true;
	}
	return false;
}
} // namespace

bool HandleHostFault(int signal, siginfo_t* info, void* ucontext) {
	auto* uc = static_cast<ucontext_t*>(ucontext);
	const uint64_t pc = uc->uc_mcontext.pc;
	// Host code jumped into guest code (a C++ call through a guest function pointer).
	// Any instruction fetch fault is a host jump into guest code: guest mappings are never
	// host-executable and the emulator does not register every guest module with NovaFex.
	if (signal == SIGSEGV && reinterpret_cast<uint64_t>(info->si_addr) == pc && pc >= 0x10000) {
		uc->uc_mcontext.regs[16] = pc;
		uc->uc_mcontext.pc = reinterpret_cast<uint64_t>(&nova_guest_bridge_entry);
		uc->uc_mcontext.pstate &= ~(uint64_t {3} << 10); // clear BTYPE: not a branch into the bridge
		return true;
	}
	// Emulator code touching a guest address above the host address space.
	if (signal == SIGSEGV && EmulateHighAccess(uc, reinterpret_cast<uint64_t>(info->si_addr))) {
		NoteHostEmulation(pc);
		static std::atomic<int> logged {0};
		if (logged.fetch_add(1, std::memory_order_relaxed) < 8) {
			char buf[160];
			const int n = std::snprintf(buf, sizeof(buf), "NOVA_FEX: host access to guest VA %p emulated (pc=0x%llx)\n",
			                            info->si_addr, static_cast<unsigned long long>(pc));
			(void)!write(2, buf, n);
		}
		return true;
	}
	// Unaligned atomics emitted by the JIT.
	if (signal == SIGBUS && g_initialized && t_thread.fex != nullptr &&
	    g_ctx->IsAddressInCodeBuffer(t_thread.fex, pc)) {
		auto result = FEXCore::ArchHelpers::Arm64::HandleUnalignedAccess(
		    t_thread.fex, FEXCore::ArchHelpers::Arm64::UnalignedHandlerType::HalfBarrier, pc,
		    reinterpret_cast<uint64_t*>(uc->uc_mcontext.regs));
		if (result) {
			uc->uc_mcontext.pc = pc + *result;
			return true;
		}
	}
	return false;
}

} // namespace NovaFex

// Called by nova_guest_bridge_entry with the target and the saved AAPCS argument registers:
// regs[0..7] = x0..x7, then q0..q7 (16 bytes each). Writes x0,x1,q0,q1 back.
extern "C" __attribute__((visibility("hidden"))) void nova_bridge_call(uint64_t target, uint64_t* regs) {
	NovaFex::CallArgs args;
	for (int i = 0; i < 8; i++) {
		args.gpr[i] = regs[i];
	}
	auto* q = reinterpret_cast<NovaFex::Vec128*>(regs + 8);
	for (int i = 0; i < 8; i++) {
		args.vec[i] = q[i];
	}
	NovaFex::CallGuest(target, &args);
	regs[0] = args.ret_gpr[0];
	regs[1] = args.ret_gpr[1];
	q[0] = args.ret_vec[0];
	q[1] = args.ret_vec[1];
}

namespace NovaFexWatchpoint {
void LunaBoundary(uint64_t object, uint64_t vtable, uint64_t event) noexcept {
  if (vtable != luna_vtable.load(std::memory_order_acquire) || !object || (object & 7)) return;
  if (event == 1) {
    const bool ok = NovaFex::RegisterVerifiedCheckpointObject(object);
    std::fprintf(stderr, "NOVA_LUNA_OBJECT: %s type=SaveGameInstanceData object=0x%llx vtable=0x%llx fields=+0x38/+0x40\n",
      ok ? "registered" : "registry_full_or_invalid", static_cast<unsigned long long>(object),
      static_cast<unsigned long long>(vtable));
  } else if (event == 2 && RetireVerifiedObject(object)) {
    std::fprintf(stderr, "NOVA_LUNA_OBJECT: retired object=0x%llx\n", static_cast<unsigned long long>(object));
    NovaFex::DumpWatchpointTrace();
  }
}
}




