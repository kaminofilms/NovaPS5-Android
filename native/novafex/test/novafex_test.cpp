// Nova PS5 - bridge tests for the embedded FEXCore (run on an AArch64 Linux host).
// SPDX-License-Identifier: GPL-2.0-or-later
#include "novafex.h"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <thread>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
#include <dlfcn.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>

namespace {

int g_failures = 0;

void Check(const char* name, bool ok, const char* detail = "") {
	std::printf("NOVAFEX_TEST: %-28s %s %s\n", name, ok ? "PASS" : "FAIL", detail);
	std::fflush(stdout);
	if (!ok) g_failures++;
}

void FaultHandler(int signal, siginfo_t* info, void* ucontext) {
	if (NovaFex::HandleHostFault(signal, info, ucontext)) {
		return;
	}
	auto* uc = static_cast<ucontext_t*>(ucontext);
	char buf[160];
	int n = std::snprintf(buf, sizeof(buf), "NOVAFEX_TEST: unhandled signal %d addr=%p pc=0x%llx\n", signal,
	                      info->si_addr, static_cast<unsigned long long>(uc->uc_mcontext.pc));
	(void)!write(2, buf, n);
	auto where = [](const char* tag, uint64_t a) {
		Dl_info di {};
		if (dladdr(reinterpret_cast<void*>(a), &di) && di.dli_fname) {
			std::fprintf(stderr, "  %s 0x%llx %s+0x%llx (%s)\n", tag, (unsigned long long)a, di.dli_fname,
			             (unsigned long long)(a - reinterpret_cast<uint64_t>(di.dli_fbase)), di.dli_sname ? di.dli_sname : "?");
		} else {
			std::fprintf(stderr, "  %s 0x%llx (JIT/anon)\n", tag, (unsigned long long)a);
		}
	};
	where("pc", uc->uc_mcontext.pc);
	where("lr", uc->uc_mcontext.regs[30]);
	auto* fp = reinterpret_cast<uint64_t*>(uc->uc_mcontext.regs[29]);
	for (int i = 0; i < 16 && fp != nullptr && (reinterpret_cast<uint64_t>(fp) & 7) == 0; i++) {
		where("frame", fp[1]);
		fp = reinterpret_cast<uint64_t*>(fp[0]);
	}
	_exit(90 + signal % 10);
}

// Guest code buffer: readable/writable only, never host-executable.
struct GuestCode {
	uint8_t* base = nullptr;
	size_t used = 0;
	uint64_t Emit(std::initializer_list<uint8_t> bytes) {
		auto start = reinterpret_cast<uint64_t>(base + used);
		for (auto b: bytes) base[used++] = b;
		used = (used + 15) & ~size_t {15};
		return start;
	}
	void Imm64(size_t at_from_end, uint64_t value) {
		std::memcpy(base + at_from_end, &value, 8);
	}
};

std::atomic<uint64_t> g_counter {0};

uint64_t HostMul(uint64_t a, uint64_t b) { return a * b; }
void HostInc() { g_counter.fetch_add(1, std::memory_order_relaxed); }
uint64_t g_guest_add = 0;
uint64_t HostNested(uint64_t x) {
	// Plain C++ call through a guest function pointer: faults, the handler bridges to FEX.
	auto fn = reinterpret_cast<uint64_t (*)(uint64_t, uint64_t)>(g_guest_add);
	return fn(x, 100);
}
double HostEight(int64_t a, int64_t b, int64_t c, int64_t d, int64_t e, int64_t f, int64_t g, int64_t h,
                 double x, double y) {
	return static_cast<double>(a + 2 * b + 3 * c + 4 * d + 5 * e + 6 * f + 7 * g + 8 * h) + x * y;
}
int64_t HostTen(int64_t a, int64_t b, int64_t c, int64_t d, int64_t e, int64_t f, int64_t g, int64_t h, int64_t i,
                int64_t j) {
	return a + b + c + d + e + f + g + h + i * 1000 + j * 10000;
}
uint64_t HostStackArgs() {
	// Variadic HLE functions read their SysV overflow area through this pointer.
	auto* slots = reinterpret_cast<uint64_t*>(NovaFex::CurrentGateStackArgs());
	return slots[0] + slots[1];
}

NovaFex::GuestCallContext g_ctx_seen {};
bool g_ctx_ok = false;
uint64_t HostContext() {
	g_ctx_ok = NovaFex::GetGuestCallContext(&g_ctx_seen);
	return 7;
}
std::atomic<int> g_hook_runs {0};
uint64_t g_hook_guest = 0;
void GateExitHook() {
	// Runs guest code from the hook, as a signal handler would.
	if (NovaFex::CallGuest(g_hook_guest, 2, 3) == 5) g_hook_runs.fetch_add(1);
}

// mov rax, imm64; call rax  ->  48 B8 <imm64> FF D0
std::vector<uint8_t> CallAbs(uint64_t target) {
	std::vector<uint8_t> v {0x48, 0xB8};
	for (int i = 0; i < 8; i++) v.push_back(static_cast<uint8_t>(target >> (8 * i)));
	v.push_back(0xFF);
	v.push_back(0xD0);
	return v;
}

uint64_t EmitVec(GuestCode& code, const std::vector<uint8_t>& bytes) {
	auto start = reinterpret_cast<uint64_t>(code.base + code.used);
	std::memcpy(code.base + code.used, bytes.data(), bytes.size());
	code.used = (code.used + bytes.size() + 15) & ~size_t {15};
	return start;
}

template<typename F>
double NsPer(uint64_t count, F&& fn) {
	auto t0 = std::chrono::steady_clock::now();
	fn();
	auto t1 = std::chrono::steady_clock::now();
	return std::chrono::duration<double, std::nano>(t1 - t0).count() / static_cast<double>(count);
}

// Android's app seccomp policy traps (SIGSYS) syscalls it does not allow. libnovafex answers
// those with ENOSYS so the caller sees an ordinary "not implemented" error.
bool SeccompTrapToEnosys() {
	const pid_t child = fork();
	if (child == 0) {
		sock_filter filter[] = {
		    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(seccomp_data, nr)),
		    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_sched_getattr, 0, 1),
		    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP),
		    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
		};
		sock_fprog prog {static_cast<unsigned short>(sizeof(filter) / sizeof(filter[0])), filter};
		if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog) != 0) {
			_exit(3);
		}
		uint8_t attr[128] {};
		errno = 0;
		const long r = syscall(__NR_sched_getattr, 0, attr, sizeof(attr), 0);
		_exit(r == -1 && errno == ENOSYS ? 0 : 4);
	}
	int status = 0;
	waitpid(child, &status, 0);
	return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

} // namespace

