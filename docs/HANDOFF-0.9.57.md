# Nova PS5 Android: handoff (0.9.57, 2026-10-21)

You are taking over **Nova PS5**, an Android PS5 emulator. The owner (repo `kaminofilms/NovaPS5-Android`, branch **`perf/0952-eop-drain`**) tests on a **Red Magic 11 Pro** (nubia NX809J, Snapdragon 8 Elite Gen 5, **Adreno 840**, Android 16, liquid cooled).

Goals:
- 30–60+ FPS, stable, in their games.
- An internal-resolution option on every game.

## Owner rules (follow them)

- **Ask before starting any APK build.** They have usage limits and want fewer, larger, pre-tested builds.
- Research root causes first and cite sources (GitHub issues/PRs, emulator source, Mesa MRs, Reddit, dev forums). No speculative micro-fixes.
- Keep the same signing key so APKs install as updates. `tools/ci/novaps5-ci-test.keystore` is already used by CI.
- Test locally before handing anything over: production-body tests, plus ASan/UBSan.
- Be honest about what is proven and what is a guess.

## Architecture

- **Kyty** (KytyPS5 at pin `df5b9b9`) is cloned and patched at build time by `tools/ci/build-android-kyty.sh`.
  - Patches are Python overlays in `tools/ci/patch-*.py`. Each one asserts its anchors (`edit(path, old, new)` raises if the text changed).
  - Each patch is followed by its test in `tests/test_*.py`, inside the regression block that tees to `regression-050.txt`.
  - New patches are appended **after** the last 0.9.57 lines.
- **NovaFEX** (`native/novafex/`) is an embedded FEXCore that translates only guest x86-64 code. The emulator itself is native ARM64.
  - Guest→host calls go through "gates". Each thread keeps a ring of its last 16 host calls (`t_thread.recent`).
  - A translated guest address space backs 1 GiB slots on demand above 2^39 (`NOVA_GUEST_VA`) for Unreal titles.
- **Launcher (Java)**: `nova-android/src/com/kaminofilms/novaps5/`.
  - `GraphicsSettings.java` sets every `NOVA_*` env var per title. Versioned keys: `*_v56`, `tu_debug_v57`.
  - The safe profile covers PPSA36257 and PPSA31162.
  - `Telemetry.java` writes `NOVA_THERMAL` every 5 s.
  - `GameActivity.java` prepares the environment.
- **CI**: `.github/workflows/android-native.yml`.
  - Builds only by `gh workflow run android-native.yml --ref perf/0952-eop-drain`; the branch is not in the push triggers.
  - Bump version name and versionCode in the workflow on each release (0.9.57 = versionCode 111).
  - The release is created automatically as `v0.9.57-android-<sha>`.
- **Local staging** (the scratch tree is gone in a new session): clone Kyty at the pin and run the patch chain from `build-android-kyty.sh` with tests. For syntax checks, `clang++ -fsyntax-only` with the include list in the build script works on x86. Code guarded by `KYTY_NOVA_FEX` only compiles for aarch64.

## Games and state as of 0.9.56 logs (Turnip A8xx 2026-10-12 unless noted)

