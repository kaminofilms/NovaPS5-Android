# Android measured guest-access fixes, 0.9.30

The 0.9.29 PPSA31162 log still reports 0.5 FPS, graphics pipeline creation of 106–432 ms, and repeated host-emulated accesses in AGC wait validation, predication and shader construction. GPL is active; this does not establish a performance gain.

This update resolves bounded native memory views before wait-packet validation, packet header predication, GPU query and boolean predicate reads, and shader header/user-data/register relocation. Shader relative offsets are added to original guest field addresses, never to native aliases. Published shader pointers and registered metadata retain guest addresses. Query reads remain volatile; unready queries retain existing suspend/non-wait behavior. No draw, wait, or query is fabricated or skipped.

The regression harness extracts the compiled production functions and runs them with PROT_NONE guest virtual addresses backed by separate native memory. It verifies 32/64-bit wait packets, malformed packets, range traversal, predication masks, shader-relative relocations, output guest addresses, shader register patching, and query readiness/condition behavior under UBSan. CI also runs existing renderer and ARM64 bridge regressions and compiles/packages the Android runtime.

This targets the remaining measured traps. It does not remove all cold pipeline compilation, prove an FPS improvement, or claim a permanent fix for all stalls. The emulator remains an Android ARM64 app with NovaFEX translating guest x86-64 code.
