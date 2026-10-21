#!/usr/bin/env python3
"""0.9.57: report why a game exits on its own.

Owner logs (0.9.56): Super Meat Boy 3D and Luna Abyss end during memory setup with
no fatal message. "FORTIFY: pthread_mutex_lock called on a destroyed mutex"
means static destructors ran, i.e. the process called exit(). Kyty's guest
exit() HLE calls ::exit silently, and the PS5 libc of both Unreal titles reaches
it through libkernel exit (6Z83sYWFlA8). Without the caller there is nothing to
fix against.

Before exiting, print once: exit code, the guest return address and the guest
modules on the stack (module+offset), any text the stack points to (Unreal
fatal messages are UTF-16 on PS5), this thread's last 16 host calls with their
return values (the failing call, if any), and the kernel memory call trace.
Behaviour is otherwise unchanged: the process still exits with the guest code.
"""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0957_EXIT: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


libc = src / 'libs/libC.cpp'
edit(libc, '''[[noreturn]] static KYTY_SYSV_ABI void abort(uint64_t arg0, uint64_t arg1, uint64_t arg2,''',
     '''// Nova 0.9.57: one-shot report of a guest-initiated exit (see patch-0957-guest-exit-report.py).
void NovaReportGuestExit(const char* who, int code) {
#if defined(KYTY_NOVA_FEX)
	static std::atomic<bool> reported {false};
	if (reported.exchange(true)) return;
	NovaFex::GuestCallContext g {};
	const bool have = NovaFex::GetGuestCallContext(&g);
	auto* lk = Common::Singleton<Loader::RuntimeLinker>::Instance();
	auto where = [&](uint64_t value) -> std::string {
		auto* program = lk->FindProgramByAddr(value);
		if (program == nullptr) return fmt::format("0x{:x}", value);
		return fmt::format("{}+0x{:x}", Common::PathToString(program->file_name.filename()), value - program->base_vaddr);
	};
	std::fprintf(stderr, "NOVA_GUEST_EXIT: %s(%d) called by the game itself (0x%x)\\n", who, code, static_cast<unsigned>(code));
	if (have) {
		uint64_t ret = 0;
		if (Graphics::HostMemoryIsReadable(g.rsp)) NovaGuest::Copy(&ret, reinterpret_cast<const void*>(g.rsp), 8);
		std::fprintf(stderr, "NOVA_GUEST_EXIT: return %s rsp=0x%llx rbx=0x%llx rbp=0x%llx r12=0x%llx\\n", where(ret).c_str(),
		             static_cast<unsigned long long>(g.rsp), static_cast<unsigned long long>(g.rbx),
		             static_cast<unsigned long long>(g.rbp), static_cast<unsigned long long>(g.r12));
		int shown = 0, texts = 0;
		for (int i = 0; i < 1024 && (shown < 24 || texts < 6); i++) {
			const auto addr = g.rsp + static_cast<uint64_t>(i) * 8;
			if (!Graphics::HostMemoryIsReadable(addr)) break;
			uint64_t value = 0;
			NovaGuest::Copy(&value, reinterpret_cast<const void*>(addr), 8);
			if (lk->FindProgramByAddr(value) != nullptr) {
				if (shown++ < 24) std::fprintf(stderr, "NOVA_GUEST_EXIT: stack[%03d] %s\\n", i, where(value).c_str());
				continue;
			}
			uint64_t readable = 0;
			if (texts >= 6 || value < 0x10000 || !Graphics::HostMemoryQueryReadable(value, 512, readable) || readable < 8) continue;
			uint8_t raw[512] {};
			NovaGuest::Copy(raw, reinterpret_cast<const void*>(value), std::min<uint64_t>(readable, sizeof(raw)));
			const bool wide = raw[1] == 0 && raw[0] >= 0x20 && raw[0] < 0x7f;
			const int  step = wide ? 2 : 1;
			char out[257] {};
			int  n = 0;
			for (int k = 0; k + step - 1 < static_cast<int>(sizeof(raw)) && n < 256; k += step) {
				const uint8_t c = raw[k];
				if (c == 0 || (wide && raw[k + 1] != 0)) break;
				if (!((c >= 0x20 && c < 0x7f) || c == '\\n' || c == '\\t')) { n = 0; break; }
				out[n++] = static_cast<char>(c);
			}
			if (n >= 8) {
				texts++;
				std::fprintf(stderr, "NOVA_GUEST_EXIT: stack[%03d] text%s \\"%s\\"\\n", i, wide ? " (utf16)" : "", out);
			}
		}
	}
	NovaFex::DumpRecentHostCalls("NOVA_GUEST_EXIT:");
	::Libs::LibKernel::Memory::NovaDumpMemoryTrace();
	std::fflush(stderr);
#else
	(void)who;
	(void)code;
#endif
}

[[noreturn]] static KYTY_SYSV_ABI void abort(uint64_t arg0, uint64_t arg1, uint64_t arg2,''')
edit(libc, '''static KYTY_SYSV_ABI void exit(int code) {
	PRINT_NAME();

	::exit(code);
}''', '''void NovaReportGuestExit(const char* who, int code);

static KYTY_SYSV_ABI void exit(int code) {
	PRINT_NAME();
	NovaReportGuestExit("libc exit", code);

	::exit(code);
}''')

lk = src / 'libs/libKernel.cpp'
edit(lk, '''namespace LibC {
int          GetArgc();
const char** GetArgv();
} // namespace LibC''', '''namespace LibC {
int          GetArgc();
const char** GetArgv();
void         NovaReportGuestExit(const char* who, int code);
} // namespace LibC''')
edit(lk, '''static void KYTY_SYSV_ABI exit(int code) {
	PRINT_NAME();

	::exit(code);
}''', '''static void KYTY_SYSV_ABI exit(int code) {
	PRINT_NAME();
	LibC::NovaReportGuestExit("libkernel exit", code);

	::exit(code);
}''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0957_EXIT: guest exit() reports code, caller, stack modules/texts, recent host calls, memory trace')
