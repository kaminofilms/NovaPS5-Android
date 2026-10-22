#!/usr/bin/env python3
"""0.9.62: structure of GPU turbo and 2x2 variable-rate shading."""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src'
na = (src / 'novaAndroid.cpp').read_text()
vw = (src / 'graphics/presentation/window/vulkanWindow.cpp').read_text()
sh = (src / 'graphics/host_gpu/renderer/pipeline/shaders.cpp').read_text()
rd = (src / 'graphics/host_gpu/renderer/renderDraw.cpp').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


# Turbo: same ioctl as adrenotools_set_turbo, cleared when not wanted, re-asserted only when it worked.
assert 'constexpr unsigned int kNovaKgslPropPwrctrl = 0xE;' in na and '_IOW(0x09, 0x32, NovaKgslProperty)' in na
t = between(na, 'void NovaStartGpuTurbo() {', '} // namespace')
assert t.index('NovaSetGpuTurbo(wanted)') < t.index('if (!wanted || result != 0) return;') < t.index('std::thread(')
assert 'NovaStartGpuTurbo();\n\tif (g_gipa != nullptr)' in na
# VRS: only with the feature and a 1-sample 2x2 rate; dynamic state; per draw; never display/MSAA/small/depth-only.
assert 'graphics.nova_vrs_enabled = nova_vrs.pipelineFragmentShadingRate && two_by_two;' in vw
assert 'nova_vrs_enable.pipelineFragmentShadingRate = VK_TRUE;' in vw
assert 'dynamic_states.push_back(vk::DynamicState::eFragmentShadingRateKHR);' in sh
v = between(rd, 'if (m_context.GetGraphics().nova_vrs_enabled) {', 'NOVA_VRS_REPORT')
for needle in ['rendering.num_color_attachments != 0', 'rendering.width * rendering.height >= 1280u * 720u',
               'image->usage.video_out', 'image->backing.samples != 1', 'depth->backing.samples != 1',
               'vkCmdSetFragmentShadingRateKHR']:
    assert needle in v, needle
assert rd.index('dynamic_state.Commit(m_context.GetGraphics(), vk_buffer);') < rd.index('if (m_context.GetGraphics().nova_vrs_enabled) {')
gr = (src / 'graphics/guest_gpu/graphicsRun.cpp').read_text()
assert gr.count('NovaRestampAtCompletion(GetScheduler(),') == 2          # fast EOP labels + COPY_DATA clock
assert 'scheduler.DeferPriorityOperation([dst, size] {' in gr          # rewritten only after the GPU finished
fast = between(gr, 'if (timestamp) data = static_cast<decltype(data)>(Sync::ReadReferenceClock());\n\t\t\tGuestMemory::Copy', 'NovaNoteGpuWrite')
assert fast.index('GuestMemory::Copy') < fast.index('NovaRestampAtCompletion')   # packet-time value written first
print('NOVA_0962_GPU_BOOST: PASS')
