#!/usr/bin/env python3
"""Compile and execute the patched production surface selection and display code."""
from pathlib import Path
import os, subprocess, sys, tempfile
root = Path(sys.argv[1])
execution = root / "core/libs/prx/libSceAgcDriver/Execution"
code = r'''
#include "prx/libSceAgcDriver/Execution/include/NovaSurfaceCompatibility.hpp"
#include "prx/libSceAgcDriver/Execution/include/DisplayFormat.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace AgcDriver;
template<class F> void rejects(F f) { bool caught=false; try {f();} catch(const std::runtime_error&) {caught=true;} assert(caught); }
int main() {
    const VkSurfaceFormatKHR bgra{VK_FORMAT_B8G8R8A8_UNORM,VK_COLOR_SPACE_SRGB_NONLINEAR_KHR};
    const VkSurfaceFormatKHR rgba{VK_FORMAT_R8G8B8A8_UNORM,VK_COLOR_SPACE_SRGB_NONLINEAR_KHR};
    const VkSurfaceFormatKHR hdr{VK_FORMAT_A2B10G10R10_UNORM_PACK32,VK_COLOR_SPACE_HDR10_ST2084_EXT};
    for (const auto& offered : std::vector<std::vector<VkSurfaceFormatKHR>>{{rgba},{bgra},{rgba,bgra},{hdr,rgba}}) {
        auto selected=SelectSdrSurfaceFormat(offered);
        bool found=false; for(auto x:offered) found|=x.format==selected.format && x.colorSpace==selected.colorSpace;
        assert(found);
        assert(DynamicRangeSurfaceFormat(offered,0,false).format==selected.format);
        assert(DynamicRangeSurfaceFormat(offered,0x8100070422000000ull,false).format==selected.format);
        assert(SelectSdrSurfaceFormat(offered).format==selected.format);
    }
    assert(SelectSdrSurfaceFormat(std::vector<VkSurfaceFormatKHR>{rgba,bgra}).format==bgra.format);
    assert(SelectSdrSurfaceFormat(std::vector<VkSurfaceFormatKHR>{{VK_FORMAT_UNDEFINED,VK_COLOR_SPACE_SRGB_NONLINEAR_KHR}}).format==bgra.format);
    rejects([]{SelectSdrSurfaceFormat({});});
    rejects([&]{SelectSdrSurfaceFormat(std::vector<VkSurfaceFormatKHR>{hdr});});
    rejects([]{SelectSdrSurfaceFormat(std::vector<VkSurfaceFormatKHR>{{VK_FORMAT_R8G8B8A8_UINT,VK_COLOR_SPACE_SRGB_NONLINEAR_KHR}});});
    assert(DynamicRangeSurfaceFormat(std::vector<VkSurfaceFormatKHR>{rgba,hdr},0x8100070422000000ull,true).format==hdr.format);
    for(unsigned mask=1;mask<16;++mask) { auto alpha=SelectSurfaceAlpha(mask); assert((mask&alpha)==alpha); }
    rejects([]{SelectSurfaceAlpha(0);});
    VkSurfaceCapabilitiesKHR caps{};
    caps.supportedTransforms=VK_SURFACE_TRANSFORM_ROTATE_90_BIT_KHR;
    caps.currentTransform=VK_SURFACE_TRANSFORM_ROTATE_90_BIT_KHR;
    assert(SelectSurfaceTransform(caps)==caps.currentTransform);
    caps.supportedTransforms=VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;
    assert(SelectSurfaceTransform(caps)==VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR);
    caps.supportedTransforms=VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR|VK_SURFACE_TRANSFORM_ROTATE_90_BIT_KHR;
    caps.currentTransform=VK_SURFACE_TRANSFORM_ROTATE_90_BIT_KHR;
    assert(SelectSurfaceTransform(caps)==VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR); // Android landscape: compositor rotates
    caps.supportedTransforms=0;
    rejects([&]{SelectSurfaceTransform(caps);});
    std::puts("NOVA_SURFACE_TEST: RGBA/BGRA, SDR/HDR transitions, undefined/invalid formats, alpha and transforms PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/"test.cpp"
    source.write_text(code)
    extra = ["-I"+os.environ["NOVA_VULKAN_INCLUDE"]] if os.environ.get("NOVA_VULKAN_INCLUDE") else []
    subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",*extra,
                    "-I"+str(root/"core/libs"),str(source),str(execution/"src/DisplayFormat.cpp"),
                    "-o",str(Path(tmp)/"test")],check=True)
    subprocess.run([str(Path(tmp)/"test")],check=True)
