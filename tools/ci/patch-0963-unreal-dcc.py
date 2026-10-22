#!/usr/bin/env python3
"""0.9.63: Unreal colour-metadata (DCC/CMask) fast-clear fills without GPU readbacks.

Super Meat Boy 3D (PPSA31162) on 0.9.62 ran at 1-2 FPS: the GPU thread spent ~3.8 s of every 5 s
in readbacks, ~280 of them from TextureCache::MaterializeColorClear (readback_caller=
TextureMetadata, 35-45 MB per 5 s, up to 426 ms each). Unreal clears DCC/CMask metadata with a
compute shader that stores one constant into every dword (SharpEmu, ConstantFillDetector.cs:
"Unreal clears DCC metadata this way, so the dispatch must reach the image cache as a clear").
Kyty already recognises that shader (uniform_fill, ResolveComputeBufferFill) but only consumed it
for depth metadata and whole-image clears, so the fill ran on the GPU, marked the metadata
GPU-written, and the next bind of the colour image waited for the GPU to read it back.

Now a fill whose destination lies inside a colour metadata range the texture cache has seen is
written to guest memory by the CPU and the dispatch is skipped; MaterializeColorClear then reads
the code from memory. Only when the range has no pending GPU writes (otherwise a GPU write could
land after the CPU store), and never for plain buffer memory. NOVA_DCC_FILL_ABSORB=0 restores 0.9.62.
NOVA_DCC_FILL: absorbed / ran-on-GPU counts every 5 s.
"""
from pathlib import Path
import sys

r = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0963_DCC: anchor changed {path.name}: {old[:80]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


th = r / 'cache/textureCache.h'
edit(th, '	[[nodiscard]] bool ClearMeta(uint64_t address);\n', '''	[[nodiscard]] bool ClearMeta(uint64_t address);
	// Nova 0.9.63: write an Unreal colour-metadata constant fill on the CPU (no GPU readback later).
	[[nodiscard]] bool NovaAbsorbColorMetaFill(uint64_t address, uint64_t size, uint32_t value);
''')
s = changes[th]
i = s.index('	BufferCache&                                      m_buffer_cache;')
s = s[:i] + '	std::map<uint64_t, uint64_t> m_nova_color_meta; // 0.9.63: colour metadata ranges (address -> size)\n' + s[i:]
if '#include <map>' not in s:
    s = s.replace('#include', '#include <map>\n#include', 1)
changes[th] = s

tc = r / 'cache/textureCache.cpp'
edit(tc, '''		auto& image         = m_slot_images[id];
		image.info.metadata = desc.info.metadata;
		// Native color metadata must not retain a reused HTile/CMask/FMask clear flag.
		m_surface_metas.erase(range.address);''', '''		auto& image         = m_slot_images[id];
		image.info.metadata = desc.info.metadata;
		// Native color metadata must not retain a reused HTile/CMask/FMask clear flag.
		m_surface_metas.erase(range.address);
		if (range.size != 0) m_nova_color_meta[range.address] = range.size;''')
edit(tc, 'void TextureCache::MaterializeColorClear(ImageId id, const ImageDesc& desc,', '''bool TextureCache::NovaAbsorbColorMetaFill(uint64_t address, uint64_t size, uint32_t value) {
	static const bool enabled = [] {
		const char* v = std::getenv("NOVA_DCC_FILL_ABSORB");
		return v == nullptr || v[0] != '0';
	}();
	static std::atomic<uint64_t> absorbed {0}, refused {0};
	static std::atomic<int64_t>  window {0};
	auto report = [&](bool ok) {
		(ok ? absorbed : refused).fetch_add(1, std::memory_order_relaxed);
		const int64_t now = std::chrono::duration_cast<std::chrono::seconds>(
		                        std::chrono::steady_clock::now().time_since_epoch()).count();
		int64_t first = window.load(std::memory_order_relaxed);
		if (first == 0) { window.store(now); return; }
		if (now - first >= 5 && window.compare_exchange_strong(first, now)) {
			std::fprintf(stderr, "NOVA_DCC_FILL: absorbed=%llu ran_on_gpu=%llu\\n",
			             (unsigned long long)absorbed.exchange(0), (unsigned long long)refused.exchange(0));
		}
	};
	if (!enabled || size == 0 || (size & 3u) != 0 || (address & 3u) != 0 || size > (64ull << 20)) return false;
	bool known = false;
	{
		std::scoped_lock lock {m_lock};
		auto it = m_nova_color_meta.upper_bound(address);
		if (it != m_nova_color_meta.begin()) {
			--it;
			known = address >= it->first && address + size <= it->first + it->second;
		}
	}
	if (!known) return false; // plain buffer memory: run the guest dispatch
	if (m_buffer_cache.IsRegionGpuModified(address, size)) {
		report(false); // pending GPU writes could land after a CPU store
		return false;
	}
	std::vector<uint32_t> words(size / sizeof(uint32_t), value);
	m_buffer_cache.InvalidateMemory(address, size, {BufferCache::ReadbackCaller::InvalidateMemory, 0, 0, false});
	LibKernel::Memory::WriteBacking(address, words.data(), size);
	report(true);
	return true;
}

void TextureCache::MaterializeColorClear(ImageId id, const ImageDesc& desc,''')
s = changes[tc]
for inc in ['#include <atomic>', '#include <chrono>', '#include <cstdio>', '#include <cstdlib>', '#include <vector>']:
    if inc not in s:
        s = s.replace('#include', inc + '\n#include', 1)
changes[tc] = s

rc = r / 'renderCompute.cpp'
edit(rc, '''	if (!cache.ClearImageFromBuffer(command, descriptor.Base48(), size, packed_clear)) {
		return false;
	}''', '''	if (!cache.ClearImageFromBuffer(command, descriptor.Base48(), size, packed_clear)) {
		// Nova 0.9.63: Unreal's DCC/CMask fast-clear fill -> CPU store, no GPU readback later.
		return cache.NovaAbsorbColorMetaFill(descriptor.Base48(), size, packed_clear);
	}''')

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0963_DCC: colour-metadata constant fills written on the CPU (NOVA_DCC_FILL_ABSORB=0 restores)')
