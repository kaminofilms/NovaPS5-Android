# NovaPS5 0.9.53 — native-speed sync for every title

Basis: `docs/RESEARCH-NATIVE-SPEED-20261020.md`. 0.9.52 owner logs: Wonder Boy Asha 6.5–7.4 FPS with 4.1–4.5 s per 5 s in `eop_label_publish`; Ever Forward 3.7 FPS with 2.7–3.3 s in `readback`. Every reference emulator (KytyPS5 upstream, shadPS4, Bloodborne-Android, AnyPS5) lets the guest CPU see labels without blocking.

## Changes (defaults for all titles; `tools/ci/patch-0953-native-sync.py`)

1. **Fast labels** (`NOVA_LABEL_MODE=fast`): constant and timestamp RELEASE_MEM labels are stored into guest memory when the packet is processed, as in KytyPS5 upstream and shadPS4. Interrupts are still deferred to the real GPU timeline. GPU-recorded labels, label publication, cooperative/ordered waits and drains are bypassed. `accurate` restores 0.9.52 behaviour.
2. **Relaxed readbacks** (`NOVA_READBACK_MODE=relaxed`): GPU-written pages are no longer read-protected, so guest CPU reads never wait for a download (shadPS4 Relaxed/Disabled, Bloodborne `BB_READBACKS` default). They stay write-protected: a CPU write still downloads GPU data first, so nothing is lost. PM4 WAIT_REG_MEM keeps coherent reads via `TryReadBufferBacking`. `precise` restores page read protection; accurate labels always use precise.
3. **64 KiB write-fault window** (`NOVA_FAULT_WINDOW_KB=64`, 0 disables): after a write fault, CPU-clean and GPU-clean pages of the aligned window are released in contiguous runs and BDA sync is queued. GPU-dirty pages are untouched. Bloodborne-Android measured +22% FPS.

Graphics dialog, per game or global: GPU sync (Fast/Accurate), GPU memory readback (Relaxed/Precise), Write-fault window. The launch log records `sync=… readback=… fault_window=…`, and the game log prints `NOVA_SYNC:` once.

## Risks

Fast labels: a game that relies on a label meaning "GPU really finished" for CPU-side reuse may show flicker or corruption. Relaxed readbacks: CPU-side logic that reads GPU compute results sees stale data (physics, occlusion, GPU-driven culling). Both are per-game switches. Dead Cells used fast labels at 50–60 FPS in 0.8.1/0.9.10.

## Validation

`tests/test_native_sync.py` (normal and ASan/UBSan) runs the production bodies:
- the mode switches for five titles, with `GpuLabelProfile`/`LabelReadbackProfile` off in fast mode;
- RELEASE_MEM 32/64-bit fast labels visible before any submit, with IRQ only after completion, immediate timestamps and unsupported/null rejection;
- `UpdateProtection`, where relaxed mode skips read protection only;
- `InvalidateCleanWindow` for alignment, GPU-dirty exclusion, runs, BDA sync and invalid sizes.

Accurate mode re-runs the existing GPU-completion and ordered-wait tests. All touched translation units (graphicsRun, bufferCache, renderContext, memoryTracker, pageManager) pass `g++ -fsyntax-only` against the staged source. No FPS figure is claimed until measured on the device.
