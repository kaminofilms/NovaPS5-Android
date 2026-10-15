# NovaPS5 0.9.23 — ARM64 LD1/ST1 guest fault recovery

## Device regression

NovaPS5 0.9.22 on NX809J (Android 16, SM8850, Turnip A8xx) faulted in host
AArch64 code: signal 11, host PC 0x74800d1ab0, guest-address fault
0x8680091fe0, instruction 0x4c40a021, ESR 0x92000004.

Instruction 0x4c40a021 is `LD1 {v1.16b, v2.16b}, [x1]` (two consecutive
16-byte SIMD vectors). The NovaFEX guest-high-address signal decoder handled
interleaved two-register `LD2/ST2` but not the contiguous `LD1/ST1` family.
When Bionic or native HLE hit a high guest pointer with this instruction,
the handler returned false and the process crashed.

## Production correction

Recognize the valid two-register LD1/ST1 contiguous encodings alongside
the existing LD2/ST2 family while retaining a distinct register-layout
selection. Preserve source and destination register wrap (v31 -> v0),
64-bit guest-base addressing, immediate or register post-index writeback,
vector upper-half clearing on 8-byte loads, and rejection of invalid
ST2 1D encodings.

Before mutating load destinations or store targets, translate and preflight
every byte. This handles crossing the 1 GiB guest-VA slots whose native
backing allocations are not adjacent; missing second-slot backing causes
rejection without modifying the saved vector context, base, or PC.

This patch is NOT a shader-feature bypass. The 0.9.17–0.9.22 mesh/compute
adaptations, AnyPS5 integration, AGC packet builders, and native Kyty/FEX
architecture remain present.

## Coverage

`tests/test_structured_simd.py` executes the production decoder with
synthetic ARM64 contexts and protected mappings. The test includes:
- Exact crashing instruction `0x4c40a021` with full 32-byte read.
- LD1/ST1 8/16-byte vector widths and all element-size field encodings.
- No, immediate, and register post-index writeback.
- Register-list wraparound `v31,v0` and two nonadjacent backing slots.
- Rejection without vector-state mutation for unmapped second slot.

`native/novafex/test/structured_simd.inc` also exercises physical AArch64
LD1/ST1 instructions and kernel sigreturn on the native arm64 CI runner.

Tests and CI verify memory access and build correctness; only a new phone
run can prove that PPSA31162 advances beyond this fault. Shader correctness,
rendered frames, and frame rate remain device-test goals.
