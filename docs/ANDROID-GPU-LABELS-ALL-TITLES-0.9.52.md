# NovaPS5 0.9.52 — GPU completion labels for every title

## Device evidence (owner log, 20 Oct 2026)

Wonder Boy Asha in Monster World (PPSA27841), 0.9.51, NX809J / SM8850 / Android 16, bundled Turnip A8xx.

- Heartbeat game FPS: 16.0 → 11.4 → 12.1 → 10.5 → 9.9.
- GPU worker (tid 22374) per 5 s window: `eop_drain` 2,000–4,700 calls, **3.6–4.6 s inclusive**; nested `wait` 3.5–4.5 s.
- Real work in the same window: draw 0.4–1.3 s, shader 0.1–0.7 s, submit 0.06–0.2 s, present thread ~0.1 s.
- ~200–400 RELEASE_MEM labels per frame, each doing `Finish()` (submit + CPU wait for GPU idle) before the CPU store.

The title was outside the per-title GPU-label allow list (Ever Forward, Super Meat Boy, Dead Cells), so every constant label took the drained fallback.

## Change

`tools/ci/patch-generic-gpu-labels.py` enables `GpuLabelProfile()` and `LabelReadbackProfile()` for all titles — the exact configuration Dead Cells has used since 0.9.50:

- constant 32/64-bit EOP labels are recorded as GPU transfer copies with barriers (`BufferCache::WriteEopLabel`);
- IRQs are deferred to the real GPU timeline;
- guest CPU faults and PM4 WAIT_REG_MEM reconcile the producer's actual tick; pending labels suspend only their PM4 queue.

Unchanged: timestamps, GDS reads, texture-backed and unaligned labels keep the real drain. No predicate, clock or completion is fabricated.

Opt-out: Graphics dialog → **Fast GPU completion** (per game or global) sets `NOVA_GPU_LABELS=0`, which restores the 0.9.51 per-title policy. Titles already on the list stay on.

## Validation

`tests/test_generic_gpu_labels.py` re-runs the production-body tests (label reads, publication, cooperative waits, GPU completion, PM4 fetch) for PPSA27841, the listed titles, Luna and an empty title, with the default and with `NOVA_GPU_LABELS=0`, normal and ASan/UBSan. Passed locally against the staged 0.9.51 Kyty source. CI additionally runs the Vulkan label/poll tests for PPSA27841.

## What to check on device

Look for `NOVA_GPU_LABELS:` once in the log, then compare `eop_gpu` vs `eop_drain`, `readback`, and heartbeat `game_fps` in the same scene. If `eop_drain` stays high, the remaining labels are timestamps/texture-backed and need a separate fix. If FPS rises but `readback` grows, investigate who reads the labels. No FPS figure is claimed until measured on the phone.
