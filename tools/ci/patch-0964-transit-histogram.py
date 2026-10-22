#!/usr/bin/env python3
"""0.9.64 (diagnostic): what the image barriers that end GPU passes really are.

0.9.63's read-to-read skip elided 0 of ~5,000-11,000 barriers per 5 s, so the tracked
old/new access masks are not what was assumed. Every 5 s NOVA_TRANSITIONS prints the 8 most
common (old layout, old access, new layout, new access) pairs emitted by Image::GetBarriers
(whole-image branch), as raw Vulkan enum/flag values. Log only.
"""
from pathlib import Path
import sys

im = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer/image/image.cpp'
s = im.read_text()
old = '''		NovaCountImageBarrier(false);
'''
if s.count(old) != 1:
    raise SystemExit('NOVA_0964: anchor changed (needs patch-0963-cpu-thermal.py)')
s = s.replace(old, '''		NovaCountImageBarrier(false);
		{
			// Nova 0.9.64: histogram of emitted whole-image transitions.
			struct Key { uint32_t ol, nl; uint64_t oa, na; uint64_t n; };
			static std::mutex          mutex;
			static std::array<Key, 64> keys {};
			static auto                start = std::chrono::steady_clock::now();
			std::lock_guard lock(mutex);
			const Key k {uint32_t(state.layout), uint32_t(destination_layout), uint64_t(VkAccessFlags2(state.access_mask)),
			             uint64_t(VkAccessFlags2(destination_access)), 0};
			for (auto& e: keys) {
				if (e.n == 0) { e = k; e.n = 1; break; }
				if (e.ol == k.ol && e.nl == k.nl && e.oa == k.oa && e.na == k.na) { e.n++; break; }
			}
			if (std::chrono::steady_clock::now() - start >= std::chrono::seconds(5)) {
				std::sort(keys.begin(), keys.end(), [](const Key& a, const Key& b) { return a.n > b.n; });
				for (int i = 0; i < 8 && keys[i].n; i++)
					std::fprintf(stderr, "NOVA_TRANSITIONS: n=%llu layout %u->%u access 0x%llx->0x%llx\\n",
					             (unsigned long long)keys[i].n, keys[i].ol, keys[i].nl,
					             (unsigned long long)keys[i].oa, (unsigned long long)keys[i].na);
				keys  = {};
				start = std::chrono::steady_clock::now();
			}
		}
''')
for inc in ['#include <mutex>', '#include <array>', '#include <algorithm>']:
    if inc not in s:
        s = s.replace('#include', inc + '\n#include', 1)
im.write_text(s)
print('NOVA_0964: NOVA_TRANSITIONS histogram')
