# 0990 local full-core link — APK BLOCKED

On October 26, 2026 the recovered corresponding-source core with overlays 0968 through 0989 compiled and linked successfully using Android NDK r29, Clang 21, API 33. The resumed Ninja build exited 0 and produced ELF64 AArch64 libmain.so.

SHA-256 libmain.so: e0294aef23678fcccf9253c6f029b211dfb24c5a1cfd2fdb0bbc3540e0b7ef92
SHA-256 rebuilt current-wrapper libnovafex.so: 973ad0ae0858bdde2724043dcae597c7c1a89b9788fb370ebdf9d469c10a9780

This closes the local full Kyty compile/link check only. The link used the recovered 0967 AnyPS5 bridge/renderer dependency, relocated runner paths for this workspace, the recovered FFmpeg static libraries, and the current rebuilt NovaFEX wrapper. It is not validation of a fully rebuilt current AnyPS5 renderer. A complete dynamic import/provider audit and current frontend/package/signature verification remain required.

The older signing-key blocker was incorrect: tools/ci/novaps5-ci-test.keystore is present in this branch and opens with alias novaps5dev. Its certificate must still be compared against the installed/user-provided APK before packaging.

All implementation and device gates from 0989 remain unresolved: writable GPU resource ownership and safe DMA scheduling, real image feedback hazards, GPU/lifetime binding-cache validation, exact flip/EOP freeze tracing, live CRI attribution, ADPF/worker lifecycle and sustained thermal/FPS measurements. No APK was packaged, no Actions started and no device FPS claimed.