| Game | State | Cause (evidence) | 0.9.57 change |
|---|---|---|---|
| Dead Cells PPSA15552 | Freezes about 30 s in, on both drivers and both sync modes | A GPU queue waits forever on `WAIT_REG_MEM` 64-bit at `0x20edb76d0`, eq ref 1, value 0. 0.7.3–0.9.10 had a give-up (2 s, then 100 ms on a remembered address); the game ran at 53–60 FPS with it. Commit `dd48245` (0.9.14) removed it. | `patch-0957-deadcells-wait.py` restores it for Dead Cells (`NOVA_GPU_WAIT_GIVEUP=0/1`). Dead Cells back on Fast sync. |
| Ever Forward PPSA04703 (Unity) | Turnip: about 20 FPS steady (best yet). System driver: stuck at 0 FPS | Each 5 s window: about 980 CPU write faults on pages that also hold GPU-written bytes. Each waits about 3 ms for the GPU, about 3 s per 5 s in total. `address_disjoint=978/978`: the CPU write never touches the GPU's bytes (false sharing). | `patch-0957-deferred-write-faults.py`: asynchronous copy, byte snapshot, page released immediately, later merge that keeps CPU-changed bytes; uploads skip pending GPU-owned bytes. EF only by default (`NOVA_DEFERRED_WRITE_FAULTS`). |
| Wonder Boy Asha PPSA27841 | FPS 49→38→29→24→11→7, then `VK_ERROR_DEVICE_LOST` (`masterSemaphore.cpp:55`) | Renders 3840x2160 despite the 1080p `VideoOutGetOutputStatus` report. The game calls no other video-out query; the log shows no unresolved video imports. RSS grows 1.9→3.4 GB. The cause of the growing GPU work is unknown. | Graphics → Turnip workaround (`TU_DEBUG` = nolrz / sysmem / both) to test. Next: GPU timestamp per pass/shader; check indirect/append counters. |
| Luna Abyss PPSA36257, Super Meat Boy 3D PPSA31162 (Unreal) | Quit during startup memory setup, before any frame, even with the safe profile | The game calls libkernel `exit()` itself (`6Z83sYWFlA8`). FORTIFY "destroyed mutex" lines and the `Config::*` backtraces are teardown fallout. The 768 GB `ReserveVirtualRange` **succeeds** (placed at guest `0x8000000000`). Last progress was in the 0.9.36 era (Meat Boy gameplay about 1 FPS, Luna 959 frames), so the regression is between 0.9.36 and 0.9.53. | `patch-0957-guest-exit-report.py` prints `NOVA_GUEST_EXIT:` lines: code, guest RIP, return module+offset, stack modules and texts, last 16 host calls with return values (NovaFEX `DumpRecentHostCalls`), memory trace. **Read that output first**: the failing call is likely among the last host calls. |
| Hollow Knight PPSA34971 | Runs 30–60 FPS | — | — |

Notes:
- Thermal throttling is ruled out: `thermal=none`, battery 34–44 °C.
- `gpu_mhz` and `gpu_busy` read `n/a`; SELinux blocks them.

## What 0.9.53–0.9.56 changed (for regressions)

- **0.9.53:** Fast labels (labels written when the packet is processed), Relaxed readback, 64 KiB write-fault window (`novaSync.h`).
- **0.9.54:**
  - Idle submit when every PM4 queue is suspended.
  - Periodic submit every 1024 draws.
  - Readback "Off". This was a mistake: it drops GPU data on CPU writes, and as of 0.9.56 it is opt-in only.
  - 80 ms audio queue.
  - Resolution scale for any 16:9 pass.
- **0.9.55:** report a 1080p display; readback telemetry for all titles.
- **0.9.56:**
  - Background graphics-pipeline compilation (`NOVA_ASYNC_PIPELINES`). Side-effect-free draws are skipped while compiling. One worker thread; a mutex serializes `CreatePipelineInternal`.
  - Relaxed default.
  - Safe profile.
  - Cleared scaled passes skip the down-blit.
  - Thermal telemetry.
- **Internal resolution:** the current scaler (`novaRasterScale.h`, `Image::BeginRasterScale`) blits native→proxy→native on every pass. That is why it barely helps. The real fix is a yuzu/Eden-style allocation-time rescaler.

## Next steps (priority)

1. When the 0.9.57 logs arrive, check each item:
   - Dead Cells: do `gave up on … continuing` lines appear, and does FPS hold?
   - Ever Forward: compare `NOVA_DEFERRED_WRITE_FAULTS` against FPS and `readback_write` time.
   - Luna and Meat Boy: work out the failing call from `NOVA_GUEST_EXIT`.
   - Wonder Boy: compare nolrz, sysmem and the system driver.
2. Fix the Unreal exit from the report's evidence, for example a failing `sceKernel*` memory query or mapping return code.
3. Wonder Boy: GPU timestamp queries per submit/shader to find what grows, plus cache-size telemetry (buffers, images, dirty ranges).
4. Real render-target rescaler (allocation-time scaling) for internal resolution.
5. Later: ADPF or thread affinity to put the GPU and guest threads on prime cores; cache GC watermark.

## Sources used so far

- shadPS4: `liverpool.cpp` WaitRegMem and readbacks_mode.
- yuzu/Eden: buffer cache word manager and resolution rescaler.
- Bloodborne-Android fork: fast labels, 64 KiB fault window, power plan.
- inFAMOUS shadPS4 fork: periodic submit.
- Eden PR #3205: TU_DEBUG gmem/noubwc, compatibility only.
- Banners-Turnip releases: A8xx described as "compile-verified only".
- Android Authority: Turnip for Adreno 8xx still in development.
- Capy PS5: also a Kyty fork, with async pipelines and a res scale option. Its developer reported CPU/GPU shared-memory writes erasing each other, and that no game got past the splash screen as of Oct 15.
