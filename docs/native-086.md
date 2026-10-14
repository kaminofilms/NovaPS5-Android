# Nova PS5 0.8.6

- Fixed direct maps (`sceKernelMapDirectMemory` / `MapNamedDirectMemory` with MAP_FIXED 0x10) honour the requested
  16 KiB-aligned guest address for every title; the alignment argument only constrains allocator-chosen
  addresses. Fixes the ccleste (PPSA59322) startup refusal `MapDirect failed 0x80020016 addr=0x400004000
  len=0x200000 flags=0x10`. Null, sub-page and wrapping addresses are still refused. Replaces 0.8.5's
  per-title `NOVA_FIXED_DIRECT_PAGE_ALIGNMENT` profile (launcher no longer sets it). Regression in
  `tests/test_native_startup.py`, run by the CI Kyty build against the patched sources.
- The equivalent edit in `vendor/kytyps5` (c9125e6) is not what CI compiles; CI applies
  `patches/kyty-nova-arm64.patch`, which now carries it.
- Not in this build: a translated/sparse guest address space for Unreal's 512 GiB libc reservation
  (Luna Abyss). Still the shrink-reservation + NovaHeap approach from 0.8.2-0.8.5.
- Device status unverified: ccleste, Luna Abyss, EverForward; Dead Cells must be re-checked for regressions.
