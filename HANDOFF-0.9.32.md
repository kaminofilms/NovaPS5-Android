# Nova PS5 — handoff after 0.9.32 (for ChatGPT / next engineer)

Paste this whole file. Read it fully before acting.

## Hard rules (from the owner)
1. No DroidDeck/Wine/Proton/Steam/Linux container. Nova PS5 is a native Android app: Kyty (C++, arm64) runs in the app process, guest x86-64 code runs in NovaFEX (embedded FEXCore).
2. Never claim a game boots or hits an FPS unless the owner's device log shows it (`game_fps` in `NOVA_FEX: heartbeat`). Never fake GPU completion, force waits, or weaken tests.
3. Sign every APK with `tools/ci/novaps5-ci-test.keystore` (alias `novaps5dev`, password `android`) so updates install over each other. Never wipe shader caches or saves.
4. **Ask the owner before starting a new APK build.** Batch fixes into one tested build (usage limits).
5. Research root causes first (AnyPS5, sharpemu, shadPS4, FEX, Unreal/PS5 dev forums, Reddit) and cite sources.
6. Keep messages short. Dead Cells must stay ~57–60 FPS.

## Where things are
- Repo: `kaminofilms/NovaPS5-Android`, branch **`fix/0931-luna-super-meat-boy`**, last build commit **`bcb8053`** (this handoff is a later docs-only commit).
- Latest release: **0.9.32-android, version code 80** — https://github.com/kaminofilms/NovaPS5-Android/releases/tag/v0.9.32-android-bcb8053 (CI run 38800432092, all jobs green).
- CI: `.github/workflows/android-native.yml` runs on push to the branches listed at the top (this branch is listed). Jobs: novafex → novafex-test (real arm64 runner) → ffmpeg → kyty → apk (build + `tests/verify_native_apk.py` + mesh check) → release. ~25 min. Put `[skip ci]` in a commit message to avoid a build.
- Version bump = 4 places in the workflow (`--output`, `--version-name/--version-code`, verify step, release tag/title). Next would be **0.9.33 / 81**.
- Kyty source is NOT stored patched. `tools/ci/build-android-kyty.sh` fetches KytyPS5 `df5b9b9`, applies `patches/linux-core.series` (with the base `kyty-nova-arm64.patch` taken from commit `740c604`), then a chain of `git apply` patches and `tools/ci/patch-*.py` scripts, each followed by its `tests/test_*.py`. Add new Kyty changes the same way: an anchored Python patch script (fail if the anchor count ≠ 1) + a test, appended after the 0.9.31 lines.
- To get the patched tree locally: run the top of `build-android-kyty.sh` up to the `cp "$repo/native/novafex/guest_memory.cpp"` line (needs only git + python; `test_pipeline_libraries.py` needs `glslangValidator`).
- FEX patches: `patches/fex-android/000{1,2,3}-*.patch` applied in order to FEX `14c92681…`. NovaFEX bridge: `native/novafex/` (tests in `native/novafex/test/novafex_test.cpp`, must print `NOVAFEX_TEST: ALL PASS`).
- Android launcher: `nova-android/src/com/kaminofilms/novaps5/GameActivity.java` (env vars: `NOVA_GUEST_VA` is on for every title except Dead Cells PPSA15552, `NOVA_WORKDIR` = cwd, `MESA_SHADER_CACHE_DIR`, `NOVA_FPS_CAP`).

## What 0.9.31 → 0.9.32 changed (all in this branch)
1. `tools/ci/patch-0931-pthread-guest-objects.py` + `tests/test_0931_pthread_xlat.py`: `NOVA_XLAT_PTR` added to PthreadCondTimedwaitAbs (POSIX `pthread_cond_timedwait`), PthreadMutexTimedlock, timed rwlock locks, KernelClockGettime/Getres, KernelNanosleep, POSIX semaphore timespec/value. **Device-verified:** Luna hostemu fell from ~7 000/s (0.9.31, 95% at `CreateObject+0x34` and `PthreadCondTimedwaitAbs`) to ~200/s.
2. `patches/fex-android/0003-nova-guest-va-gather.patch`: with guest VA on, AVX2 gathers use the per-element path and translate each element (the SVE `ld1w` gather faulted forever on raw guest bases ≥ 2^39). Dead Cells keeps the SVE path. Bridge test covers vpgatherdd (all-ones + masked) and vpgatherqd across two non-adjacent slots — passes on the arm64 runner.
3. `tools/ci/patch-0931-gpu-watch.py` + `tests/test_0931_gpu_wait_diag.py`: truthful GPU wait logs (says when write history is compiled out; prints label width; `NOVA_GPU_WATCH … satisfies=1/0`). No behaviour change.

## Device results with 0.9.32 (owner's logs, Red Magic 11 Pro, Turnip 26.3)
| Game | Result |
|---|---|
| Dead Cells PPSA15552 | Good: 50–57 FPS, audio fine, hostemu 0. Log shows `Vulkan pipeline cache: initializing … initialized empty` (see item C). |
| Luna Abyss PPSA36257 (Unreal) | Audio works, 2.9–3.7 game FPS, **crashes at the menu**. hostemu now low, so CPU emulation of host accesses is no longer the bottleneck. |
| Super Meat Boy 3D PPSA31162 (Unreal) | 1.3 game FPS, **no audio** (audio port receives samples but `peak=0` = silence), hostemu low. Compute/pixel shaders keep being created every frame (`Shaders: … CS 54→83`). |

