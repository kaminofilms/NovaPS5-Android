# NovaPS5 0.9.39-android — APK checkpoint

Version code: 93. Package: com.kaminofilms.novaps5.
APK SHA-256: b8abdb643c02eb703d183b92302145cc7b0cfc9b236615b331233fea32a80f3a.
Signing certificate SHA-256: 21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0.
Certificate matches the previously signed 0.9.38 APK.

## Included

- Android-supported-subset PKG/PFS importer, JNI bridge and library insertion.
- Stream plain files; bounded compressed data, staging and partial-file refusal.
- Installer's private static C++ runtime hidden from other native libraries.
- KytyPS5 FP16 signaling-NaN quiet-bit correction.
- NovaFEX unchanged byte-for-byte from the successful 0.9.38 artifact.

## Build provenance

The runtime was rebuilt from the exact patched source archive in successful run
38944677621 (f2934bcbfee736c2bfc97c9a3d5a05e6e183627a), plus the FP16 patch.
Compiler/toolchain: NDK r30, revision 30.0.16248370, Clang 21.0.0, Android API 33,
matching the original successful build log. CMake/Ninja, static libc++, 16 KiB
ELF alignment. glslang 16.6.0 regenerated the 13 tiler/fault shaders.
The initial r28c core attempt failed due to missing jthread/stop_token support;
it was not packaged. No thread or synchronization behavior was changed to bypass it.

## Checks completed

- Full ARM64 Kyty shared library and native PKG installer compilation.
- Full Java frontend compilation with actual GameActivity and SDL classes; D8.
- Package, version, certificate, ARM64-only and native dependency checks.
- All native LOAD alignment checks and installer JNI/export isolation checks.
- Bundled Adreno driver checksum and packaging check.
- PKG installer ASan/UBSan regressions with successful synthetic ELF installation,
  malformed/truncated payload rejection and nonempty-destination protection.
- 131,072-case execution of production FP16 classification code; original
  classification fails the negative control while the port passes.
- GPU completion, EOP label lookup/publication, PM4 fetch, shader device-profile
  and RELEASE_MEM dispatch/batching host regressions.
- GPU-fence and storage-backed atomic SPIR-V modules validated.
- All 13 generated tiler/fault modules validate for Vulkan 1.3.

Local Vulkan driver execution and phone game testing were not performed.

## Important scope

This APK is NOT a complete AnyPS5 backend port. AnyPS5's public 1166/1166 shader
instruction metric counts decoder recognition of the AMD RDNA instruction list,
not full rendering correctness or guaranteed playable performance. No new
AnyPS5 decoder/renderer replacement is enabled in this build. Nova's earlier
AnyPS5-derived integrations remain intact.

Encrypted/finalized-image PKGs, whole-image PFSC and compressed inode/stream data
over 64 MiB are unsupported. This is not a PKG patch/DLC merger. Supported
installation and ELF validation do not prove game compatibility. No gameplay
FPS improvement is claimed without same-device, same-scene owner logs.
