#!/usr/bin/env python3
"""Wire Android launch controls into existing renderer paths; preserve defaults."""
from pathlib import Path
import sys
root=Path(sys.argv[1]); changes={}
def edit(p,old,new):
 s=changes.get(p,(root/p).read_text())
 if s.count(old)!=1: raise SystemExit('graphics settings anchor changed: '+p)
 changes[p]=s.replace(old,new,1)
p='src/common/emulatorConfig.cpp'
edit(p,'#include <memory>','#include <memory>\n#include <cstdlib>\n#include <cstring>')
edit(p,'PresentMode GetPresentMode() {\n\treturn g_config->present_mode;','''PresentMode GetPresentMode() {
#if defined(__ANDROID__) && defined(__aarch64__)
    if (const char* mode = std::getenv("NOVA_PRESENT_MODE")) {
        if (std::strcmp(mode, "fifo") == 0) return PresentMode::Fifo;
        if (std::strcmp(mode, "mailbox") == 0) return PresentMode::Mailbox;
        if (std::strcmp(mode, "immediate") == 0) return PresentMode::Immediate;
    }
#endif
\treturn g_config->present_mode;''')
p='src/graphics/host_gpu/renderer/pipeline/novaShaderDisk.h'
edit(p,'#include <cstdio>','#include <cstdio>\n#include <cstdlib>')
edit(p,'    if (title.empty()) return {};','''    // Disabling cache never removes existing artifacts.
    const char* enabled = std::getenv("NOVA_SHADER_CACHE");
    if (title.empty() || (enabled && std::strcmp(enabled, "0") == 0)) return {};''')
p='src/graphics/presentation/window/vulkanWindow.cpp'
edit(p,'nova_gpl_properties.graphicsPipelineLibraryFastLinking;','''nova_gpl_properties.graphicsPipelineLibraryFastLinking;
    if (const char* enabled = std::getenv("NOVA_PIPELINE_LIBRARIES"); enabled && std::string_view(enabled) == "0")
        graphics.graphics_pipeline_library_enabled = false;''')
# string_view is already used in this translation unit; add its own include explicitly.
edit(p,'#include "common/emulatorConfig.h"','#include "common/emulatorConfig.h"\n#include <string_view>')
for p,s in changes.items(): (root/p).write_text(s)
print('Graphics settings: presentation, shader disk cache, capability-gated pipeline libraries')
