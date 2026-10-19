#!/usr/bin/env python3
"""Remove eager Dead Cells EOP drains without restoring pre-completion CPU stores."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);renderer=root/'src/graphics/host_gpu/renderer'
p=renderer/'novaRenderCosts.h';s=p.read_text()
a='inline bool GpuLabelProfile() {'
assert s.count(a)==1
s=s.replace(a,'''inline bool DeadCellsProfile() {
    static const bool enabled = [] {
        const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
        return title && std::string_view(title) == "PPSA15552";
    }();
    return enabled;
}
inline bool LabelReadbackProfile() { return EverProfile() || DeadCellsProfile(); }
inline bool GpuLabelProfile() {''',1)
a='std::string_view(title) == "PPSA31162");';b='std::string_view(title) == "PPSA31162" ||\n                         std::string_view(title) == "PPSA15552");'
assert s.count(a)==1;s=s.replace(a,b);p.write_text(s)
p=renderer/'cache/bufferCache.cpp';s=p.read_text()
assert s.count('!NovaRender::EverProfile()')==2
s=s.replace('!NovaRender::EverProfile()', '!NovaRender::LabelReadbackProfile()')
a='\tm_eop_labels.Record(vaddr, data, size, m_scheduler.CurrentTick());'
assert s.count(a)==1
s=s.replace(a,a+'''
    if (NovaRender::DeadCellsProfile()) {
        static bool logged = false;
        if (!logged) {
            const auto* cap = std::getenv("NOVA_FPS_CAP");
            const auto* present = std::getenv("NOVA_PRESENT_MODE");
            std::fprintf(stderr, "NOVA_DEADCELLS: GPU-recorded completion labels; real timeline/readback; eager constant-label drains disabled; cap=%s present=%s\\n",
                         cap ? cap : "unset", present ? present : "default");
            logged = true;
        }
    }
''');p.write_text(s)
p=root/'src/graphics/guest_gpu/graphicsRun.cpp';s=p.read_text();a='if (NovaRender::EverProfile() && m_renderer.GetBufferCache().IsEopLabelPending('
assert s.count(a)==1;s=s.replace(a,'if (NovaRender::LabelReadbackProfile() && m_renderer.GetBufferCache().IsEopLabelPending(')
s=s.replace('// Ever Forward: yield only this PM4 queue while a known label is pending.', '// Yield only this PM4 queue while an enabled title has a known pending label.')
p.write_text(s)
print('Dead Cells: GPU label recording, coherent CPU fault publication and cooperative PM4 waits; timestamps/unsupported labels retain real drain')
