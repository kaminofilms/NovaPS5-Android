# MASTER PROMPT — continue Nova PS5 (paste all of this)

You are continuing work on **Nova PS5**, my port of the KytyPS5 PS5 emulator to native Android. Read everything below before acting. Before you change anything, re-check the reference resources listed in "Resources" for how they solve the same problem, and cite them.

## Hard rules (always)
1. Never download copyrighted games, firmware or keys. No Wine/Proton/Steam/DroidDeck. Don't touch my separate Nova Switch emulator.
2. Never claim a game boots/works without device-log evidence from me. Never fake CI or weaken tests. If you're unsure, say so.
3. Sign every APK with `tools/ci/novaps5-ci-test.keystore`, alias `novaps5dev`, password `android` (so updates install over each other).
4. Ask me before starting a new APK build. I prefer larger, tested, batched releases over micro-fixes (I have usage limits).
5. Research root causes first (resources below + Unity/Unreal/PS5 dev forums + Reddit). End every research answer with a **Sources** list. Ignore rpcs5.com (fake: empty file, no source).
6. Keep messages short.

## Resources (check these first)
- PS5SDK: https://github.com/PS5Dev/PS5SDK
- ps5-payload-sdk: https://github.com/john-tornblom/ps5-payload-sdk
- AnyPS5 (GPL-2.0, same licence as ours; licence in `LICENSES/AnyPS5-GPL-2.0.txt`): https://github.com/boykopovar/AnyPS5 — its `docs/dev/debt/*.md` documents what real games (incl. Unity titles) call; its NGS2 mixer is already ported into Kyty.
- sharpemu (Unity notes: user id 0x10000000, sceKernelRaiseException on target thread, NpCppWebApi stubs): https://github.com/sharpemu/sharpemu
- prosper (libc 512 GiB heap, HLE refs): https://github.com/mattias800/prosper
- FEX-Emu (our CPU translator): https://github.com/FEX-Emu/FEX (pinned commit 14c92681f4d62cf84d901460e0358de09c8847a7)
- Kyty upstream: https://github.com/KytyPS5/KytyPS5

## Project layout
- Repo github.com/kaminofilms/NovaPS5-Android, branch `android-native`. All builds in GitHub Actions `.github/workflows/android-native.yml` (jobs: novafex → novafex-test → ffmpeg → kyty → apk → logs). Release tag `v<ver>-android-<sha7>` with the APK. Logs mirrored to a lab-logs repo `runs/android-<runid>-<sha>/` (kyty build log: `android-kyty/logs/kyty-android-build.txt`).
- Kyty is applied as ONE patch: `patches/kyty-nova-arm64.patch` = `git diff 6d76a5c4 HEAD` of my Kyty fork. To change Kyty: apply patch to Kyty base 6d76a5c4, edit, regenerate the patch.
- `native/novafex/novafex.{h,cpp}` = embedded FEXCore bridge (libnovafex.so). Tests `native/novafex/test/novafex_test.cpp` run on an arm64 runner; must print `NOVAFEX_TEST: ALL PASS`.
- Java launcher `nova-android/src/com/kaminofilms/novaps5/` (MainActivity session log with "Key lines" summary, GameActivity sets env like NOVA_HEAP_HLE, GameStore, Art = SteamGridDB backgrounds, HomeView).
- Version bump: workflow `--version-name/--version-code` + defaults in `tests/verify_native_apk.py`. Current: **0.8.4 / versionCode 42**.
- Device: Red Magic 11 Pro (nubia NX809J, SM8850, Android 16), system Vulkan. Address space is 39-bit (host VA ceiling 0x80_0000_0000); guest user window clamped to [0x10_0000_0000, 0x60_0000_0000). Guest modules load near 0x9_0000_0000.

