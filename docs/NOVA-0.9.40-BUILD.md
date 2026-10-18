# NovaPS5 0.9.40-android

VersionCode: 94. Native Android ARM64. AnyPS5 source: 9caecfd2d5a822be9daf84c69c7c33c7fafe52b9.

The default graphics backend now uses AnyPS5's complete AGC Vulkan renderer, full shader compiler/optimizer, graphics SDK API and native Android-adapted VideoOut. It is integrated with NovaFEX call gates, translated guest memory, actual allocation-registry GPU leases, Nova kernel events and SDL3/Android window lifetime. Nova OS services, audio, input, PKG importer and CPU translation remain the Nova implementations. This is a graphics-backend fusion, not a replacement of every Nova subsystem with AnyPS5's desktop runtime.

All 10 host integration tests passed, including software-Vulkan compute, buffer formats, buffer atomics, vertex draw, mapped memory and real queue waits/cancellation. Cross-slot command spans and remote guest labels are exercised. GPU waits are not skipped or completed artificially. Android renderer and core link with NDK r30, shared libc++ and 16 KiB alignment. Final APK and bundled Turnip checks pass.

APK SHA-256: ad3533f382dcb65bfee03b44a6284355f754292ba7e770c46dd5b43f04960136

Signing certificate SHA-256: 21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0 (same as existing Nova CI update builds).

No connected Android device was available. Game boot, Ever Forward performance and Turnip rendering correctness remain unverified on hardware. The owner's previous build measured 3.6–4.7 game FPS; no 60 FPS claim is made for this APK. Existing saves/caches are not removed; AnyPS5 shader cache has its own directory.
