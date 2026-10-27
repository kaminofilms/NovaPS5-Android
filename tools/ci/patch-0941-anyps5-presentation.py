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
# Staged AnyPS5 sources may already be patched by a previous build attempt.
# Re-running must not fail or partially rewrite a valid patched checkout.
if new_check in s and new_assignment in s and old_check not in s and old_assignment not in s:
    print("NOVA_ANYPS5: composite-alpha fix already applied")
    pass
elif s.count(old_check) != 1 or s.count(old_assignment) != 1:
    raise SystemExit(
        "AnyPS5 0.9.41: source is neither the pinned original nor fully patched; "
        "inspect VulkanDevice.cpp before continuing"
    )
s = s.replace(old_check, new_check, 1).replace(old_assignment, new_assignment, 1)
p.write_text(s)
print("NOVA_ANYPS5: negotiated surface-supported Vulkan composite alpha")

# 0.9.42: negotiate SDR formats and surface capabilities at startup AND resize.
def replace_once(text, old, new):
    if text.count(old) == 1:
        return text.replace(old, new, 1)
    if old not in text and text.count(new) == 1:
        return text
    raise SystemExit("NOVA_SURFACE: unexpected or partial source anchor: " + old[:100])

helper = "#pragma once\n#include <vulkan/vulkan.h>\n#include <array>\n#include <span>\n#include <stdexcept>\n\nnamespace AgcDriver {\ninline VkSurfaceFormatKHR SelectSdrSurfaceFormat(std::span<const VkSurfaceFormatKHR> formats) {\n    constexpr std::array<VkFormat, 2> preferred{VK_FORMAT_B8G8R8A8_UNORM, VK_FORMAT_R8G8B8A8_UNORM};\n    for (const auto wanted : preferred)\n        for (const auto& offered : formats)\n            if (offered.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR &&\n                (offered.format == wanted || (formats.size() == 1 && offered.format == VK_FORMAT_UNDEFINED)))\n                return {wanted, offered.colorSpace};\n    throw std::runtime_error(\"Vulkan presentation: no supported SDR RGBA8/BGRA8 UNORM surface format\");\n}\ninline VkCompositeAlphaFlagBitsKHR SelectSurfaceAlpha(VkCompositeAlphaFlagsKHR supported) {\n    for (const auto mode : {VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR,\n                           VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR, VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR})\n        if ((supported & mode) != 0) return mode;\n    throw std::runtime_error(\"Vulkan presentation: no supported surface composite alpha mode\");\n}\n// AnyPS5 renders and presents unrotated images. A rotated preTransform (Android reports\n// ROTATE_90 for a landscape window on a portrait panel) would require pre-rotated content and\n// otherwise shows the game sideways. Identity lets the compositor rotate it.\ninline VkSurfaceTransformFlagBitsKHR SelectSurfaceTransform(const VkSurfaceCapabilitiesKHR& surface) {\n    if ((surface.supportedTransforms & VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR) != 0)\n        return VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;\n    if ((surface.supportedTransforms & surface.currentTransform) != 0) return surface.currentTransform;\n    throw std::runtime_error(\"Vulkan presentation: no supported current or identity surface transform\");\n}\n}\n"
(p.parent.parent / "include/NovaSurfaceCompatibility.hpp").write_text(helper)
include = '#include "prx/libSceAgcDriver/Execution/include/NovaSurfaceCompatibility.hpp"'
if include not in s:
    s = include + '\n' + s
s = replace_once(s,
    '        require((surface.supportedTransforms & VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR) != 0, "identity surface transform is unavailable");',
    '        const auto selectedSurfaceTransform = SelectSurfaceTransform(surface);')
s = replace_once(s,
    '        require(std::any_of(state->surfaceFormats.begin(), state->surfaceFormats.end(), [](const auto& format) { return format.format == VK_FORMAT_B8G8R8A8_UNORM && format.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR; }), "BGRA8 sRGB-nonlinear surface format is unavailable");',
    '        const auto selectedSdr = SelectSdrSurfaceFormat(state->surfaceFormats);\n        state->surfaceFormat = selectedSdr.format;\n        state->surfaceColorSpace = selectedSdr.colorSpace;\n        std::fprintf(stderr, "NOVA_SURFACE: selected startup format=%d colorSpace=%d alpha=0x%x transform=0x%x\\n", static_cast<int>(selectedSdr.format), static_cast<int>(selectedSdr.colorSpace), static_cast<unsigned>(selectedCompositeAlpha), static_cast<unsigned>(selectedSurfaceTransform));')
s = replace_once(s, '        swapchain.preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;', '        swapchain.preTransform = selectedSurfaceTransform;')
s = replace_once(s,
    'if (!offered || !AgcDriver::CurrentHostHdr().available) useSurfaceFormat({VK_FORMAT_B8G8R8A8_UNORM, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR});',
    'if (!offered || !AgcDriver::CurrentHostHdr().available) useSurfaceFormat(SelectSdrSurfaceFormat(state->surfaceFormats));')
s = replace_once(s,
    '    require((surface.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT) != 0 && (surface.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR) != 0 && (surface.supportedTransforms & VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR) != 0, "resized surface capabilities are unsupported");',
    '    require((surface.supportedUsageFlags & (VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT)) == (VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT), "resized surface usage is unsupported");\n    if (state->surfaceColorSpace != VK_COLOR_SPACE_HDR10_ST2084_EXT) {\n        const auto selected = SelectSdrSurfaceFormat(state->surfaceFormats);\n        if (selected.format != state->surfaceFormat || selected.colorSpace != state->surfaceColorSpace) useSurfaceFormat(selected);\n    }')
s = replace_once(s, '    create.preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;', '    create.preTransform = SelectSurfaceTransform(surface);')
s = replace_once(s, '    create.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;', '    create.compositeAlpha = SelectSurfaceAlpha(surface.supportedCompositeAlpha);')
s = replace_once(s,
    '    formats.resize(count);\n    constexpr VkFormatFeatureFlags target = VK_FORMAT_FEATURE_BLIT_DST_BIT | VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT;',
    '    formats.resize(count);\n    for (const auto& offered : formats) std::fprintf(stderr, "NOVA_SURFACE: offered format=%d colorSpace=%d\\n", static_cast<int>(offered.format), static_cast<int>(offered.colorSpace));\n    if (formats.size() == 1 && formats.front().format == VK_FORMAT_UNDEFINED && formats.front().colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) formats = {{VK_FORMAT_B8G8R8A8_UNORM, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR}, {VK_FORMAT_R8G8B8A8_UNORM, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR}};\n    constexpr VkFormatFeatureFlags target = VK_FORMAT_FEATURE_BLIT_DST_BIT | VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT;')
s = replace_once(s,
    '        if (format.colorSpace != VK_COLOR_SPACE_HDR10_ST2084_EXT) return false;',
    '        if (format.colorSpace != VK_COLOR_SPACE_HDR10_ST2084_EXT && format.colorSpace != VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) return false;')
display = p.parent / "DisplayFormat.cpp"
d = display.read_text()
if include not in d:
    d = include + '\n' + d
d = replace_once(d,
    'if (!DisplayPq(pixelFormat) || !hdrAvailable) return {VK_FORMAT_B8G8R8A8_UNORM, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR};',
    'if (!DisplayPq(pixelFormat) || !hdrAvailable) return SelectSdrSurfaceFormat(formats);')
display.write_text(d)
p.write_text(s)
print("NOVA_SURFACE: supported SDR formats, alpha and transforms negotiated across startup, dynamic range and resize")
