# Research: what the fast PS4/PS5 emulators do differently — 20 Oct 2026

Trigger: 0.9.52 made Wonder Boy Asha slower (10–16 → 6.5–7.4 FPS) and Ever Forward slower (4–6 → 3.7 FPS). No build was started for this research.

## 1. What our own logs say (0.9.52, NX809J, Turnip A8xx)

| Title | Main cost per 5 s window on the GPU thread |
|---|---|
| Wonder Boy Asha PPSA27841 | `eop_label_publish` 4.1–4.5 s (1,250–1,670 CPU faults on label pages, avg ~2.7 ms each, max 46–64 ms). Draw 0.2–1.0 s. `eop_drain` now ~70 calls. |
| Ever Forward PPSA04703 | `readback` 2.7–3.3 s, of which `eop_label_publish` 1.7–2.3 s. `queue_poll_wait` is gone (ordered waits: ~3,000/5 s). Draw 2.0 s. |

The game's CPU reads (and rewrites) completion labels hundreds of times per second. Nova makes every such access wait until the GPU has executed everything recorded so far. Whether that wait happens at the packet (`eop_drain`, ≤0.9.51) or at the CPU fault (`eop_label_publish`, 0.9.52), it is the same CPU↔GPU serialization.

## 2. How every reference project handles labels

