You are continuing work on **Nova PS5**, my port of the KytyPS5 PS5 emulator to native Android. Read all of this before doing anything.

## Project
- Repo: github.com/kaminofilms/NovaPS5-Android, branch `android-native`. All builds run in GitHub Actions (workflow `.github/workflows/android-native.yml`, jobs: novafex → novafex-test → ffmpeg → kyty → apk → logs). Build logs are mirrored to a lab-logs repo under `runs/android-<runid>-<sha>/`.
- Kyty is not vendored: it is applied as one patch, `patches/kyty-nova-arm64.patch` (diff of my Kyty fork from base commit `6d76a5c4`). Kyty changes = edit the fork, commit, regenerate the patch with `git diff 6d76a5c4 HEAD > patches/kyty-nova-arm64.patch`.
- Pieces in the APK: `libmain.so` (Kyty, native arm64), `libSDL3.so`, `libnovafex.so` (embedded FEXCore; source `native/novafex/novafex.{h,cpp}`, tests `native/novafex/test/novafex_test.cpp`, run on an arm64 runner and must print `NOVAFEX_TEST: ALL PASS`). Java launcher in `nova-android/src/com/kaminofilms/novaps5/` (MainActivity, GameActivity, GameStore, Art (SteamGridDB), HomeView).
- Guest PS5 x86-64 code runs through FEX with 1:1 addresses. Guest→host calls go through x86 "gates" (`MakeGate`, `GateDispatch`); host→guest through `NovaFex::CallGuest`. Guest modules load around 0x9_0000_0000; the guest user window is clamped to [0x10_0000_0000, 0x60_0000_0000) because the phone's address space is 39-bit (host VA ceiling 0x80_0000_0000).
- Device: Red Magic 11 Pro (nubia NX809J, Snapdragon SM8850, Android 16), system Vulkan driver.
- Version bump: the workflow `--version-name/--version-code` and the defaults in `tests/verify_native_apk.py` (currently 0.8.3 / versionCode 41). Releases are published as `v<ver>-android-<sha7>` with the APK attached.

## Hard rules (always follow)
1. Never download copyrighted games, firmware or keys. No Wine/Proton/Steam. Don't touch my Nova Switch emulator project.
2. Never claim a game boots without device-log evidence. Never fake CI or weaken test assertions.
3. Always sign with `tools/ci/novaps5-ci-test.keystore`, alias `novaps5dev`, password `android`.
4. Ask before I run a new APK. I prefer bigger, tested, batched builds over many micro-fixes (I have weekly usage limits).
5. Research before fixing (PS5SDK, ps5-payload-sdk, AnyPS5, sharpemu, prosper, Unity/Unreal forums, Reddit). Always end with a Sources list. rpcs5.com is fake (empty file, no source); ignore it.
6. Keep messages short.

## Reference emulators I use (licences ok: AnyPS5 is GPL-2.0 like us, licence copied to LICENSES/AnyPS5-GPL-2.0.txt)
- AnyPS5 github.com/boykopovar/AnyPS5 — its NGS2 audio mixer is already ported into Kyty (`src/libs/anyngs2/*`, exports wrapped in `src/libs/anyNgs2Exports.cpp`, compiled with -fexceptions -frtti per-source). Its `docs/dev/debt/*.md` documents what real games (incl. Unity titles) call.
- sharpemu (Unity notes: user id 0x10000000; sceKernelRaiseException must run on the target thread).
- prosper / sharpemu PRs about the libc 512 GiB heap arena (Unreal).

