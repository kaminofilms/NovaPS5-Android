# NovaPs5 0.2.2 — experimental runtime preview

This APK adds a real launch path for the full KytyPS5 core through ARM64 Wine/FEX. **A PS5 game boot and 60 FPS gameplay have not been verified.** This is a device-test build, not a compatibility release.

## Install and test

Install the new APK over NovaPs5 0.1.0; the package ID and development signing certificate match. Existing game metadata remains in the same app preferences. Allow file access, select an extracted game folder on internal shared storage, and press **Play game**. The first launch installs about 1.4 GB of downloaded runtime archives and needs at least 6 GB free internally. No Steam account is required. Games on SD cards or cloud document providers are not supported by this first direct-path launch implementation.

The initial configuration uses a 1280×720 output, a 60 Hz presentation limit and conservative FEX memory-ordering settings. These are launch settings, not a measured frame rate. The runtime uses DroidDeck's Linux Vulkan/Turnip path; the home-screen GPU report measures the separate Android system Vulkan driver.

After a launch, **Diagnostics → Export** includes the latest session log. The complete log folder is `Download/NovaPs5/session-.../` (or private `files/logs` if shared storage is unwritable). Runtime logs identify whether Wine/FEX started Kyty, whether Kyty accepted the game, and where initialization failed.

## 0.2.2 direct Kyty session

NovaSessionActivity forces `mode=run`, `/opt/novaps5/launch.sh` and the selected game path; it refuses an unrelated running session. Both the installed root script and the APK script refreshed by SessionFiles reject any Steam or desktop route. The inherited loading title/hints now describe Kyty. The user screenshot's old “Steam is loading” text was hardcoded in the platform UI and did not prove that a Steam process started.

The session displays a persistent, tappable boot status with the bounded session log. The launcher records Wine errors, a timed Kyty CLI preflight, the exact game request and the final process status. It stops leftover services for Nova's private Wine prefix when Kyty exits. A compositor frame or CLI preflight does not establish PS5 game compatibility.

## 0.2.1 preparation crash fix

The 0.2.0 APK called a package-private installer constructor from another Java package, causing IllegalAccessError before downloading the runtime. The constructor is now public in the packaged platform. The verifier checks actual DEX class/method access flags, not only descriptors. Recoverable preparation/launch failures are displayed and saved before the session logger exists.

The original signing key is retained, so 0.2.1 installs over 0.2.0 and keeps the imported library. This repairs a confirmed startup integration bug; it does not verify a PS5 game boot. See docs/RECOVERY.md.

## Automatic builds

.github/workflows/build-novaps5-android.yml builds main, dev and manual runs, verifies dependencies and APK access/signing/structure, uploads artifacts, and publishes prereleases for dev-v* tags. CI uses a temporary development key; those CI APKs cannot update the privately signed APK delivered in chat. No private key is committed.

## What changed

- A Play action installs a pinned Linux runtime and ARM64 GE-Proton with its FEX integration, verifies SHA-256, and starts the full Kyty Windows/x86-64 executable in DroidDeck's Vulkan session.
- The core archive is included in the APK. Kyty supplies its PS5 loader, services, RDNA shader translation and Vulkan renderer; FEX translates the x86 code. A PC compatibility layer alone cannot supply the PS5 environment.
- The executable inspector reads embedded ELF headers in recognized SELF containers. A SELF header alone does not establish that the payload is encrypted. Kyty's full loader makes the actual launch decision; encrypted or otherwise unsupported payloads remain a possible failure.
- DroidDeck's session input bridge exposes the on-screen/hardware gamepad to Wine/SDL. Its face buttons are relabeled ×, ○, □ and △. Full DualSense touchpad, motion sensors, adaptive triggers and game-level input correctness are unverified.
- Runtime installation checks archive hashes and preserves relative Proton symlinks. Large boot-log reads are bounded.
- Native Android Vulkan/control diagnostics, folder metadata and optional firmware-file retention remain available. Retaining a PUP is not firmware installation or decryption.

## Build the delivered APK

Requirements: Python 3, Java 17 JDK, Android SDK platform 36/build-tools 36.0.0, Android NDK r28c, Linux x86-64 build host, and the existing development signing key.

```bash
python3 build-runtime-apk.py \
  --sdk /absolute/path/android-sdk \
  --ndk /absolute/path/android-sdk/ndk/28.2.13676358 \
  --jdk /absolute/path/jdk-17 \
  --keystore /absolute/path/novaps5-development.keystore \
  --output /absolute/path/NovaPs5-0.2.2-runtime-arm64.apk
```

The script compiles Nova's Java/native code and combines it with the SHA-256-pinned official DroidDeck 0.1.7 Android platform. Matching upstream source is in `vendor/droiddeck-0.1.7` at commit `d7cadd05d6e69b61b043f083b4bb408ef59967d1`. Compile-only backend ABI declarations are never packaged. Optional `--base-apk`, `--apktool` and `--compress-jar` arguments reuse already downloaded, verified dependencies.

The delivered APK targets API 28 because the Linux runtime executes binaries from app storage. It supports ARM64 Android API 28+; the earlier diagnostic-only APK targeted API 36. Nova's native diagnostics and the principal session/compositor libraries use 16 KB ELF alignment, but inherited PulseAudio-related binaries use 4 KB alignment. Complete 16 KB device compatibility is not established.

`droid-runtime/` also preserves a newer source fork and Nova integrations for further platform development. Its full Gradle build was blocked by dependency retrieval in this workspace and is not the platform binary used for this release. The pinned-platform build above is the checked build path. `build-apk.py` still builds the historical diagnostic-only 0.1 application.

Signing: alias `novaps5dev`, development password `android`. Preserve the original private key for future app updates. No private signing key is included in this source package.

## Verification and limits

See `docs/VALIDATION.md`, `docs/PORTING.md` and `release.json`. Packaging, checksums, direct-route/failure regression tests, the native inspector and signature were checked. The host x86 Kyty CLI and ARM64 Wine version command ran; the complete Wine/FEX → Kyty → PS5 game path did not run successfully here. The user's latest screenshots show the compatibility session/loading surface and controls with 0 FPS; there is no demonstrated PS5 game frame.

There is no confirmed EverForward compatibility result, measured gameplay FPS, firmware boot, native ARM64 Kyty port or automatic payload decryption. No game files or Sony firmware are included. No GitHub repository has been published.

## Licences and source

The DroidDeck-derived platform and Nova runtime-module code are GPL-3.0. Kyty's GPL-2.0-only Windows core runs as a separate process and its source is preserved in `vendor/kytyps5`; no Kyty GPL-2-only controller header is linked into the new Android runtime libraries. The historical 0.1 application remains GPL-2.0-only. Third-party component licences remain in their original directories and the packaged core archive. See `docs/UPSTREAM.md` and `droid-runtime/NOVA-LICENSES.md`.
