#!/usr/bin/env python3
"""0.9.53 native-speed synchronization (defaults for every title, per-game opt-out).

Research: docs/RESEARCH-NATIVE-SPEED-20261020.md. Every reference emulator lets
the guest CPU observe completion labels without blocking:
  * KytyPS5 upstream (HEAD 7b7f9a7 and Nova's pin) stores EOP labels when the
    packet is processed; the IRQ is deferred to real GPU completion.
  * shadPS4 (main c1b2655) does the same; readbacks_mode defaults to Disabled.
  * Bloodborne-Android (FEX + shadPS4 renderer on Turnip) stores early by
    default, BB_READBACKS defaults to Relaxed, and unprotects a 64 KiB window
    around write faults (+22% FPS, docs/parallel_gpu.md).

1. NOVA_LABEL_MODE=fast (default): constant and timestamp EOP labels are stored
   into guest memory when RELEASE_MEM is processed (Kyty/shadPS4 behaviour).
   IRQs still run from the real GPU timeline. "accurate" keeps the 0.9.52 paths
   (GPU labels, cooperative/ordered waits, completion publication).
2. NOVA_READBACK_MODE=relaxed (default): GPU-written pages are no longer
   read-protected, so guest CPU reads never wait for a download (shadPS4/BB
   Relaxed). GPU-written pages stay write-protected: a CPU write still downloads
   the GPU data first. PM4 WAIT_REG_MEM keeps coherent reads through the buffer
   cache. "precise" restores the old model. Accurate labels force precise.
3. NOVA_FAULT_WINDOW_KB=64 (default; 0 disables): after a CPU write fault on a
   tracked page, release the CPU-clean, GPU-clean pages of the aligned window so
   sequential writers fault once per window. GPU-dirty pages are never touched.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])
renderer = root / 'src/graphics/host_gpu/renderer'
host = root / 'src/graphics/host_gpu'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_SYNC: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


# --- shared mode switches -------------------------------------------------------
modes = '''namespace NovaSync {
// Default "fast": labels are stored when their packet is processed (KytyPS5/shadPS4).
inline bool FastLabels() {
    static const bool fast = [] {
        const char* value = std::getenv("NOVA_LABEL_MODE");
        return !(value && std::string_view(value) == "accurate");
    }();
    return fast;
}
// Default "relaxed": GPU-written pages are not read-protected. Accurate labels
// publish through read faults and therefore always use precise readbacks.
inline bool PreciseReadbacks() {
    static const bool precise = [] {
        const char* value = std::getenv("NOVA_READBACK_MODE");
        return !FastLabels() || (value && std::string_view(value) == "precise");
    }();
    return precise;
}
inline uint64_t FaultWindowBytes() {
    static const uint64_t bytes = [] {
        const char* value = std::getenv("NOVA_FAULT_WINDOW_KB");
        const long kb = value ? std::strtol(value, nullptr, 10) : 64;
        if (kb != 0 && kb != 16 && kb != 32 && kb != 64 && kb != 128 && kb != 256) return uint64_t {64 * 1024};
        return uint64_t(kb) * 1024u;
    }();
    return bytes;
}
} // namespace NovaSync
'''
sync_header = host / 'novaSync.h'
if sync_header.exists():
    raise SystemExit('NOVA_SYNC: novaSync.h already exists; refusing to overwrite')
changes[sync_header] = '#pragma once\n#include <cstdint>\n#include <cstdlib>\n#include <string_view>\n\n' + modes

cost = renderer / 'novaRenderCosts.h'
edit(cost, '#include "novaReadbackTelemetry.h"', '#include "novaReadbackTelemetry.h"\n#include "graphics/host_gpu/novaSync.h"')
edit(cost, 'inline bool LabelReadbackProfile() { return EverProfile() || DeadCellsProfile() || GenericGpuLabels(); }',
     'inline bool LabelReadbackProfile() { return !NovaSync::FastLabels() && (EverProfile() || DeadCellsProfile() || GenericGpuLabels()); }')
edit(cost, '        return GenericGpuLabels() ||\n               (title && (',
     '        return !NovaSync::FastLabels() && (GenericGpuLabels() ||\n               (title && (')
edit(cost, '''                          std::string_view(title) == "PPSA15552"));
    }();''', '''                          std::string_view(title) == "PPSA15552")));
    }();''')
edit(cost, 'EopLabelOrdered, Count };', 'EopLabelOrdered, EopFast, Count };')
edit(cost, '"eop_label_ordered"', '"eop_label_ordered", "eop_fast"')

# --- 1. fast labels -------------------------------------------------------------
gr = root / 'src/graphics/guest_gpu/graphicsRun.cpp'
edit(gr, '''	auto complete_write = [&](auto data, bool timestamp) {
		if (NovaRender::GpuLabelProfile() && !timestamp &&''', '''	auto complete_write = [&](auto data, bool timestamp) {
		if (NovaSync::FastLabels()) {
			// KytyPS5/shadPS4 behaviour: the label is visible when its packet is
			// processed; only the IRQ waits for the real GPU timeline.
			NovaRender::Scope nova_fast_cost(NovaRender::Cost::EopFast);
			EXIT_IF(dst_gpu_addr == nullptr);
			static bool nova_sync_logged = false;
			if (!nova_sync_logged) {
				nova_sync_logged = true;
				std::fprintf(stderr, "NOVA_SYNC: labels=fast readback=%s fault_window=%lluKB (Graphics > GPU sync = Accurate restores completion-ordered labels)\\n",
				             NovaSync::PreciseReadbacks() ? "precise" : "relaxed",
				             static_cast<unsigned long long>(NovaSync::FaultWindowBytes() / 1024u));
			}
			(void)command.Handle();
			if (timestamp) data = static_cast<decltype(data)>(Sync::ReadReferenceClock());
			GuestMemory::Copy(dst_gpu_addr, &data, sizeof(data));
#if defined(KYTY_NOVA_FEX)
			NovaNoteGpuWrite(dst_gpu_addr, static_cast<uint64_t>(data),
			                 static_cast<uint32_t>(m_interrupt_event_id), 'E');
#endif
			if (with_interrupt) {
				GetScheduler().DeferPriorityOperation(
				    [&renderer = m_renderer, event_id = m_interrupt_event_id, interrupt_context_id] {
					    renderer.TriggerInterrupt(event_id, interrupt_context_id);
				    });
			}
			return;
		}
		if (NovaRender::GpuLabelProfile() && !timestamp &&''')

# PM4 waits keep coherent reads of GPU-written memory when reads are relaxed.
edit(gr, '''	if (NovaRender::GpuLabelProfile()) {
		EXIT_IF(!LibKernel::Memory::TryReadBufferBacking(''', '''	if (NovaRender::GpuLabelProfile() || !NovaSync::PreciseReadbacks()) {
		EXIT_IF(!LibKernel::Memory::TryReadBufferBacking(''')

# --- 2. relaxed readbacks -------------------------------------------------------
rm = host / 'regionManager.h'
edit(rm, '''	template <bool track, bool is_read>
	void UpdateProtection() {
''', '''	template <bool track, bool is_read>
	void UpdateProtection() {
		// Relaxed readbacks: GPU-written pages stay readable (stale CPU copy), as in
		// shadPS4/Bloodborne-Android. Write protection is unchanged.
		if constexpr (is_read) {
			if (!NovaSync::PreciseReadbacks()) return;
		}
''')
rs = changes.get(rm, rm.read_text())
first_include = rs.index('#include')
changes[rm] = rs[:first_include] + '#include "graphics/host_gpu/novaSync.h"\n' + rs[first_include:]

# --- 3. write-fault window ------------------------------------------------------
mt = host / 'memoryTracker.h'
edit(mt, '''#if KYTY_BUILD == KYTY_BUILD_DEBUG
	void ValidateGpuDirtyPages(''', '''	// Nova 0.9.53: after a write fault, release the CPU-clean, GPU-clean pages of
	// the aligned window so sequential writers fault once per window (Bloodborne-
	// Android +22%). GPU-dirty pages keep their protection and ownership.
	void InvalidateCleanWindow(uint64_t vaddr, uint64_t window) noexcept {
		if (window < TRACKER_PAGE_SIZE || (window & (window - 1)) != 0) return;
		CheckNotInUploadCallback();
		const uint64_t begin = vaddr & ~(window - 1);
		if (begin + window < begin) return;
		Iterate<false>(begin, window, [&](RegionManager* manager, uint64_t offset, uint64_t bytes) {
			std::scoped_lock lock(manager->lock);
			uint64_t run = 0, run_bytes = 0;
			const auto release = [&] {
				if (run_bytes != 0) manager->ChangeState<DirtySource::Cpu, true>(manager->GetCpuAddr() + run, run_bytes);
				run_bytes = 0;
			};
			for (uint64_t at = offset; at < offset + bytes; at += TRACKER_PAGE_SIZE) {
				if (manager->IsModified<DirtySource::Gpu>(at, TRACKER_PAGE_SIZE)) { release(); continue; }
				if (run_bytes == 0) run = at;
				run_bytes += TRACKER_PAGE_SIZE;
			}
			release();
		});
		QueueBdaSync(begin, window);
	}

#if KYTY_BUILD == KYTY_BUILD_DEBUG
	void ValidateGpuDirtyPages(''')

bh = renderer / 'cache/bufferCache.h'
edit(bh, '\tbool TryPeekEopLabel(uint64_t vaddr, void* data, uint64_t size);',
     '\tbool TryPeekEopLabel(uint64_t vaddr, void* data, uint64_t size);\n'
     '\tvoid InvalidateCleanWindow(uint64_t vaddr, uint64_t window) { m_memory_tracker.InvalidateCleanWindow(vaddr, window); }')

rc = renderer / 'renderContext.cpp'
edit(rc, '''		m_buffer_cache.InvalidateMemory(fault_vaddr, fault_size, {BufferCache::ReadbackCaller::HandleFaultWrite, fault_vaddr, fault_size, true});
		m_texture_cache.InvalidateMemory(fault_vaddr, fault_size);''',
     '''		m_buffer_cache.InvalidateMemory(fault_vaddr, fault_size, {BufferCache::ReadbackCaller::HandleFaultWrite, fault_vaddr, fault_size, true});
		m_texture_cache.InvalidateMemory(fault_vaddr, fault_size);
		if (const auto window = NovaSync::FaultWindowBytes(); window != 0) {
			const auto begin = fault_vaddr & ~(window - 1);
			if (IsMapped(begin, window)) m_buffer_cache.InvalidateCleanWindow(fault_vaddr, window);
		}''')
rcs = changes[rc]
first_include = rcs.index('#include')
changes[rc] = rcs[:first_include] + '#include "graphics/host_gpu/novaSync.h"\n' + rcs[first_include:]

for path, s in changes.items():
    path.write_text(s)
print('NOVA_SYNC: fast labels (IRQ on real completion), relaxed readbacks, 64 KiB write-fault window; per-game opt-outs')
