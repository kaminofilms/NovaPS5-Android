# NovaPS5 0.9.54 — fixes from the 0.9.53 owner logs

| Title | 0.9.53 log | Cause | Fix |
|---|---|---|---|
| Dead Cells PPSA15552 | Freezes ~10 s after the menu in both GPU-sync modes. `NOVA_GPU_WAIT` on a 64-bit word that only the CPU sets to 1; `queue_poll_wait` 3.5 s/5 s. | The GPU queue waits for a CPU flag. The CPU waits for an EOP interrupt that is deferred to the GPU timeline, but nothing submits the recorded command buffer while every queue is suspended. | **Idle submit:** submit once per idle period (Bloodborne-Android rule: the GPU thread submits when it runs out of work). |
| Wonder Boy PPSA27841 | 20 → 5 FPS over 45 s, then `MasterSemaphore::Wait` fatal (Vulkan device lost). Submits fell from ~4,600 to ~200 per 5 s after fast labels. | Very large command buffers; the GPU idles while the CPU records. | **Periodic submit** every 1024 draws/dispatches (inFAMOUS shadPS4 fork `ISS_SUBMIT_DRAWS`). |
| Ever Forward PPSA04703 | 9.5–13.7 FPS (was 4–6). `readback_write` 1.9–2.5 s/5 s, ~650–2,500 CPU write faults on GPU-written pages, each waiting ~2.5 ms. | Precise ownership: the CPU write first downloads GPU data. | **Readback Off** (default; shadPS4 `GpuReadbacksMode::Disabled` default): the CPU write wins, no download or wait. Relaxed/Precise selectable. |
| Hollow Knight PPSA34971 | 48–56 FPS, muffled/crackling audio. AAudio low-latency mode, 40 ms queue, `queued` ≈ 12 KB (~33 ms). | SDL notes low-latency mode sounds flat on some devices; 40 ms does not absorb 30–60 FPS swings. | **80 ms queue** and normal AAudio performance mode (`NOVA_AUDIO_LATENCY_MS`, `NOVA_AUDIO_LOW_LATENCY`). |
| Luna Abyss PPSA36257 | No frames; the session ends during memory setup; the crash is the present thread reading Config during process teardown. System Vulkan driver selected. | Still loading when exited (no new fatal before teardown). | Not changed beyond the idle submit; retest with the bundled Turnip driver and wait longer. |
| All | — | Internal resolution was Ever Forward only and 1080p only. | **Internal resolution** 100/75/67/50/33/25 % for every title, any 16:9 pass ≥ 540p. |

## Validation

`tests/test_0954_stability_speed.py` (normal + ASan/UBSan) runs:
- the idle-submit structure: flush before the queue lock, once per idle period, reset on progress;
- `NovaPeriodicSubmit` with the real template and env bounds;
- the production readback-off block (no download, GPU ownership dropped, reads unaffected) against every mode;
- audio latency parsing and the low-latency hint before both `SDL_InitSubSystem(SDL_INIT_AUDIO)` calls;
- `novaRasterScale.h` extents for 1080p/2160p/720p and invalid sizes.

The 0.9.53 native-sync tests pass on the 0.9.54 source. Touched C++ files show no new `g++ -fsyntax-only` errors (pre-existing GCC-only Vulkan-Hpp ambiguities are unchanged). `GraphicsSettings.java` compiles against Android API stubs. FPS is unverified until the owner's device logs.

## Risks

Readback Off can show stale data where a game's CPU partially rewrites a page the GPU also wrote; use Relaxed or Precise for that game. Lower internal resolution can blur or break effects that sample the main targets at native coordinates; use Native for that game.
