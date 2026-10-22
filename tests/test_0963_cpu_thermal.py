#!/usr/bin/env python3
"""0.9.63: event loop no longer spins; read-to-read image barriers skipped (whole-image state only)."""
from pathlib import Path
import sys

g = Path(sys.argv[1]) / 'src/graphics'
hi = (g / 'presentation/window/hostInput.cpp').read_text()
im = (g / 'host_gpu/renderer/image/image.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


w = between(hi, '#if defined(__ANDROID__)\n\t// Nova 0.9.63', '#else')
assert 'SDL_PollEvent(event)' in w and 'SDL_Delay(' in w and 'SDL_WaitEventTimeout' not in w
assert 'return ms < 1 ? 1 : (ms > 16 ? 16 : ms);' in hi
r = between(im, 'bool NovaReadToRead(', '\n}\n')
for needle in ['from.layout == layout', 'from.layout != vk::ImageLayout::eUndefined', '!(from.access_mask & kNovaWriteAccess)',
               '!(access & kNovaWriteAccess)', 'from.access_mask != vk::AccessFlags2 {}']:
    assert needle in r, needle
for bit in ['eColorAttachmentWrite', 'eDepthStencilAttachmentWrite', 'eShaderWrite', 'eTransferWrite', 'eMemoryWrite', 'eHostWrite']:
    assert bit in between(im, 'constexpr vk::AccessFlags2 kNovaWriteAccess', ';'), bit
whole = between(im, 'if (NovaReadToRead(state, destination_layout, destination_access)) {', 'return {};')
assert 'state.pl_stage |= destination_stage;' in whole and 'state.access_mask |= destination_access;' in whole
assert im.count('NovaReadToRead(') == 2   # definition + whole-image use only (per-subresource states are rewritten)
print('NOVA_0963: PASS')
