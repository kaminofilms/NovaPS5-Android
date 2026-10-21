#!/usr/bin/env python3
"""0.9.58: show guest puts() text in the log.

0.9.57 exit reports (Super Meat Boy 3D and Luna Abyss): right before exit(0)
both games' libc call puts() with a 27-character message, then
sceKernelDebugRaiseExceptionOnReleaseMode(0xa0020005), then exit. The message
never reached the exported log, so echo every puts() line to stderr.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/libs/libC.cpp'
s = p.read_text()
old = '''static KYTY_SYSV_ABI int puts(const char* s) {
	PRINT_NAME();
'''
if s.count(old) != 1:
    raise SystemExit('NOVA_0958_PUTS: anchor changed')
s = s.replace(old, old + '''	{
		uint64_t readable = 0;
		if (s != nullptr && Graphics::HostMemoryQueryReadable(reinterpret_cast<uint64_t>(s), 1024, readable) && readable != 0) {
			const auto* end = static_cast<const char*>(std::memchr(s, 0, static_cast<size_t>(readable)));
			std::fprintf(stderr, "NOVA_GUEST_PUTS: %.*s\\n", static_cast<int>(end ? end - s : static_cast<int>(readable)), s);
			std::fflush(stderr);
		}
	}
''')
p.write_text(s)
print('NOVA_0958_PUTS: guest puts() echoed to stderr')
