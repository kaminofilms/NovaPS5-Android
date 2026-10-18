#!/usr/bin/env python3
"""Guarded Android swapchain composite-alpha negotiation for staged Kyty source."""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / "src/graphics/presentation/window/swapchain.cpp"
source = p.read_text()
old = """\tconst auto composite =
\t    surface.capabilities.supportedCompositeAlpha & vk::CompositeAlphaFlagBitsKHR::eOpaque
\t        ? vk::CompositeAlphaFlagBitsKHR::eOpaque
\t        : vk::CompositeAlphaFlagBitsKHR::eInherit;"""
new = """\t// Choose only a composite-alpha mode advertised by this Android surface.
\tconst auto supported_alpha = surface.capabilities.supportedCompositeAlpha;
\tvk::CompositeAlphaFlagBitsKHR composite = vk::CompositeAlphaFlagBitsKHR::eOpaque;
\tbool alpha_found = false;
\tfor (const auto candidate: {vk::CompositeAlphaFlagBitsKHR::eOpaque,
\t                            vk::CompositeAlphaFlagBitsKHR::ePreMultiplied,
\t                            vk::CompositeAlphaFlagBitsKHR::ePostMultiplied,
\t                            vk::CompositeAlphaFlagBitsKHR::eInherit}) {
\t\tif (static_cast<bool>(supported_alpha & candidate)) {
\t\t\tcomposite = candidate;
\t\t\talpha_found = true;
\t\t\tbreak;
\t\t}
\t}
\tif (!alpha_found) {
\t\tEXIT("Vulkan presentation: no supported composite alpha mode\\n");
\t}
\tLOGF("NOVA_PRESENT: selected composite alpha=0x%x supported=0x%x\\n",
\t     static_cast<uint32_t>(composite), static_cast<uint32_t>(supported_alpha));"""
if source.count(old) != 1:
    raise SystemExit("NOVA_PRESENT: source anchor mismatch; refusing patch")
p.write_text(source.replace(old, new, 1))
print("NOVA_PRESENT: guarded composite-alpha selection installed")
