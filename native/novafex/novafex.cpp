#include <sys/uio.h>
// Nova PS5 - FEXCore embedding for guest-only translation. See novafex.h.
// SPDX-License-Identifier: GPL-2.0-or-later
#include "novafex.h"

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
namespace {

using FEXCore::X86State::REG_R8;
using FEXCore::X86State::REG_R9;
using FEXCore::X86State::REG_RAX;
using FEXCore::X86State::REG_RCX;
using FEXCore::X86State::REG_RDI;
using FEXCore::X86State::REG_RDX;
using FEXCore::X86State::REG_RSI;
using FEXCore::X86State::REG_RSP;

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
	int tid = 0;
	~ThreadData();
	uint64_t guest_stack_top = 0;
	uint64_t fs_base = 0;
	uint64_t gate_stack_args = 0;
	uint64_t gate_rsp = 0;
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

void GateDispatch(void* block_pointer) {
	auto* block = static_cast<GateBlock*>(block_pointer);
	auto& t = t_thread;
	t.gates.fetch_add(1, std::memory_order_relaxed);
	g_total_gates.fetch_add(1, std::memory_order_relaxed);
	const auto saved_in_host = t.in_host.load(std::memory_order_relaxed);
	t.in_host.store(block->target, std::memory_order_relaxed);
	t.last_host.store(block->target, std::memory_order_relaxed);
	const auto saved_args = t.gate_stack_args;
	const auto saved_rsp = t.gate_rsp;
	t.gate_stack_args = block->stack_args;
	t.gate_rsp = reinterpret_cast<uint64_t>(block) - 8;
	nova_call_native(block);
	t.in_host.store(saved_in_host, std::memory_order_relaxed);
	t.gate_stack_args = saved_args;
	t.gate_rsp = saved_rsp;
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

// Stall diagnostics: every host thread prints its own native backtrace on SIGRTMIN+6.
void DumpSelf(int, siginfo_t*, void*) {
	void* frames[40];
	const int count = backtrace(frames, 40);
	char header[96];
	const int n = std::snprintf(header, sizeof(header), "NOVA_FEX: --- stack of tid %d ---\n", static_cast<int>(gettid()));
	(void)!write(2, header, static_cast<size_t>(n));
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
	const int report_every = EnvInt("NOVA_FEX_HEARTBEAT", 30);
	const int freeze_after = EnvInt("NOVA_FREEZE_SECONDS", 4);
	// The Nova launcher that started this process. Kyty may run outside the session's process
	// tree (outside proot); when the launcher is gone the session has ended.
	const pid_t launcher = static_cast<pid_t>(EnvInt("NOVA_LAUNCHER_PID", 0));
	uint64_t last_frames = 0, report_frames = 0, report_gates = 0, last_gates = 0;
	int frozen_for = 0, quiet_for = 0, freeze_episodes = 0;
	bool stall_dumped = false;
	for (int tick = 1;; tick++) {
		sleep(1);
		if (getppid() == 1 || (launcher > 0 && kill(launcher, 0) != 0 && errno == ESRCH)) {
			std::fprintf(stderr, "NOVA_FEX: launcher gone, exiting\n");
			_exit(0);
		}
		const auto frames = g_frames.load(std::memory_order_relaxed);
		const auto gates = g_total_gates.load(std::memory_order_relaxed);
		const auto calls = g_total_calls.load(std::memory_order_relaxed);
		if (frames != last_frames) {
			last_frames = frames;
			frozen_for = 0;
		} else if (frames != 0) {
			frozen_for++;
		}
		// The game had been presenting frames and stopped: report where every thread is. Loading
		// screens can pause presentation for a while, so the first reports only read /proc; the
		// stacks (which interrupt each thread) come only if it stays frozen.
		if (freeze_after > 0 && frames != 0 && freeze_episodes <= 3 &&
		    (frozen_for == freeze_after || frozen_for == freeze_after * 3 || frozen_for == freeze_after * 5)) {
			if (frozen_for == freeze_after) freeze_episodes++;
			std::fprintf(stderr, "NOVA_FREEZE: no frame for %d s (frames=%llu gates=%llu guest_calls=%llu rss=%ldMB avail=%ldMB)\n",
			             frozen_for, (unsigned long long)frames, (unsigned long long)gates, (unsigned long long)calls,
			             ReadKb("/proc/self/status", "VmRSS:") / 1024, ReadKb("/proc/meminfo", "MemAvailable:") / 1024);
			ReportGuestThreads();
			ReportTasks();
			if (frozen_for == freeze_after * 5) DumpAllThreads();
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
			const int span = tick == 5 ? 5 : report_every;
			std::fprintf(stderr, "NOVA_FEX: heartbeat fps=%.1f frames=%llu gates=%llu (+%llu) guest_calls=%llu threads=%zu rss=%ldMB avail=%ldMB\n",
			             static_cast<double>(frames - report_frames) / span, (unsigned long long)frames,
			             (unsigned long long)gates, (unsigned long long)(gates - report_gates), (unsigned long long)calls,
			             g_threads.size(), ReadKb("/proc/self/status", "VmRSS:") / 1024,
			             ReadKb("/proc/meminfo", "MemAvailable:") / 1024);
			report_frames = frames;
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
	g_ctx->HandleCallback(t.fex, target);
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

void InvalidateGuestCode(uint64_t start, uint64_t size) {
	if (g_ctx) {
		g_ctx->InvalidateCodeBuffersCodeRange(start, size);
	}
}

void NoteFrame() {
	g_frames.fetch_add(1, std::memory_order_relaxed);
}

void ReportGuestFault(void* ucontext) {
	auto* uc = static_cast<ucontext_t*>(ucontext);
	if (uc == nullptr) return;
	const uint64_t pc = uc->uc_mcontext.pc;
	const bool in_jit = g_initialized && t_thread.fex != nullptr && g_ctx->IsAddressInCodeBuffer(t_thread.fex, pc);
	std::fprintf(stderr, "NOVA_FAULT: host pc=0x%llx %s\n", (unsigned long long)pc, in_jit ? "(guest JIT code)" : "(host code)");
	if (t_thread.fex != nullptr) {
		const auto& st = t_thread.fex->CurrentFrame->State;
		std::fprintf(stderr, "NOVA_FAULT: guest block rip=0x%llx\n", (unsigned long long)st.rip);
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
		}
		std::fprintf(stderr, "NOVA_FAULT: last host call %.160s (gates=%llu)\n", name, (unsigned long long)t_thread.gates.load());
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
