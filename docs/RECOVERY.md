# Nova PS5 recovery checkpoint

Current device update: NovaPs5 0.2.2-runtime, versionCode 4, ARM64, package com.kaminofilms.novaps5. It preserves the original development certificate and installed game preferences.

## Direct Kyty route and boot evidence

The latest user screenshots show a hardcoded upstream “Steam is loading” overlay and a black session surface with 0 FPS. The original launch extras already selected run mode; neither screenshot is proof that Steam actually started. The new NovaSessionActivity validates the game route, supplies explicit run/script/game extras, and shows guest boot stages and a tappable log. The guarded compositor script refuses Steam/desktop requests. Guarding only the installed root is insufficient: SessionFiles stages its APK asset on every launch, so build-runtime-apk.py guards that copy too.

launch.sh now records Wine errors and phase/exit markers, bounds the CLI preflight to 180 seconds and stops this private Wine prefix's remaining services on exit. Five regression cases check route rejection, exact arguments with spaces, preflight failure, game exit propagation and missing game input using a fake Wine process. They do not validate Wine/FEX or a PS5 game.

## Immediate crash repaired

The 0.2.0 platform's LinuxRuntimeInstaller.Release constructor had package-private access (DEX flags 0x10000). Nova called it from another Java package. This is an IllegalAccessError before the installer starts, which escaped the Exception-only catch and could terminate the app.

The pinned-platform patch changes the constructor to public (flags 0x10001). The newer source fork already exposes it publicly. The artifact verifier now resolves the platform methods referenced by Nova and checks their class/method access flags, in addition to descriptors. Engine preparation and Activity launch catch recoverable Throwable failures; fatal VM errors are rethrown. Pre-session failures are saved in private logs/nova-engine.log and included in Diagnostics export.

Regression evidence:

```bash
python3 tests/verify_runtime_apk.py /path/NovaPs5-0.2.0-runtime-arm64.apk --expect-inaccessible
python3 tests/verify_runtime_apk.py /path/NovaPs5-0.2.1-runtime-arm64.apk --sdk /path/android-sdk
```

## Continue from this project

- Build the current package with build-runtime-apk.py, official SDK 36/build-tools 36.0.0/NDK 28.2.13676358 and Java 17. No Gradle dependency mirror is needed for this pinned-platform build path.
- The core archive may be fetched and SHA-256-verified automatically if absent from the source tree.
- The automatic workflow is .github/workflows/build-novaps5-android.yml. It builds main/dev and manual runs, retains artifacts, and publishes prereleases for dev-v* tags. CMake 3.22.1 is installed with the toolchain; the checked package script compiles Nova's C++ directly with NDK clang.
- CI signing is temporary. Preserve the private development key separately for updates to the user's current installation; never commit it.
- The user reports that Dead Cells runs on desktop Kyty. The latest Android screenshots reach a compatibility session surface but show 0 FPS. There is no confirmed Android Wine/FEX/Kyty game boot yet.
- Next on-device evidence is successful engine installation, Kyty --help preflight, then the game's session.log. A 60 Hz presentation target is not a measured 60 FPS game result.
- GitHub publication must be verified before claiming that a remote repository, branch, workflow run or release exists. The requested destination is private kaminofilms/NovaPS5-Android, main and dev.
