#!/usr/bin/env python3
"""Render resolution as an absolute height (fixes "1080p" meaning "native" on 4K-rendering games).

0.9.107's GPU draw timing shows Wonder Boy (PPSA27841) rendering every main pass at 3840x2160 even
with a 1080p console display reported; ~15-20 full-screen passes per frame at 1.3-3.3 ms each make
up the ~42 ms GPU frame. The app's "Render resolution" options were permille of a 1080p base
(1080p = 1000 = no scaling, 720p = 666), so on a 4K-rendering game "1080p" left it at 4K and
"720p" gave 2560x1440.

With NOVA_RESCALE_TARGET_HEIGHT=<h>, each eligible render target taller than h is allocated at
h/height of its guest size (e.g. 3840x2160 -> 1920x1080 for h=1080); targets at or below h stay
native. Everything else is the existing rescale path: per-binding guest/host sizes in shader
specialization, the same eligibility rules and the same per-pass ratio compatibility checks
with native fallbacks. NOVA_RESCALE_PERMILLE keeps working when no target height is set.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'src'
h = root / 'common/novaRescale.h'
s = h.read_text()
old = '''inline uint32_t Permille() {
    static const uint32_t value = ParsePermille(std::getenv("NOVA_RESCALE_PERMILLE"));
    return value;
}
inline bool Enabled() { return Permille() < 1000; }
'''
if s.count(old) != 1:
    raise SystemExit(f'0994: novaRescale.h Permille anchor changed ({s.count(old)}); no source written')
s = s.replace(old, '''inline uint32_t Permille() {
    static const uint32_t value = ParsePermille(std::getenv("NOVA_RESCALE_PERMILLE"));
    return value;
}
// Nova 0994: absolute target height (360..4320); 0 = use Permille().
inline uint32_t TargetHeight() {
    static const uint32_t value = [] {
        const char* text = std::getenv("NOVA_RESCALE_TARGET_HEIGHT");
        const long  h    = text ? std::strtol(text, nullptr, 10) : 0;
        return (h >= 360 && h <= 4320) ? uint32_t(h) : 0u;
    }();
    return value;
}
constexpr uint32_t PermilleForHeight(uint32_t guest_height, uint32_t target_height) {
    if (target_height == 0 || guest_height <= target_height) return 1000;
    const auto permille = uint32_t(uint64_t(target_height) * 1000 / guest_height);
    return permille < 250 ? 250 : permille;
}
// Scale for one image of the given guest height.
inline uint32_t PermilleFor(uint32_t guest_height) {
    return TargetHeight() != 0 ? PermilleForHeight(guest_height, TargetHeight()) : Permille();
}
inline bool Enabled() { return Permille() < 1000 || TargetHeight() != 0; }
''', 1)
old_note = 'reason,Permille());'
if s.count(old_note) != 1:
    raise SystemExit('0994: novaRescale.h Note anchor changed; no source written')
s = s.replace(old_note, 'reason,TargetHeight() != 0 ? TargetHeight() : Permille());', 1)
s = s.replace('"NOVA_RESCALE: scaled_images=%llu fallbacks=%llu reason=%s permille=%u\\n"',
              '"NOVA_RESCALE: scaled_images=%llu fallbacks=%llu reason=%s permille_or_target_height=%u\\n"', 1)
h.write_text(s)

t = root / 'graphics/host_gpu/renderer/cache/textureCache.cpp'
s = t.read_text()
old = '''			if (ni.type == Prospero::ImageType::kColor2D && NovaRescale::Eligible(candidate,NovaRescale::Permille()) &&
			    (features & required) == required) {
				nova_permille = NovaRescale::Permille();'''
if s.count(old) != 1:
    raise SystemExit(f'0994: textureCache.cpp rescale anchor changed ({s.count(old)}); no source written')
s = s.replace(old, '''			const uint32_t nova_wanted = NovaRescale::PermilleFor(ni.extent.height);
			if (ni.type == Prospero::ImageType::kColor2D && NovaRescale::Eligible(candidate,nova_wanted) &&
			    (features & required) == required) {
				nova_permille = nova_wanted;''', 1)
t.write_text(s)
print('0994: render resolution can target an absolute height (NOVA_RESCALE_TARGET_HEIGHT)')
