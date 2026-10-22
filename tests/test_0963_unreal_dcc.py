#!/usr/bin/env python3
"""0.9.63: Unreal colour-metadata fills absorbed on the CPU only when safe."""
from pathlib import Path
import sys

r = Path(sys.argv[1]) / 'src/graphics/host_gpu/renderer'
tc = (r / 'cache/textureCache.cpp').read_text()
rc = (r / 'renderCompute.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


ab = between(tc, 'bool TextureCache::NovaAbsorbColorMetaFill(', 'void TextureCache::MaterializeColorClear(')
assert ab.index('if (!known) return false;') < ab.index('IsRegionGpuModified(address, size)') < ab.index('WriteBacking(')
assert ab.index('m_buffer_cache.InvalidateMemory(') < ab.index('WriteBacking(')
assert 'address + size <= it->first + it->second' in ab          # wholly inside one known metadata range
assert "v == nullptr || v[0] != '0'" in ab                         # NOVA_DCC_FILL_ABSORB=0 restores 0.9.62
assert 'if (range.size != 0) m_nova_color_meta[range.address] = range.size;' in tc
ci = between(rc, 'if (!cache.ClearImageFromBuffer(command, descriptor.Base48(), size, packed_clear)) {', '\n\t}')
assert 'return cache.NovaAbsorbColorMetaFill(descriptor.Base48(), size, packed_clear);' in ci
print('NOVA_0963_DCC: PASS')
