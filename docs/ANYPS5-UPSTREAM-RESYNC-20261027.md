# AnyPS5 upstream status vs Nova's pin — 2026-10-27

Research and staging probe only. No source change to the renderer, no Android build,
no device result.

## What upstream announced

- ~2026-10-09: AnyPS5 reports its decoder recognises all 1,166 tracked PS5 GPU shader
  instructions (RDNA -> SPIR-V). "Implemented" means decoded/lowered, not proven correct
  in every game. Tracked system-library coverage is ~84.8% (2,575 of 3,038 functions).
  One verified playable title on PC (Dreaming Sarah, 2D). Releases v0.1.0 to v0.1.3.
- AnyPS5 keeps guest CPU code as x86-64 and relinks it into a host executable. It has no
  aarch64/Android support upstream (no __aarch64__/ANDROID in core/ at HEAD).

## Nova's position

- Nova already links the full AnyPS5 shader compiler/optimizer, AGC driver/API and an
  adapted VideoOut as libnova_anyps5_renderer.so (docs/ANYPS5-ANDROID-INTEGRATION.md),
  pinned at 9caecfd2d5a822be9daf84c69c7c33c7fafe52b9 (2026-10-18).
- It is OFF by default: native/anyps5/kyty_bridge.cpp Enabled() requires
  NOVA_GPU_BACKEND=anyps5, and no frontend setting exposes it. The phone owner cannot
  currently select it without a PC.
- Upstream HEAD checked: eaf7ee878b1ee6c857740a01ebc069ed67959849 (2026-10-27).
  9,478 commits since the pin; 598 touch core/shader (136 files, +10,696/-1,420).
  Largest churn: core/libs/prx (HLE libraries), AGC driver execution/graphics, relinker.

## Staging probe against HEAD

native/anyps5/renderer/stage.py was run on a copy of upstream HEAD:
- All libSceAgcDriver, CpuTopology, GuestBufferMemory and GuestMemory transforms applied.
- Fails at the VideoOutDriver step: upstream refactored VideoOutDriver.cpp
  (+134/-61; OnMainThread wrappers, new SDL hints, display-mode query). With the
  assertion turned into a report, 6 SDL_ references remain. Several str.replace()
  transforms in that block are unasserted and may have silently not matched, so the
  VideoOut adaptation must be rewritten against the new file, not just relaxed.
- Submission.cpp copySegment and ReadVolatile transforms applied (their asserts passed).
- apply_kyty.py, export manifest regeneration and NDK compilation were NOT run: this
  environment has no Android NDK and Actions must not be started.

## Implications

- The shader milestone helps the AnyPS5 backend only, and only after a resync. It does
  not change Kyty's default renderer, where tasks 1-3 currently live.
- "Every game compatible" is not supported by upstream's own status; HLE library
  coverage and per-game fixes, not shader decode, are the limiting factor.
- Candidate next batch (needs owner approval and an NDK r29 build host):
  1. Rewrite the VideoOut staging for upstream HEAD; harden unasserted replaces.
  2. Regenerate export manifest; re-run host AGC/shader tests and spirv-val.
  3. Add a GPU backend selector (Kyty default / AnyPS5 experimental) to game settings so
     the owner can A/B on device with NOVA_PACING game_fps.
  4. Evaluate porting newer AnyPS5 HLE PRX implementations through NovaFEX call gates.