## How the emulator works (key internals)
- Guest x86-64 runs in FEX with 1:1 addresses. Guest→host calls go through x86 "gates" (`MakeGate`, `GateDispatch`); host→guest via `NovaFex::CallGuest`.
- `NovaFex::InvalidateGuestCode` MUST hold `GetCodeInvalidationMutex()` (FEX's assert macro evaluates try_lock() even in release; fixed in 0.8.3 — it deadlocked before).
- New in 0.8.3: `NovaFex::GetGuestCallContext` (guest regs at the current host call), `SetGateExitHook/ArmGateExitHook` (safe point when a host call returns).
- NIDs = base64(reverse(SHA1(name + hex 518d64a635ded8c1e6b039b1c3e55230)[0:8])), '/'→'-'. e.g. malloc = gQX+4GDQjpM.
- Diagnostics in logs: NOVA_FREEZE (no frame 4 s: per-thread host function/gates/wchan, GPU queue, flips, NOVA_WAIT waiters), NOVA_FAULT (guest regs, last 16 host calls, stack annotated with module exports), NOVA_MEMORY, NOVA_HEAP, NOVA_SIGNAL, NOVA_AUDIO.

## Game status (evidence = my device logs)
- **Dead Cells (PPSA15552)** — WORKS (~58-60 fps, audio OK via AnyPS5 NGS2). Done.
- **ccleste homebrew (PPSA59322)** — has NEVER booted on Android-native (an earlier claim it ran was wrong). Crash at startup: `MapDirect failed 0x80020016 addr=0x400004000 len=0x200000 flags=0x10` (fixed mapping refused, EINVAL), then null deref at guest rip 0x900b8d5c1. In `src/kernel/memory.cpp` MapDirectMemoryImpl, a fixed map returns EINVAL if `in_addr % alignment != 0` (0x400004000 isn't 2 MB aligned) — and the address is also below the clamped guest window. Next: find which check fails, compare with how AnyPS5/sharpemu handle fixed direct maps, honour the request (e.g. ignore alignment for MAP_FIXED, allow fixed maps below the window when the host range is free).
- **Luna Abyss (PPSA36257, Unreal)** — libc.prx reserves 512 GiB and puts its heap at the top (impossible in 39-bit). Approach: NovaHeap (`src/libs/novaHeap.cpp`, TLSF heap, enabled by NOVA_HEAP_HLE=1 which the launcher sets for Unreal games) + `PatchLibc()` rewrites libc.prx allocator exports to `FF 25 00000000 <gate>`.
  - 0.8.2: hung (FEX invalidation lock bug) → fixed 0.8.3.
  - 0.8.3: crashed inside libc `free` with a NovaHeap pointer, because libc free/realloc/reallocalign/malloc_usable_size are wrappers `55 48 89 e5 ff 15 <disp32> 5d c3` (call through a pointer slot) and weren't redirected.
  - **0.8.4 (just built, UNTESTED)**: `BuildOriginalTrampoline` now relocates `call/jmp [rip+disp]` (via r11) so these four are redirected and the original stays callable for old pointers. Check the log for `NOVA_HEAP: 11 libc.prx allocator entry points…` and no "cannot be relocated" lines.
  - If Unreal still can't work this way: fallback "option 3" = give the guest its own translated address space in FEXCore (big job; I approved it if needed).
- **EverForward (PPSA04703, Unity)** — 0.8.2 froze because Kyty ran Unity's GC suspend signal (sceKernelRaiseException SIGUSR1) on the calling thread. 0.8.3 delivers it on the target thread (logs show `NOVA_SIGNAL … (delivered)`), default user id now 0x10000000. Now: black screen, 0 flips, ~60 threads mostly waiting (Unity EventFlag / semaphores); thread "Loading.Preload" spins with millions of host calls (KernelWaitSema). 4 unresolved NpCppWebApi imports (Y295ygEccqk, 8x++mBOUeso, UYPxv8MIzGo = Common::initialize, 52AlYvq+dmk) already return 0 like sharpemu — not the blocker. Next: find what Loading.Preload waits for (likely a file/AIO, GPU or async-read completion); check AnyPS5 docs for Unity loading paths (`--module-dir`, Media/Plugins modules loaded with sceKernelLoadStartModule).
- A known gap: a guest thread spinning in pure guest code with no host calls never receives a raised signal.

## Immediate next steps
1. Give me the 0.8.4 link (already built): https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.8.4-android-2df4742/NovaPS5-0.8.4-android-arm64.apk — wait for my Luna / EverForward / ccleste logs.
2. Research + fix ccleste's fixed MapDirect, EverForward's loading stall, and whatever 0.8.4 shows for Luna. Batch them into one tested build (0.8.5) and ask me before building.
