# NovaPs5 0.1.0-dev validation

## Passed

- Compiled portable native tests with C++17, `-Wall -Wextra -Werror`.
- Verified 160 supported integer blocks by independently executing emitted ARM64 instructions and corresponding x86-64 arithmetic using Unicorn. The x86 execution stops at the RET test boundary; guest stack returns are not implemented.
- Tested rejected system calls, memory addressing, branches, invalid opcode groups, truncated operands, invalid prefixes and missing/trailing RET data.
- Tested malformed/truncated ELF recognition and x86-64 machine type handling; executable inspection does not load or execute a game.
- Asserted Kyty PadData ABI size (120 bytes), touch-data offset (52), timestamp offset (80).
- Compiled the native Vulkan/JNI code with Android NDK r28c for ARM64, API 28.
- Compiled both shaders with the NDK's glslc, targeting Vulkan 1.0/SPIR-V.
- Compiled all native Android Java classes, generated DEX, linked Android API 36 resources and packaged the APK.
- Verified the APK's v3 signature using apksigner and its manifest/package metadata using aapt.
- Verified zip alignment and 16 KB ELF LOAD-segment alignment.
- Inspected native dependencies: only standard Android libraries are required; the C++ runtime is statically linked.
- The supplied official Sony firmware URL responded to HEAD with HTTP 200; the file length was 1,261,408,256 bytes. A 64-byte ranged read returned HTTP 206 and a PS5 SLB2 container header. The full firmware was not downloaded or redistributed.

## Not verified

- Physical Android/Adreno 840 operation, driver-specific Vulkan capabilities and actual ARM64 JIT execution on the user's phone.
- On-device touch hit targets, file-picker flows, controller handling or native Vulkan presentation.
- Android emulator UI verification: a separate x86-64 build compiled and signed, but the test emulator exited with signal 11 before application launch. This environment has no hardware virtualization; the forced software-emulation attempt could not complete. No successful Android runtime test is claimed.
- PS5 games, firmware installation, full Kyty runtime integration, rendering compatibility or frame rate. Those features are not present in this APK.

## Release identity

Package: com.kaminofilms.novaps5
Label: NovaPs5
Version: 0.1.0-dev / versionCode 1
ABI: arm64-v8a
Minimum Android API: 28
Target Android API: 36
Development signing certificate SHA-256:
118656f8a3e3f5a2633b8cf49de6494ccb8eefcd30f2df662c6bdbc4f1a7b829

The release manifest records hashes for the APK and supplied upstream archive. This document does not assert commercial-game boot support.
