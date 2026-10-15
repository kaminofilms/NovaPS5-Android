# NovaPS5 0.9.25 — AGC command-buffer host-view performance

0.9.24 device log for PPSA31162, nubia NX809J SM8850 Android 16,
Turnip Mesa v26.3.0-20261012-A8xx, shows slow game execution even though
Kyty boots, shaders continue compiling, and AAudio/FM0D run.

The freeze report at 555 frames showed 602,754 emulated host memory accesses.
Dominant named sites shifted from pixel shader and Opus in 0.9.23 to:
- `Gen5::AgcSetCxRegIndirectPatchAddRegisters` (three adjacent host PCs);
- `Gen5::CommandBuffer::ReserveDW` and `AllocateDW`;
- `Gen5::AgcUnknownIkfdtRIqCE`.

The new native Android Kyty patch runs AFTER all pre-existing packet/Opus
patches and BEFORE compilation. It applies bounded host pointer views to:
- CommandBuffer `GetAvailableSizeDW`, grow callback fields and `AllocateDW`
  cursor reads/writes; callback still receives the *guest* CommandBuffer
  pointer and returns a guest packet address.
- Five-DWORD indirect Cx/Sh/Uc register packet validation, address and count
  updates; the encoded GPU buffer address continues to be guest virtual.
- Four-DWORD indirect-buffer target patching; no packet flags or arithmetic
  are changed.

No GPU fences, release writes or waiting rules are skipped or replaced.
For a cross-slot structure the native view is not used: existing guest
fallback remains. `tests/test_agc_cb_hostviews.py` compiles the actual
patched helpers into a host harness, testing synthetic nonidentity guest
mapping, cursor advance, grow callbacks, packet opcode validation, and
14-bit register count rollover. CI is configured to fail rather than publish
if an upstream source anchor or behavioral test no longer matches.

The AAudio error -899 (device disconnected) is independently visible and
may contribute to stalls. Its root cause is not established by this log.
Remaining system-side bottlenecks include slow first-use shader compilation,
guest CPU translation, resource constraints, GPU queue blocking, and
frame-flip synchronization. FPS increase is NOT assumed without a new device
measurement of the same game scene and comparable elapsed interval.