| Project (revision inspected) | EOP/RELEASE_MEM label | CPU reading GPU-written memory |
|---|---|---|
| **KytyPS5 upstream** HEAD 7b7f9a7 (20 Oct) and Nova's pin df5b9b9 | `memcpy` into guest memory **when the packet is processed**; IRQ deferred to real completion (`TriggerEopEventAtEndOfPipe` → `DeferPriorityOperation`). `WaitRegMem` just tests memory and suspends. | Optional "readback linear images" setting, default off (commit d70f9c0). |
| **shadPS4** main c1b2655 (21 Oct) | `ReleaseMem`/`EventWriteEop` → `SignalFence` → `TryWriteBacking` **immediately**; `WaitRegMem` yields until memory matches (`src/video_core/amdgpu/liverpool.cpp`). | `readbacks_mode` Disabled / Relaxed / Precise, **default Disabled** (`src/core/emulator_settings.h`). Precise = page-protect GPU-written pages (Nova's current model). |
| **Bloodborne-Android** 0ca25cb (20 Oct; FEXCore + shadPS4 renderer on Adreno/Turnip, 34–35 FPS on SD 8 Gen 2) | Default: CPU store after host copies, at record time. Optional `BB_HONEST_LABELS`: a dedicated `bb:GpuSignals` thread waits on the timeline semaphore and then stores — the guest never blocks, it just keeps polling. GPU-side `vkCmdUpdateBuffer` labels only when guest memory is mapped in place. | `BB_READBACKS` default **Relaxed**. |
| **AnyPS5** 3b5a24c (21 Oct) | GPU writes the label into guest memory imported with `VK_EXT_external_memory_host`; fallback is an immediate `GuestMemory::Write`. | GPU works in place on imported guest memory. |
| **Nova ≤0.8.1 / 0.9.10** | Immediate CPU store (Kyty default). Dead Cells 50–60 FPS (owner logs, `docs/ANDROID-REGRESSION-RECOVERY-0.9.50.md`). | — |
| **Nova 0.9.14 → 0.9.52** | Drain or fault-publish after real completion (adapted from AnyPS5's *fallback*, `docs/ANYPS5-GPU-INTEGRATION.md`). Introduced for Super Meat Boy / Luna, which were never verified to need it. Dead Cells fell to ~37 FPS with 3.6–4.1 s/5 s in `eop_drain` (`docs/EVER-048-DEVICE-FINDINGS.md`). | Precise-equivalent page protection, always on. |

Conclusion: no fast emulator blocks the guest CPU on a label. They either publish at command-processing time (Kyty, shadPS4, Bloodborne default) or let the GPU / a completion thread publish later while the guest keeps polling (AnyPS5, Bloodborne honest mode). Nova is the only one doing a blocking wait, and it is the largest measured cost in both titles.

## 3. Readback cost in other projects

- shadPS4 RFC #4316 measured Precise readbacks at ~68 µs per `Scheduler::Finish()` on an RTX 5090, and a community RX 6750 XT test dropped DriveClub from 30 to ~17–20 FPS with Precise. They proposed batching downloads per PM4 sync point. Our Turnip waits are ~2.7 ms each — about 40× worse — so the effect on a phone is much larger.
- The inFAMOUS fork (HayatoG/iss_pc PR #14): readbacks cut ~55 → 30 FPS; letting the reading guest thread wait only for its own download (not a full drain) gave ~32 FPS median from 25–30.

## 4. Other measured wins worth porting (Bloodborne-Android `docs/parallel_gpu.md`)

| Technique | Their result |
|---|---|
| Unprotect a 64 KiB window around each write fault (later 256 KiB) | 115k → 16k faults/s; **66.4 → 81.0 FPS (+22%)** |
| Speculative draw preparation on 4 worker threads, validated on the GPU thread | 64.1 → 71.5 FPS (+11.5%), identical screenshots |
| Texture-description cache | 65.6 → 93.9 FPS in another view |
| Async guest→staging copies on copy threads, staging pool kept warm | streaming stalls 60–170 ms → 40–50 ms |
| Hot-page re-upload instead of re-protecting repeatedly written pages | opt-in; naive version regressed to 33 FPS |
| userfaultfd write-protection instead of mprotect | removed mprotect time, no measurable stall change; opt-in |

The inFAMOUS fork also compiles compute pipelines off the GPU thread (60–190 ms each, 0.6–3.8 s freezes) and submits every ~1,024 draws so the GPU is not left idle.

Turnip specifics: `vkCmdUpdateBuffer`/copy labels must end the render pass on a tiler (Bloodborne doc and Vulkan spec). Nova's 0.9.52 GPU labels call `EndRendering()` per label (~1,700 per 5 s in Wonder Boy, ~6,000 in Ever Forward), which costs GMEM store/load on Adreno. An immediate CPU store avoids that entirely.

Unified memory on Turnip: Bloodborne-Android shares memory by allocating exportable Vulkan memory as dma-buf and mapping it as guest memory; KGSL imports it IO-coherent by default. Whether Turnip exposes `VK_EXT_external_memory_host` (AnyPS5's route) is unverified — a RetroArch report lists it as missing on Adreno 650. Treat as long-term.

## 5. Recommended 0.9.53 batch (not built — needs owner go-ahead)

1. **Label mode setting, default "Fast"**: restore Kyty/shadPS4 behaviour — store constant EOP labels into guest memory when the packet is processed, IRQ still at real completion, timestamps sampled at completion. Keep the current path as "Accurate" per game. No WAIT_REG_MEM timeout bypass (that old diagnostic stays removed).
2. **Readback mode setting** like shadPS4: Precise (current) / Relaxed (only CPU *writes* to GPU-modified pages force a download) / Off. Default per title once measured; Ever Forward's ~0.9 s non-label readback is the test case.
3. **Write-fault window**: unprotect 64 KiB around a write fault (Bloodborne +22%).
4. **Turn 0.9.52's GPU labels and ordered waits off by default** (keep the code behind the switches).

Validation for the batch: same production-body tests as 0.9.52 plus a Fast-mode test that a label is visible to the CPU right after its packet and its IRQ still follows completion. On device: Dead Cells should return toward 50–60 FPS (historical baseline). Wonder Boy and Ever Forward should drop `eop_drain`/`eop_label_publish` to near zero.

Later, bigger items: speculative draw prep threads, async pipeline compilation, periodic submits, unified memory.

## Sources

- KytyPS5: https://github.com/KytyPS5/KytyPS5 (HEAD 7b7f9a7, `src/graphics/guest_gpu/graphicsRun.cpp` write32/write64 and WaitRegMem; commits d70f9c0, 8e42e99, d58aefd)
- shadPS4: https://github.com/shadps4-emu/shadPS4 (main c1b2655, `src/video_core/amdgpu/liverpool.cpp`, `src/core/emulator_settings.h`, `src/video_core/buffer_cache/*`)
- shadPS4 readback RFC: https://github.com/shadps4-emu/shadPS4/issues/4316
- inFAMOUS fork readback/stutter PR: https://github.com/HayatoG/iss_pc/pull/14
- Bloodborne-Android: https://github.com/ducvd89/Bloodborne-Android (0ca25cb: README, `docs/parallel_gpu.md`, `docs/TRANSLATION_GPU_COPY_LABELS.ru.md`, `docs/ANDROID_UNIFIED_MEMORY_PLAN.md`, `gpu/shadps4/video_core/amdgpu/liverpool.cpp`, `vk_rasterizer.cpp`)
- Bloodborne-Android coverage: https://androgaming.com/bloodborne-on-android-uses-fex-and-shadps4-technology/
- AnyPS5: https://github.com/boykopovar/AnyPS5 (3b5a24c, `PacketMemory.cpp`, `GuestBufferMemory.cpp`, `VulkanDevice.cpp`)
- KytyPlus: https://github.com/Coder787-source/KytyPlus (d7991a6; no label/readback changes beyond KytyPS5)
- CapyPS5 (Kyty-based Android, Dead Cells up to 60 FPS): https://www.oficinadanet.com.br/games/73395-capyps5-emulador-ps5-android
- Kyty on PC status: https://www.tomshardware.com/video-games/playstation/ps5-emulation-hits-new-milestone-in-record-time-multiple-3d-games-now-playable-in-kyty-performance-and-support-steadily-improving-with-30-fps-gameplay-possible-today
- RetroArch Adreno extension report: https://github.com/libretro/RetroArch/issues/18143
- Vulkan `vkCmdUpdateBuffer` (outside render pass only): https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdUpdateBuffer.html
