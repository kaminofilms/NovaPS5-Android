#!/usr/bin/env python3
"""0.9.52: GPU-recorded completion labels for every title (opt-out per game).

Device evidence (Wonder Boy Asha PPSA27841, 0.9.51, NX809J/Turnip A8xx): the GPU
worker spends ~3.6-4.6 s of every 5 s window in `eop_drain` (2,000-4,700 calls),
i.e. a full CPU<->GPU `Finish()` per RELEASE_MEM label. Heartbeat is 9.9-16 FPS
while draw+shader+submit cost is only ~0.7-1.4 s per window.

Dead Cells (0.9.50) and Ever Forward already replace that drain with the
validated path: the constant label is recorded as a real GPU transfer with
barriers, IRQs are deferred to the actual timeline, CPU faults / PM4 reads
reconcile the producer's real tick, and pending labels suspend only their PM4
queue. This overlay enables the same path for all titles. Nothing new is
fabricated: timestamps, GDS, texture-backed and unaligned labels keep the drain.

NOVA_GPU_LABELS=0 (Graphics dialog switch) restores the previous per-title
behaviour; titles that were already enabled stay enabled.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])
renderer = root / 'src/graphics/host_gpu/renderer'
changes = {}


def edit(path, old, new):
    s = changes.get(path, path.read_text())
    if s.count(old) != 1:
        raise SystemExit(f'NOVA_GPU_LABELS: anchor changed {path}: {old[:90]!r}')
    changes[path] = s.replace(old, new, 1)


cost = renderer / 'novaRenderCosts.h'
edit(cost, 'inline bool DeadCellsProfile() {', '''inline bool GenericGpuLabels() {
    // Default on. Only an explicit "0" restores the old per-title drain policy.
    static const bool enabled = [] {
        const char* value = std::getenv("NOVA_GPU_LABELS");
        return !(value && std::string_view(value) == "0");
    }();
    return enabled;
}
inline bool DeadCellsProfile() {''')
edit(cost, 'inline bool LabelReadbackProfile() { return EverProfile() || DeadCellsProfile(); }',
     'inline bool LabelReadbackProfile() { return EverProfile() || DeadCellsProfile() || GenericGpuLabels(); }')
edit(cost, '''        return title && (std::string_view(title) == "PPSA04703" ||
                         std::string_view(title) == "PPSA31162" ||
                         std::string_view(title) == "PPSA15552");''',
     '''        return GenericGpuLabels() ||
               (title && (std::string_view(title) == "PPSA04703" ||
                          std::string_view(title) == "PPSA31162" ||
                          std::string_view(title) == "PPSA15552"));''')

cache = renderer / 'cache/bufferCache.cpp'
edit(cache, '    if (NovaRender::DeadCellsProfile()) {\n        static bool logged = false;',
     '''    if (!NovaRender::DeadCellsProfile() && !NovaRender::EverProfile()) {
        static bool generic_logged = false;
        if (!generic_logged) {
            const auto* title = std::getenv("NOVA_CACHE_TITLE_ID");
            std::fprintf(stderr, "NOVA_GPU_LABELS: GPU-recorded completion labels for %s; real timeline/readback; constant-label drains disabled (NOVA_GPU_LABELS=0 restores)\\n",
                         title ? title : "unknown");
            generic_logged = true;
        }
    }
    if (NovaRender::DeadCellsProfile()) {
        static bool logged = false;''')

for path, s in changes.items():
    path.write_text(s)
print('NOVA_GPU_LABELS: GPU completion labels + coherent readback + cooperative PM4 waits for all titles; opt-out NOVA_GPU_LABELS=0')
