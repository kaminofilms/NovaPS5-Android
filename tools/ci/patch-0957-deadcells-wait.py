#!/usr/bin/env python3
"""0.9.57: restore the WAIT_REG_MEM give-up Dead Cells ran with in 0.8.1-0.9.10.

Dead Cells PPSA15552 makes a GPU queue wait for a 64-bit flag at a fixed
address (0x20edb76d0, func 3 "equal", ref 1) that nothing in the emulated
system ever sets. 0.7.3 (feb5fe7) added a last-resort give-up: after the wait
had lasted 2 s the queue continued, and later waits on a remembered address
continued after 100 ms. With it the owner measured 60 FPS (0.8.1) and
53-57 FPS (0.9.10). 0.9.14 (dd48245) removed it for every title; Dead Cells has
frozen ~30 s into gameplay on every build since (owner logs: same address,
value 0, system Vulkan and Turnip, Fast and Accurate sync).

Restored exactly as in 0.9.10, but only for Dead Cells by default.
NOVA_GPU_WAIT_GIVEUP=1 enables it for any title, =0 disables it.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/graphics/guest_gpu/graphicsRun.cpp'
s = p.read_text()

helper_anchor = 'uint64_t NovaGpuNowMs() {'
if s.count(helper_anchor) != 1:
    raise SystemExit('NOVA_0957: NovaGpuNowMs anchor changed')
s = s.replace(helper_anchor, '''// Nova 0.9.57: WAIT_REG_MEM give-up (0.7.3-0.9.10 behaviour), Dead Cells by default.
bool NovaWaitGiveUp() {
	static const bool enabled = [] {
		const char* value = std::getenv("NOVA_GPU_WAIT_GIVEUP");
		if (value && value[0] == '0') return false;
		if (value && value[0] == '1') return true;
		const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
		return title && std::string_view(title) == "PPSA15552";
	}();
	return enabled;
}
const void* g_nova_bad_waits[16] {};
uint32_t    g_nova_bad_wait_count = 0;
bool NovaIsBadWait(const void* addr) {
	for (uint32_t i = 0; i < g_nova_bad_wait_count; i++) {
		if (g_nova_bad_waits[i] == addr) {
			return true;
		}
	}
	return false;
}
''' + helper_anchor, 1)

old = '''			g_nova_watch_addr.store(a64, std::memory_order_relaxed);
		}

#endif
		SuspendPm4();
	}
}'''
if s.count(old) != 1:
    raise SystemExit('NOVA_0957: WaitRegMem tail anchor changed')
s = s.replace(old, '''			g_nova_watch_addr.store(a64, std::memory_order_relaxed);
		}
		if (NovaWaitGiveUp()) {
			const bool known_bad = NovaIsBadWait(addr);
			if (waited > (known_bad ? 100u : 2000u)) {
				static std::atomic<uint32_t> skip_count {0};
				if (skip_count.fetch_add(1) < 16) {
					std::fprintf(stderr, "NOVA_GPU_WAIT: gave up on 0x%016llx after %llu ms, continuing (0.9.10 behaviour)\\n",
					             static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(addr)),
					             static_cast<unsigned long long>(waited));
				}
				if (!known_bad && g_nova_bad_wait_count < 16) {
					g_nova_bad_waits[g_nova_bad_wait_count++] = addr;
				}
				m_nova_wait_addr = nullptr;
				g_nova_gpu_stall_since_ms.store(0, std::memory_order_relaxed);
				return;
			}
		}

#endif
		SuspendPm4();
	}
}''', 1)
for inc in ('#include <string_view>', '#include <cstdlib>'):
    if inc not in s:
        s = inc + '\n' + s
p.write_text(s)
print('NOVA_0957: WAIT_REG_MEM give-up restored (Dead Cells default; NOVA_GPU_WAIT_GIVEUP)')