int main() {
	Check("seccomp SIGSYS -> ENOSYS", SeccompTrapToEnosys());

	struct sigaction sa {};
	sa.sa_sigaction = FaultHandler;
	sa.sa_flags = SA_SIGINFO | SA_NODEFER;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGSEGV, &sa, nullptr);
	sigaction(SIGBUS, &sa, nullptr);

	Check("init", NovaFex::Init());
	if (g_failures) return 1;

	GuestCode code;
	code.base = static_cast<uint8_t*>(mmap(nullptr, 1 << 16, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
	NovaFex::RegisterGuestCodeRange(reinterpret_cast<uint64_t>(code.base), 1 << 16);

	// add(a, b): lea rax, [rdi+rsi]; ret
	const uint64_t add = code.Emit({0x48, 0x8D, 0x04, 0x37, 0xC3});
	g_guest_add = add;
	{
		uint64_t r = NovaFex::CallGuest(add, 40, 2);
		Check("host->guest CallGuest", r == 42);
	}
	{
		auto fn = reinterpret_cast<uint64_t (*)(uint64_t, uint64_t)>(add);
		uint64_t r = fn(1000, 234);
		Check("host->guest fn pointer", r == 1234);
	}
	// sum(n): xor eax,eax; L: add rax,rdi; dec rdi; jnz L; ret
	const uint64_t sum = code.Emit({0x31, 0xC0, 0x48, 0x01, 0xF8, 0x48, 0xFF, 0xCF, 0x75, 0xF8, 0xC3});
	{
		uint64_t r = NovaFex::CallGuest(sum, 100000);
		Check("guest loop", r == 100000ull * 100001ull / 2);
	}
	// call_mul(a,b): sub rsp,8; call gate(HostMul); add rsp,8; add rax,1; ret
	{
		auto v = std::vector<uint8_t> {0x48, 0x83, 0xEC, 0x08};
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostMul)));
		v.insert(v.end(), c.begin(), c.end());
		v.insert(v.end(), {0x48, 0x83, 0xC4, 0x08, 0x48, 0x83, 0xC0, 0x01, 0xC3});
		uint64_t f = EmitVec(code, v);
		uint64_t r = NovaFex::CallGuest(f, 6, 7);
		Check("guest->host gate", r == 43);
	}
	// nested(x): guest -> host gate -> host calls guest add through a pointer -> back; +1
	{
		auto v = std::vector<uint8_t> {0x48, 0x83, 0xEC, 0x08};
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostNested)));
		v.insert(v.end(), c.begin(), c.end());
		v.insert(v.end(), {0x48, 0x83, 0xC4, 0x08, 0x48, 0x83, 0xC0, 0x01, 0xC3});
		uint64_t f = EmitVec(code, v);
		auto fn = reinterpret_cast<uint64_t (*)(uint64_t)>(f);
		uint64_t r = fn(5);
		Check("nested guest->host->guest", r == 106);
	}
	// Eight integer arguments (two on the SysV stack) and two doubles, called through the gate.
	{
		NovaFex::CallArgs args;
		for (int i = 0; i < 8; i++) args.gpr[i] = static_cast<uint64_t>(i + 1);
		double x = 1.5, y = 4.0;
		std::memcpy(&args.vec[0].lo, &x, 8);
		std::memcpy(&args.vec[1].lo, &y, 8);
		NovaFex::CallGuest(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostEight)), &args);
		double r;
		std::memcpy(&r, &args.ret_vec[0].lo, 8);
		Check("8 int + 2 double args", r == 204.0 + 6.0);
	}
	// Ten integer arguments: SysV stack slots 2,3 -> AAPCS stack.
	{
		// ten(): push 10th, 9th, 8th, 7th args then call the gate
		// mov edi,1 .. r9d=6; push 10; push 9; push 8; push 7; call gate; add rsp,32; ret
		std::vector<uint8_t> v {0x48, 0x83, 0xEC, 0x08,           // sub rsp,8 (align)
		                        0xBF, 1, 0, 0, 0, 0xBE, 2, 0, 0, 0, 0xBA, 3, 0, 0, 0, 0xB9, 4, 0, 0, 0,
		                        0x41, 0xB8, 5, 0, 0, 0, 0x41, 0xB9, 6, 0, 0, 0,
		                        0x6A, 10, 0x6A, 9, 0x6A, 8, 0x6A, 7};
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostTen)));
		v.insert(v.end(), c.begin(), c.end());
		v.insert(v.end(), {0x48, 0x83, 0xC4, 0x28, 0xC3}); // add rsp,40; ret
		uint64_t f = EmitVec(code, v);
		int64_t r = static_cast<int64_t>(NovaFex::CallGuest(f));
		Check("10 int args (AAPCS stack)", r == 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9000 + 100000);
	}
	// Stack-argument pointer seen by a variadic-style HLE function.
	{
		std::vector<uint8_t> v {0x6A, 22, 0x6A, 20}; // push 22; push 20 -> slots 0,1 = 20,22
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostStackArgs)));
		v.insert(v.end(), c.begin(), c.end());
		v.insert(v.end(), {0x48, 0x83, 0xC4, 0x10, 0xC3}); // add rsp,16; ret
		uint64_t f = EmitVec(code, v);
		// entry rsp = 8 mod 16; two pushes keep it 8 mod 16 at the call -> gate sees 0 mod 16? (call
		// pushes 8 -> gate entry rsp 0 mod 16). The gate does not depend on alignment for correctness.
		uint64_t r = NovaFex::CallGuest(f);
		Check("gate stack args pointer", r == 42);
	}
	// SSE: addsd xmm0, xmm1; ret  (host double(*)(double,double))
	{
		const uint64_t addsd = code.Emit({0xF2, 0x0F, 0x58, 0xC1, 0xC3});
		auto fn = reinterpret_cast<double (*)(double, double)>(addsd);
		double r = fn(0.25, 2.5);
		Check("double args/return", r == 2.75);
	}
	// FS-relative TLS: mov rax, fs:[0x10]; ret
	{
		static uint64_t tls[4] = {0, 0, 0xABCD1234, 0};
		NovaFex::SetThreadFsBase(reinterpret_cast<uint64_t>(tls));
		const uint64_t fsread = code.Emit({0x64, 0x48, 0x8B, 0x04, 0x25, 0x10, 0, 0, 0, 0xC3});
		Check("fs base", NovaFex::CallGuest(fsread) == 0xABCD1234);
	}
	// Atomic crossing a 64-byte line: mov rax,rsi; lock xadd [rdi],rax; ret
	{
		const uint64_t xadd = code.Emit({0x48, 0x89, 0xF0, 0xF0, 0x48, 0x0F, 0xC1, 0x07, 0xC3});
		alignas(64) static uint8_t line[128];
		uint64_t initial = 0x1111111111111111ull;
		std::memcpy(line + 60, &initial, 8);
		uint64_t old = NovaFex::CallGuest(xadd, reinterpret_cast<uint64_t>(line + 60), 5);
		uint64_t now;
		std::memcpy(&now, line + 60, 8);
		Check("split-line lock xadd", old == initial && now == initial + 5);
	}
	// Other threads get their own FEX thread state.
	{
		std::atomic<int> ok {0};
		std::vector<std::thread> threads;
		for (int i = 0; i < 4; i++) {
			threads.emplace_back([&, i] {
				auto fn = reinterpret_cast<uint64_t (*)(uint64_t, uint64_t)>(add);
				bool good = true;
				for (int k = 0; k < 1000; k++) {
					good &= fn(static_cast<uint64_t>(i), static_cast<uint64_t>(k)) == static_cast<uint64_t>(i + k);
					good &= NovaFex::CallGuest(sum, 10) == 55;
				}
				if (good) ok++;
			});
		}
		for (auto& t: threads) t.join();
		Check("4 host threads", ok == 4);
	}
	// Guest code modified after it ran: InvalidateGuestCode must take FEX's invalidation lock and
	// release it (0.8.2 left it held, so the next block compile waited forever).
	{
		const uint64_t ret1 = code.Emit({0xB8, 1, 0, 0, 0, 0xC3}); // mov eax,1; ret
		const uint64_t r1 = NovaFex::CallGuest(ret1);
		reinterpret_cast<uint8_t*>(ret1)[1] = 2;
		NovaFex::InvalidateGuestCode(ret1, 6);
		std::atomic<int> state {0};
		uint64_t r2 = 0, r3 = 0;
		std::thread t([&] {
			r2 = NovaFex::CallGuest(ret1);
			const uint64_t fresh = code.Emit({0xB8, 9, 0, 0, 0, 0xC3});
			r3 = NovaFex::CallGuest(fresh);
			state = 1;
		});
		for (int i = 0; i < 500 && state == 0; i++) std::this_thread::sleep_for(std::chrono::milliseconds(10));
		const bool done = state == 1;
		if (done) {
			t.join();
		} else {
			t.detach();
		}
		Check("invalidate + recompile", done && r1 == 1 && r2 == 2 && r3 == 9, done ? "" : "(deadlock)");
	}
	// Guest register state seen from inside a gate call (signal context for the guest).
	{
		// push rbx; push r12; mov rbx,0x1111; mov r12,0x2222; call gate; pop r12; pop rbx; ret
		std::vector<uint8_t> v {0x53, 0x41, 0x54, 0x48, 0xC7, 0xC3, 0x11, 0x11, 0, 0, 0x49, 0xC7, 0xC4, 0x22, 0x22, 0, 0};
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostContext)));
		v.insert(v.end(), c.begin(), c.end());
		const size_t ret_off = v.size();
		v.insert(v.end(), {0x41, 0x5C, 0x5B, 0xC3});
		uint64_t f = EmitVec(code, v);
		uint64_t r = NovaFex::CallGuest(f);
		const bool ok = g_ctx_ok && r == 7 && g_ctx_seen.rbx == 0x1111 && g_ctx_seen.r12 == 0x2222 &&
		                g_ctx_seen.rip == f + ret_off &&
		                *reinterpret_cast<const uint64_t*>(g_ctx_seen.rsp - 8) == f + ret_off;
		char d[128];
		std::snprintf(d, sizeof(d), "(rbx=%llx r12=%llx rip=+%llx)", (unsigned long long)g_ctx_seen.rbx,
		              (unsigned long long)g_ctx_seen.r12, (unsigned long long)(g_ctx_seen.rip - f));
		Check("guest call context", ok, d);
	}
	// Gate-exit hook: armed -> runs once per returning gate call, may call guest code, and the
	// gate's own return value survives it.
	{
		g_hook_guest = add;
		NovaFex::SetGateExitHook(&GateExitHook);
		auto v = std::vector<uint8_t> {0x48, 0x83, 0xEC, 0x08};
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostMul)));
		v.insert(v.end(), c.begin(), c.end());
		v.insert(v.end(), {0x48, 0x83, 0xC4, 0x08, 0xC3});
		uint64_t f = EmitVec(code, v);
		const uint64_t before = NovaFex::CallGuest(f, 3, 4);
		const int runs_before = g_hook_runs.load();
		NovaFex::ArmGateExitHook(1);
		const uint64_t armed = NovaFex::CallGuest(f, 5, 6);
		NovaFex::ArmGateExitHook(-1);
		const uint64_t after = NovaFex::CallGuest(f, 2, 2);
		Check("gate exit hook", before == 12 && armed == 30 && after == 4 && runs_before == 0 && g_hook_runs.load() >= 1);
		NovaFex::SetGateExitHook(nullptr);
	}
	// Guest addresses above the host's address space (NOVA_GUEST_VA). Enabled from here on, so
	// only code translated after this point is affected.
	{
		NovaFex::EnableGuestVA();
		constexpr uint64_t kGuestSlot = 0x8fc0000000ull & ~((uint64_t {1} << 30) - 1); // slot of libc's arena top
		void* window = mmap(nullptr, uint64_t {1} << 30, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
		const auto host = reinterpret_cast<uint64_t>(window);
		const uint64_t guest = 0x8fc0000000ull + 0x123450;
		const uint64_t backing = host + (guest - kGuestSlot);
		mprotect(reinterpret_cast<void*>(backing & ~uint64_t {0xfff}), 0x2000, PROT_READ | PROT_WRITE);
		NovaFex::MapGuestVASlot(kGuestSlot, host);
		*reinterpret_cast<uint64_t*>(backing) = 0x1122334455667788ull;
		// load64(p): mov rax, [rdi]; ret
		const uint64_t load64 = code.Emit({0x48, 0x8B, 0x07, 0xC3});
		// store64(p, v): mov [rdi], rsi; ret
		const uint64_t store64 = code.Emit({0x48, 0x89, 0x37, 0xC3});
		// loadidx(base, idx): mov rax, [rdi + rsi*8 + 0x10]; ret
		const uint64_t loadidx = code.Emit({0x48, 0x8B, 0x44, 0xF7, 0x10, 0xC3});
		// xadd(p, v): lock xadd [rdi], rsi; mov rax, rsi; ret
		const uint64_t xadd = code.Emit({0xF0, 0x48, 0x0F, 0xC1, 0x37, 0x48, 0x89, 0xF0, 0xC3});
		const uint64_t r1 = NovaFex::CallGuest(load64, guest);
		NovaFex::CallGuest(store64, guest + 8, 0xCAFEF00Dull);
		const uint64_t stored = *reinterpret_cast<uint64_t*>(backing + 8);
		*reinterpret_cast<uint64_t*>(backing + 0x20) = 77;
		const uint64_t r3 = NovaFex::CallGuest(loadidx, guest, 2); // guest + 16 + 16
		const uint64_t old = NovaFex::CallGuest(xadd, guest + 8, 5);
		const uint64_t after = *reinterpret_cast<uint64_t*>(backing + 8);
		static uint64_t low_cell = 99;
		const uint64_t r_low = NovaFex::CallGuest(load64, reinterpret_cast<uint64_t>(&low_cell));
		const bool ok = r1 == 0x1122334455667788ull && stored == 0xCAFEF00Dull && r3 == 77 && old == 0xCAFEF00Dull &&
		                after == 0xCAFEF00Dull + 5 && r_low == 99 && NovaFex::TranslateGuestVA(guest) == backing;
		char d[160];
		std::snprintf(d, sizeof(d), "(load=%llx store=%llx idx=%llu xadd=%llx/%llx low=%llu)", (unsigned long long)r1,
		              (unsigned long long)stored, (unsigned long long)r3, (unsigned long long)old, (unsigned long long)after,
		              (unsigned long long)r_low);
		Check("guest VA above 2^39", ok, d);
	}
	// Host (emulator) code dereferencing a translated guest address: the fault handler
	// emulates the access on the backing host memory.
	{
		const uint64_t guest = 0x8fc0000000ull + 0x200100;
		const uint64_t host = NovaFex::TranslateGuestVA(guest);
		mprotect(reinterpret_cast<void*>(host & ~uint64_t {0xfff}), 0x2000, PROT_READ | PROT_WRITE);
		auto* p = reinterpret_cast<volatile uint64_t*>(guest);
		*p = 0x55;                                         // STR
		const uint64_t a = *p;                             // LDR
		__atomic_store_n(reinterpret_cast<uint64_t*>(guest + 8), 7, __ATOMIC_RELEASE); // STLR
		const uint64_t b = __atomic_fetch_add(reinterpret_cast<uint64_t*>(guest + 8), 3, __ATOMIC_SEQ_CST);
		uint8_t src[48];
		for (int i = 0; i < 48; i++) src[i] = static_cast<uint8_t>(i);
		std::memcpy(reinterpret_cast<void*>(guest + 64), src, sizeof(src));
		uint8_t back[48] {};
		std::memcpy(back, reinterpret_cast<const void*>(guest + 64), sizeof(back));
		const bool ok = a == 0x55 && b == 7 && *reinterpret_cast<uint64_t*>(host + 8) == 10 &&
		                std::memcmp(src, back, sizeof(src)) == 0 && *reinterpret_cast<uint64_t*>(host) == 0x55;
		Check("host access to guest VA", ok);
	}
	// Overheads.
	{
		// loop(n): push rbx; mov rbx,rdi; L: call gate(HostInc); dec rbx; jnz L; pop rbx; ret
		std::vector<uint8_t> v {0x53, 0x48, 0x89, 0xFB};
		auto c = CallAbs(NovaFex::MakeGate(reinterpret_cast<const void*>(&HostInc)));
		v.insert(v.end(), c.begin(), c.end());
		v.insert(v.end(), {0x48, 0xFF, 0xCB, 0x75, static_cast<uint8_t>(-(12 + 3 + 2)), 0x5B, 0xC3});
		uint64_t f = EmitVec(code, v);
		constexpr uint64_t kN = 1000000;
		g_counter = 0;
		double gate_ns = NsPer(kN, [&] { NovaFex::CallGuest(f, kN); });
		char d[96];
		std::snprintf(d, sizeof(d), "(%.1f ns per guest->host call)", gate_ns);
		Check("gate call overhead", g_counter == kN, d);

		double call_ns = NsPer(kN, [&] {
			for (uint64_t i = 0; i < kN; i++) NovaFex::CallGuest(add, i, 1);
		});
		std::snprintf(d, sizeof(d), "(%.1f ns per CallGuest)", call_ns);
		Check("CallGuest overhead", true, d);

		constexpr uint64_t kF = 20000;
		auto fn = reinterpret_cast<uint64_t (*)(uint64_t, uint64_t)>(add);
		uint64_t acc = 0;
		double fault_ns = NsPer(kF, [&] {
			for (uint64_t i = 0; i < kF; i++) acc += fn(i, 1);
		});
		std::snprintf(d, sizeof(d), "(%.1f ns per fault-bridged call)", fault_ns);
		Check("fault bridge overhead", acc == kF * (kF - 1) / 2 + kF, d);
	}

	std::printf("NOVAFEX_TEST: %s (%d failures)\n", g_failures ? "FAILED" : "ALL PASS", g_failures);
	return g_failures ? 1 : 0;
}