## Game status (last device test = 0.8.2)
- **Dead Cells (PPSA15552)**: works, ~58-60 fps, audio works (AnyPS5 NGS2). A GPU wait on label 0x20edb76d0 (game writes 0, waits for 1) is mitigated by a 2 s give-up. Treat as done.
- **Luna Abyss (PPSA36257, Unreal)**: 0.8.0/0.8.1 crashed because libc.prx reserves 512 GiB and maps its heap at the top (beyond what a 39-bit phone has). Fix path: NovaHeap (`src/libs/novaHeap.cpp`, TLSF heap in a 32 GB reservation, enabled with NOVA_HEAP_HLE=1 which the launcher sets for Unreal games detected by `.utoc/.ucas` or `Content/Paks/*.pak`). Imports of malloc/free/new/delete bind to it by NID, and `PatchLibc()` rewrites libc.prx's own allocator entry points with `FF 25 00000000 <gate>`.
  - 0.8.2 result: no crash anymore, but it hung right after patching (one guest thread, futex wait, gates frozen at 3414). Cause found: `NovaFex::InvalidateGuestCode` called FEX's `InvalidateCodeBuffersCodeRange` without holding `CodeInvalidationMutex`; FEX's assert macro still evaluates `try_lock()` in release builds, so the mutex was taken and never released → every later JIT compile blocked. Also libc free/realloc/usable_size were NOT redirected (they're real functions, not jump thunks), so libc free would receive NovaHeap pointers.
  - 0.8.3 fixes both: InvalidateGuestCode now takes the mutex with `std::unique_lock`; `BuildOriginalTrampoline` relocates the first ≥14 bytes of those libc functions (small x86 decoder, handles rel8/rel32 branches, refuses RIP-relative) so they can be redirected and the original stays callable for old pointers.
  - Fallback if Unreal still fails: rewrite FEX memory translation so guest addresses above the 39-bit limit are remapped (big job).
- **EverForward (PPSA04703, Unity)**: freezes at ~21 frames. All job workers wait on 'Unity EventFlag', one waiter on 'resumeEvent', GPU idle, no flips. Cause: Unity's IL2CPP GC stops threads with `sceKernelRaiseException(thread, SIGUSR1)`; Kyty's Android path ran the handler on the *calling* thread, so the GC thread suspended itself (AnyPS5 libkernel.md documents this Unity PS5Util behaviour; handler reads mc_rsp at ucontext+0xf8).
  - 0.8.3 fix: on Android the signal is queued for the target thread (`PthreadQueuePendingSignal` + wake + `WaitForSignalDispatch`) and delivered at its next safe point: blocking waits/sleeps already poll every 10 ms, plus a new FEX gate-exit hook (`NovaFex::SetGateExitHook/ArmGateExitHook`) when a host call returns. The handler gets the real guest registers/stack from `NovaFex::GetGuestCallContext` (rip = return address, rsp = caller rsp, callee-saved exact). Default user id changed from 1000 to 0x10000000 (Unity maps small ids to slot -1; AnyPS5 and sharpemu use 0x10000000).
  - Known gap: a thread spinning in pure guest code with no host calls never gets the signal.

## Current state
- Commit `c24f479` on android-native = 0.8.3. novafex + novafex-test jobs PASSED (new tests: invalidate+recompile, guest call context, gate exit hook). The kyty and apk jobs were still building when I handed off. If kyty fails, read `runs/android-<runid>-c24f479*/android-kyty/logs/kyty-android-build.txt` in lab-logs, fix, push.
- When the release `v0.8.3-android-c24f479` exists, I'll test Luna and EverForward and send the in-app Session logs (they have a "Key lines" summary at the top). Look for: `NOVA_HEAP:` lines (all 11 entry points redirected?), `NOVA_SIGNAL:` (RaiseException delivered?), `NOVA_FREEZE`/`NOVA_WAIT` reports, `NOVA_FEX: guest fault` reports.

## Useful diagnostics already in the build
- NOVA_FREEZE watchdog (no frame for 4 s) dumps every thread: gates, current host function, wchan, plus GPU queue state (`NOVA_GPU_WAIT`), flip queue (`NOVA_VIDEO`), event flag/queue waiters (`NOVA_WAIT`).
- Guest fault report: guest registers (FEX SRA mapping rax=x4, rcx=x7, rdx=x5, rbx=x6, rsp=x8, rbp=x9, rsi=x10, rdi=x11, r8-r15=x12-x17,x19,x29), last 16 host calls, stack values annotated with the nearest module export.
- NOVA_MEMORY logs for oversized reservations; NOVA_AUDIO per-port stats.

Next step for you: confirm the 0.8.3 build finished (or fix it), give me the APK link, then wait for my logs and continue from the evidence. Sources list at the end of every research answer.