## Open problems, evidence, and what to do next (priority order)

### A. Luna crash at the menu (same in 0.9.31 and 0.9.32, deterministic)
- Guest `MainThread`, libc.prx memcpy (`vmovdqu xmm0,[rsi]` at guest rip `0x910003fc6`), **src `rsi=0x0000000800000003`**, dst `0x906d060000`, `rdx=0x858fffee` (~2.2 GB).
- Last host calls: `KernelBatchMap(0x907653010, 1) -> 0`, then mutex lock/unlock pairs.
- `0x0000000800000003` looks like a packed pair of 32-bit values {3, 8}, not a pointer — the game is reading a struct field that the emulator never filled (or filled at the wrong offset/size), most likely an output of a kernel/AMPR call just before.
- Next steps: (1) log the 32-byte `KernelBatchMapEntry` before/after the call and every MapDirect/MapFlexible output in this window (`NovaMemTrace` already exists in memory.cpp); (2) check `sceKernelIsStack`: Kyty returns `EACCES` **without writing `*start/*end`** when the address is unknown, but sharpemu notes the real kernel always writes 0 and that libc's VM allocator otherwise "consumes stale stack values and issues invalid fixed-range reservations" (sharpemu `KernelMemoryCompatExports.cs`, `KernelIsStack`); (3) check AMPR/APR file reads (Luna uses `APREventQueue`; `src/libs/libAmpr.cpp`) — if a read returns short/compressed data the game parses garbage.

### B. Both Unreal games are GPU/shader-bound, not CPU-emulation-bound now
- `NOVA_SHADER_TIME: stage=cs … words=306511 ms=105` (Luna): huge compute shaders take ~100 ms each to translate; plus Turnip pipeline compile (0.9.29 notes: 106–432 ms per graphics pipeline).
- Next steps: (1) asynchronous pipeline compilation with a correct fallback (skip the draw only if the owner accepts visual pop-in — must be opt-in and logged; never fake results); (2) pre-warm from the translated-shader disk cache (`NOVA_SHADER_DISK`) on boot; (3) measure where the 1.3 FPS goes with per-frame timings (CPU guest time vs GPU submit vs pipeline creation) before changing anything.

### C. Vulkan pipeline cache appears never to persist
- Dead Cells (played many times) logs `initializing _PipelineCache/PPSA15552.bin` → `initialized empty` at every boot, and no `saved …` line appears in its log.
- Save is triggered from `GetGraphicsPipeline/GetComputePipeline` when the pipeline count is 16 or a multiple of 64 (`tools/ci/patch-persistent-shaders.py`). cwd is `NOVA_WORKDIR` (chdir in `NovaAndroidStartup`).
- Next steps: find why the file never exists on the next boot (is `Save(true)` reached? does `Common::File` resolve relative paths against cwd? is the workdir cleared?). Fixing this helps every game's load stalls.

### D. Super Meat Boy has no sound
- FMOD threads run, AudioOut2 receives 1875 puts per 15 s, but every buffer is silent (`peak=0`). Luna (also FMOD) has non-zero peaks.
- Next steps: check what FMOD output path SMB uses (AudioOut2 port type/format, `ch=8` F32), compare with Luna; check whether the game is waiting on something (e.g. a Bink/media stream: `BinkAsy*` threads exist) before starting music; see AnyPS5 `docs/dev/debt/libSceAudioOut.md`.

### E. Smaller items
- Remaining hostemu sites: `libmain.so+0x822784` (3 040 hits in SMB, unsymbolized — symbolize with the unstripped `libmain.so` from the CI `android-kyty` artifact), `AgcCreatePrimState` (+0x1d8…+0x418), guest-touching bionic `libc.so+0x6ba60` and `vsnprintf`.
- FEX guest-VA pass does not translate `Push/Pop/PushTwo/PopTwo`, `CacheLine*`, `StoreStackMem` (fine while guest stacks stay below 2^39).
- GPU thread re-polls blocked queues every 100 µs (`CondVar::WaitFor` takes microseconds).
- Luna func=3 wait: `(value & mask) == ref` with ref 1; the producer's E-write of 1 satisfies it — a normal cross-queue dependency, not a compare bug.

## Sources used
- AnyPS5 (GPL-2.0, already partly ported: NGS2 mixer, GPU completion): https://github.com/boykopovar/AnyPS5 — `core/libs/prx/libkernel/DirectMemory/Export.cpp` (BatchMap matches Kyty), `docs/dev/debt/*.md`.
- sharpemu: https://github.com/sharpemu/sharpemu — `src/SharpEmu.Libs/Kernel/KernelMemoryCompatExports.cs` (sceKernelIsStack output initialization; Unreal `../../../` path normalization).
- FEX-Emu (pinned 14c92681): https://github.com/FEX-Emu/FEX — `JIT/MemoryOps.cpp` gather lowering, `OpcodeDispatcher/AVX_128.cpp`.
- shadPS4 (renderer design reference): https://github.com/shadps4-emu/shadPS4
- KytyPS5 upstream: https://github.com/KytyPS5/KytyPS5
