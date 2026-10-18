#!/usr/bin/env python3
"""Apply guarded AnyPS5 Android Vulkan composite-alpha negotiation to staged source."""
from pathlib import Path
import sys

source = Path(sys.argv[1]).resolve()
p = source / "core/libs/prx/libSceAgcDriver/Execution/src/VulkanDevice.cpp"
s = p.read_text()
old_check = '        require((surface.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR) != 0, "opaque composition is unavailable");'
new_check = '''        // Android surfaces are not required to advertise opaque composition.
        VkCompositeAlphaFlagBitsKHR selectedCompositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
        bool compositeAlphaSupported = false;
        for (const auto candidate : {VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
                                     VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR,
                                     VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR,
                                     VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR}) {
            if ((surface.supportedCompositeAlpha & candidate) != 0) {
                selectedCompositeAlpha = candidate;
                compositeAlphaSupported = true;
                break;
            }
        }
        require(compositeAlphaSupported, "no supported Vulkan surface composite alpha mode");'''
old_assignment = '        swapchain.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;'
new_assignment = '        swapchain.compositeAlpha = selectedCompositeAlpha;'
for old in (old_check, old_assignment):
    if s.count(old) != 1:
        raise SystemExit(f"AnyPS5 0.9.41: expected exactly one anchor: {old}")
s = s.replace(old_check, new_check, 1).replace(old_assignment, new_assignment, 1)
p.write_text(s)
print("NOVA_ANYPS5: negotiated surface-supported Vulkan composite alpha")
