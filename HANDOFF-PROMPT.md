# MASTER PROMPT — continue Nova PS5 (paste all of this)

You are continuing work on **Nova PS5**, my port of the KytyPS5 PS5 emulator to native Android. Read everything below before acting.

## Hard rules
1. Never download copyrighted games, firmware or keys. No Wine/Proton/Steam/DroidDeck. Don't touch my separate Nova Switch emulator.
2. Never claim a game boots without my device log showing it (`game_fps` > 0 in the heartbeat). Never fake CI or weaken tests. Say when you are unsure.
3. Sign every APK with `tools/ci/novaps5-ci-test.keystore`, alias `novaps5dev`, password `android`, so updates install over each other.
4. Ask me before starting a new APK build. I prefer larger, tested, batched releases (I have usage limits).
5. Research root causes first (resources below + Unreal/Unity/PS5 dev forums + Reddit) and end research answers with a **Sources** list. Ignore rpcs5.com (fake).
6. Keep messages short.

## Resources
- PS5SDK https://github.com/PS5Dev/PS5SDK · ps5-payload-sdk https://github.com/john-tornblom/ps5-payload-sdk
- AnyPS5 (GPL-2.0, licence in `LICENSES/AnyPS5-GPL-2.0.txt`) https://github.com/boykopovar/AnyPS5 — `docs/dev/debt/*.md` lists what real games call; its NGS2 mixer is already ported.
- sharpemu (Unity notes, NpCppWebApi stubs) https://github.com/sharpemu/sharpemu · prosper (libc heap, HLE) https://github.com/mattias800/prosper
- shadPS4 (Kyty's renderer design: buffer cache / BDA page table / page manager) https://github.com/shadps4-emu/shadPS4
- FEX-Emu (CPU translator, pinned 14c92681f4d62cf84d901460e0358de09c8847a7) https://github.com/FEX-Emu/FEX · Kyty upstream https://github.com/KytyPS5/KytyPS5

## Layout and build
- Repo github.com/kaminofilms/NovaPS5-Android. **Current work branch: `feature/guest-va`** (stable: `android-native`). CI: `.github/workflows/android-native.yml` (jobs novafex → novafex-test → ffmpeg → kyty → apk → logs); run it with `gh workflow run android-native.yml --ref feature/guest-va`. Release tag `v<ver>-android-<sha7>` with the APK. About 10–20 min with ccache.
- Kyty = KytyPS5 commit df5b9b9 + `patches/linux-core.series` (5 small patches, then `patches/kyty-nova-arm64.patch`). To change Kyty: apply the series to df5b9b9, commit after the first five ("base5"), edit, then regenerate `kyty-nova-arm64.patch` = `git diff base5 HEAD`. `tests/test_native_startup.py <patched kyty>` runs in CI before the build and must print two `ALL PASS` lines.
- `native/novafex/novafex.{h,cpp}` = embedded FEXCore bridge (libnovafex.so); `patches/fex-android/0002-nova-guest-va.patch` = FEX guest-VA translation. Bridge tests must print `NOVAFEX_TEST: ALL PASS`.
- Java launcher `nova-android/src/com/kaminofilms/novaps5/` (GameActivity sets env: NOVA_GUEST_VA, NOVA_HEAP_HLE…; MainActivity = settings and the session log with "Key lines").
- Version: workflow `--version-name/--version-code` + defaults in `tests/verify_native_apk.py`. **Current: 0.9.7 / 55.**
- Device: Red Magic 11 Pro (nubia NX809J, SM8850 / Adreno 840, Android 16), 39-bit address space (host VA ceiling 0x80_0000_0000), guest window [0x10_0000_0000, 0x60_0000_0000), guest modules at 0x9_0000_0000.

## How it works
- Guest x86-64 runs in FEX; host (Kyty, native arm64) and guest connect through gates (`MakeGate`) and `NovaFex::CallGuest`.
- **Guest VA translation (on for every title except Dead Cells):** guest addresses ≥ 2^39 are rebased per 1 GiB slot (`NovaFex::TranslateGuestVA`; slot windows come from the guest window, `NovaEnsureVASlots` in memory.cpp). Unreal/libc reserve 512–768 GiB at guest 0x80_0000_0000. Host (emulator) code must translate before touching such memory: `src/common/guestMemory.h` (`GuestMemory::Ptr/Read/Write/Copy/Fill32`) and `common/novaFex.h` `NovaGuest::*`. Untranslated host accesses still work, but each one is a SIGSEGV emulated in `EmulateHighAccess` (slow); they are counted as `hostemu` in the heartbeat with the busiest call sites.
- GPU address domain on aarch64: `regionDefinitions.h` LOWER_ADDRESS_SIZE = 1.5 TiB, no extended memory (covers the translated arenas).
- GPU page-tracking faults on slot host windows are mapped back to guest addresses (`NovaHostToGuestVA` in `HandleGpuFault`); the SIGSEGV handler uses SA_NODEFER (depth-limited).
- Diagnostics: heartbeat every 15 s (`fps` = presenter, `game_fps` = real game flips, `hostemu`), `NOVA_FREEZE: no game frame after 20/45 s` (all threads, GPU queues, flips), NOVA_FAULT, NOVA_ABORT (Unreal fatal text), NOVA_MEMTRACE, NOVA_GPU_WAIT, NOVA_WAIT.

## Status (evidence = my device logs)
- **Dead Cells (PPSA15552)** — works (~60 fps).
- **Super Meat Boy 3D (PPSA31162, Unreal)** — 0.9.5 crashed in VideoOutRegisterBuffers2 (buffer at 0x13FC0000000, above the GPU's old 1 TiB domain); fixed in 0.9.6 (it got past it). The 0.9.6 test ran with the "emulator heap" setting ON and hit Unreal's fatal "Ran out of memory allocating 32 MiB" right after mapping the first 32 MiB display buffer.
- **Luna Abyss (PPSA36257, Unreal)** — 0.9.5: black screen; the GPU ran 8 compute + 1 vertex shader and `AgcEqueue` (EOP ids 0 and 32) waited > 4 s. 0.9.6 with the emulator heap ON: guest null deref at rip 0x90108af2f (linked-list walk) right after `cxa_atexit`.
- **0.9.7**: the emulator heap is forced OFF for translated titles (setting removed; it broke both games). So 0.9.7 = 0.9.5 baseline + the 0.9.6 GPU fixes. No 0.9.7 device log yet.
- EverForward (Unity): black screen (see AnyPS5/sharpemu notes). ccleste homebrew: never booted.

## Next steps
1. Get my 0.9.7 logs for Meat Boy and Luna (let each run ≥ 45 s). Read `game_fps`, the `NOVA_FREEZE: no game frame` report (which thread waits on what, GPU queue state, flips), the `hostemu` call sites, and any NOVA_FAULT/NOVA_ABORT.
2. If `hostemu` is high, translate that call site with `GuestMemory::*` (likely candidates: Agc command builders in `src/libs/agc.cpp` writing PM4 through `CommandBuffer::AllocateDW`, HLE memcpy/memset paths).
3. If Unreal aborts again, the NOVA_ABORT text names the Unreal source file and line; research it and fix the HLE it depends on.
4. Batch fixes into one tested build and ask me before building.
