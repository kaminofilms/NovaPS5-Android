# Nova Android homebrew boot API patch

This is a development build for the ccleste PPSA59322 startup failures shown in
the supplied PC log. It uses the complete KytyPS5 core at
`df5b9b92be7dfd463b47756b707d6d356a9f0550` with the reviewed source overlay.

Changes:

- Resolve the homebrew's `pipe`, `dup2` and `sceKernelDebugOutText` imports.
- Implement a bounded pipe with blocking I/O, atomic writes up to 4096 bytes,
  nonblocking flags, EOF, EPIPE, descriptor duplication and close behavior.
- Route descriptor 2 writes through its redirected pipe, and preserve duplicates
  when the original write descriptor closes.
- Flush the SDK's FreeBSD output buffers through their guest write callbacks,
  including partial writes and stream error flags. Other guest stdio ABIs use
  the supplied guest libc export. Native stdout/stderr use the host CRT.
  Resolve the SDK's `__stdinp`, `__stdoutp`, and `__stderrp` objects with guest ABI
  stream layouts and real descriptor callbacks. `fflush(NULL)` also flushes
  those SDK output streams before invoking the host and guest flush-all functions.
  An unavailable guest implementation returns ENOSYS instead of crashing or
  passing a guest FILE object to the Windows CRT.
- Reject seeking and truncation on pipe descriptors; report FIFO metadata.

The deliverable is the Nova Android APK. The workflow builds the x86-64 Kyty
core internally because the current Android port executes that core through
ARM64 Wine/FEX. The resulting executable is packaged into the APK with the
Wine guest address-space bridge; no separate PC release is produced.

Keep the console output from the first new failure. Passing API tests is not
proof that the game renders or is playable. A compositor or emulator splash
frame is not a game boot. General file/socket `dup2` remains unsupported and
returns ENOSYS; this patch implements the pipe path used at ccleste startup.

The supplied homebrew has readable, uncompressed SELF segments. Its packaged
fflush export is a return-only stub, so recognized SDK output buffers need the
callback adapter. Flush-all behavior for additional streams managed by a libc
that only supplies such a stub is still limited by that libc's implementation.
This build does not decrypt encrypted retail packages or
SELF files. Use legally obtained executable data that is already decrypted.

Host API validation has no Vulkan/GPU requirement. Actual game boot still needs
the Vulkan capabilities required by the full core. Android Wine/FEX guest
address-space reservation is a separate blocker and is not solved by the guest API patch alone. No Steam integration is part of this change.
