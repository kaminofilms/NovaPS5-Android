# NovaPS5 0.9.24 — shader semantic and AJM native guest-memory hot paths

## Device evidence (0.9.23, PPSA31162)

On a nubia NX809J (Android 16, Adreno 840, bundled Turnip A8xx),
the game no longer crashes at ARM64 LD1 but reports 0.5–0.8 game FPS.
The late heartbeat shows 1,820,374 host-emulated accesses and an increase of
637,563 between heartbeat samples. The largest named sites include
`Libs::Graphics::PrepareProgram(PixelShaderInfo...)`,
`Libs::Audio::Ajm::AjmOpusDecoder::Decode`, and AJM batch/result functions.
No aggregate timing proof exists that signal emulation alone explains all
of the frame time; ongoing shader compilation and memory pressure also matter.

## Production changes

After applying the existing full 0.9.23 Kyty patch series:

* Shader mapped-data registration converts the semantics-table pointer into
  a native host view if the entire bounded table fits in a mapped guest slot.
  The shader code address/hash, register values and original guest pointers
  outside the local view are unchanged. Cross-slot semantics retain the old
  slow path rather than treating unrelated host slots as contiguous.
* AJM batch receiver access uses a native alias for cursor, capacity, and
  status writes. Job addresses stored in the emulated ABI remain guest values.
* AJM sideband/stream/format/resample writes use native aliases for complete
  result buffers contained within one guest slot.
* AJM codec decoder input/output buffers are passed as native host aliases
  when they fit one guest slot. If a buffer crosses a slot boundary, input
  is staged into a contiguous native vector; output is staged and only
  decoder-produced bytes are copied back, with original guest return pointers
  and decoder result/status fields retained.

The patch does NOT skip shader compilation, ignore GPU fences, bypass FMOD
semaphores, fabricate game frames, swap in DroidDeck, or alter bundled Turnip.
Existing mesh/compute and AGC packet work remains intact.

## Verification

CI applies the patch with strict anchors to the exact vendored Kyty tree
before CMake; unexpected source changes fail the build instead of shipping
a partial patch. `tests/test_guest_hotpaths.py` verifies the installed
native-view code, while the existing `test_guest_memory.py` covers copy
behavior and slot crossings. Full Android compilation and ARM64 NovaFEX
regression tests must pass before a signed APK is published.

0.9.24 is a targeted performance attempt, not a verified FPS claim. Only
device logs can show whether the host-emulation delta declines and whether
game FPS rises after shader warmup.
