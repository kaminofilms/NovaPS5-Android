# Component provenance

## KytyPS5

https://github.com/KytyPS5/KytyPS5 — supplied snapshot `df5b9b9`, dated 2026-10-12. GPL-2.0-only with preserved third-party notices and original Kyty MIT notice. The unmodified supplied source is under `vendor/kytyps5`; empty submodule directories still require their upstream dependencies for a fresh desktop build.

The full official Windows/x64 core archive is packaged in `droid-runtime/app/src/main/assets/engine/kyty-windows-df5b9b9.zip`. It includes the emulator, libraries, assets and its original licences. URL and SHA-256 are recorded in `release.json`. It executes as a separate process; it is not linked into the GPL-3 Android module.

## DroidDeck platform

https://github.com/The412Banner/DroidDeck — official Android release 0.1.7, source tag resolving to `d7cadd05d6e69b61b043f083b4bb408ef59967d1`. Its verified APK supplies the compiled Android session, compositor, input/audio support and bundled libraries. Matching source is preserved under `vendor/droiddeck-0.1.7`. GPL-3.0 and retained third-party notices. `build-runtime-apk.py` documents and applies the package/launcher, action-name, gamepad-label, log-folder and FPS-limit modifications; it compiles the new Nova frontend and diagnostics separately.

`droid-runtime` contains a newer DroidDeck source fork with the same Nova integration for subsequent full-source development. It is not represented as the exact upstream version of the reused platform binary.

## Downloaded runtime components

The pinned Linux root is `linuxfs-r9` from The412Banner/winlator-contents. The pinned ARM64 Wine/FEX distribution is GE-Proton11-7-aarch64 from GloriousEggroll/proton-ge-custom. Exact URLs, archive sizes and SHA-256 are in `release.json` and RuntimeEngine.java. These archives are installed from their official release hosts on the user's first Play action; they are not part of the APK or source ZIP. Wine/Proton, FEX, Mesa and other included components retain their respective licences. No Valve Steam client, Sony firmware or games are bundled.

Apktool 3.0.3 and Commons Compress 1.27.1 are pinned build dependencies. Commons Compress is already present in the platform APK; the build-time JAR is used only on the compilation classpath.
