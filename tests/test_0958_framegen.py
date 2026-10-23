#!/usr/bin/env python3
"""0.9.58: structure of Lossless Scaling frame generation in the patched presenter."""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src/graphics/presentation/window'
hdr = (src / 'novaFramegen.h').read_text()
vw = (src / 'vulkanWindow.cpp').read_text()
sc = (src / 'swapchain.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


# Env switches and their safe defaults: off unless a multiplier AND the user's DLL path are set.
for needle in ['std::getenv("NOVA_FRAMEGEN")', 'std::getenv("NOVA_LSFG_DLL")', 'std::getenv("NOVA_FRAMEGEN_FLOW")',
               'std::getenv("NOVA_FRAMEGEN_PERF")', 'return Multiplier() > 1 && std::getenv("NOVA_LSFG_DLL") != nullptr;',
               'return !m_failed && Requested() && AhbEnabled() && DisplayTiming();', 'dlopen("libnovalsfg.so"',
               'dlsym(lib, "nova_lsfg_init")', 'dlsym(lib, "nova_lsfg_create")', 'dlsym(lib, "nova_lsfg_present")',
               'dlsym(lib, "nova_lsfg_destroy")', 'VK_FORMAT_R16G16B16A16_SFLOAT', 'AHARDWAREBUFFER_FORMAT_R16G16B16A16_FLOAT',
               'Multiplier() - 1']:
    assert needle in hdr, needle
# Every failure path turns frame generation off instead of crashing.
assert hdr.count('Disable(') >= 6
# Non-Android stub keeps the presenter compiling with frame generation inert.
stub = hdr[hdr.rindex('#else'):]
assert '[[nodiscard]] bool Active() const { return false; }' in stub and '[[nodiscard]] uint64_t NextSlotNs() { return 0; }' in stub
# Pacing: bounded interval, slots of interval/multiplier (total wait < one real frame).
assert 'std::clamp<int64_t>(ns, 4\'000\'000, 100\'000\'000)' in hdr and 'm_interval_ns / Multiplier()' in hdr
assert 'VK_IMAGE_USAGE_STORAGE_BIT' not in hdr

# Device extension only when requested, and AhbEnabled only when the driver has it.
dev = between(vw, 'if (NovaFramegen::Requested()) {', 'NovaFramegen::AhbEnabled() = true;')
assert 'HasExtension(available_extensions, "VK_ANDROID_external_memory_android_hardware_buffer")' in dev
assert '#include "graphics/presentation/window/novaFramegen.h"' in vw

# Swapchain: room for multiplier+1 images, before the maxImageCount clamp.
img = between(sc, 'uint32_t image_count = surface.capabilities.minImageCount + 1;', 'if (surface.capabilities.maxImageCount != 0) {')
assert 'NovaFramegen::Multiplier()) + 1u' in img
gen = between(sc, 'Swapchain::Status Swapchain::NovaPresentGenerated(', '\nPresenter::Presenter(')
assert gen.index('AcquireNextImage(scheduler)') < gen.index('Common::LockGuard lock(render_mutex)') < gen.index('RecordOutput(') \
    < gen.index('Submit(scheduler)') < gen.index('status        = Present();')
assert gen.count('m_image_index = real_index;') == 2   # restored on both the failure and success paths
assert 'NovaFramegen::State   framegen;' in sc

# Present order: input copy recorded before the normal present commands, the copy waited on before
# generation, generated frames shown before the real frame, and the whole path gated on Active().
pres = between(sc, 'bool     nova_fg_input = false;', 'status = swapchain.Present();')
assert 'framegen.Active()' in pres and '!source->blank' in pres
order = ['source->Transit(', 'framegen.RecordInput(', 'swapchain.RecordPresentCommands(', 'swapchain.Submit(present_scheduler)',
         'present_scheduler.Wait(nova_fg_tick)', 'framegen.CountReal()', 'framegen.Generate()',
         'if (i != 0) swapchain.NovaSetPresentTime(framegen.NextSlotNs());', 'swapchain.NovaPresentGenerated(',
         'if (!generated.empty()) swapchain.NovaSetPresentTime(framegen.NextSlotNs());']
assert 'sleep_until' not in hdr   # 0.9.60: the flip thread never sleeps for pacing
pr = between(sc, 'Swapchain::Status Swapchain::Present() {', 'presentKHR(&present)')
assert 'VK_STRUCTURE_TYPE_PRESENT_TIMES_INFO_GOOGLE' in pr and 'm_nova_present_time_ns = 0;' in pr
assert 'NovaFramegen::DisplayTiming() = true;' in vw
pos = [pres.index(n) for n in order]
assert pos == sorted(pos), list(zip(order, pos))
assert 'if (nova_fg_input) {' in pres
print('NOVA_0958_FRAMEGEN: PASS')

