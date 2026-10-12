# NovaPs5 — Android development alpha

NovaPs5 0.1.0-dev is a native Android foundation for researching an ARM64 port of KytyPS5. **This release does not boot or play PS5 games.** It is not a completed Kyty Android port. Importing firmware does not change that limitation.

## Included in this APK

- A PS5-inspired landscape home screen with NovaPs5 branding, a horizontal game row, local game artwork and Android folder selection.
- Game-library scanning for extracted folders containing `eboot.bin`; title metadata from `sce_sys/param.json`, covers from `icon0.png`, backgrounds from `pic1.png`. No game files are bundled.
- A native Android Vulkan triangle and swapchain test, with live presented-frame count and touch-responsive movement/color.
- Driver capability reporting: actual GPU and Vulkan version, integer shader support, rendering/synchronization features, subgroup properties and relevant extensions. The app uses the device's installed system Vulkan driver. No custom Adreno driver is included.
- A bounded integer-block x86-64-to-ARM64 JIT smoke test. `MOV`, register-only `ADD/SUB/XOR`, `NOP`, and a `RET` test boundary are supported. All memory operations, branches, stack-based guest returns, SIMD/AVX, imports and system calls are rejected. It is not a general x86 CPU emulator.
- PS5-layout touch controls: two analog sticks, D-pad, four face buttons, L1/R1/L2/R2, L3/R3, Options, Create, a touchpad and a Nova menu button. Create and Nova are host actions. Input is mapped into Kyty's 120-byte PadData layout for the test. No adaptive-trigger force feedback is simulated.
- Optional hardware-gamepad input, touch opacity and right-stick sensitivity settings.
- Firmware-file retention: import a PS5 SLB2 `.PUP` container, copy it to private app storage and compute SHA-256. This is **not** firmware decryption, installation or emulation. The official download opens in the user's browser. No Sony firmware is bundled.
- Exportable diagnostics. Imported games can have their ELF/SELF header inspected; execution is unavailable.

## Runtime port still required

Kyty's guest loader currently jumps to x86-64 entry points using an x86 System V ABI and stack. Its Xbyak patches and x86 signal handling cannot execute directly on ARM64. A complete CPU backend (for example, an appropriately adapted Box64/FEX integration), PS5 guest memory/TLS/signals, native-to-guest ABI bridges, relocations and module imports must be implemented and verified.

Kyty's RDNA-to-SPIR-V translator and Vulkan renderer are **not linked into this APK**. They need an Android platform integration and per-feature fallback work. The existing desktop renderer requires features including shaderInt64, dual-source blending and PS5 wave behavior that must be checked on the actual Adreno 840 driver. Android services, audio, module loading and executable scheduling also remain.

Proton targets Windows games on Linux. Its DirectX-to-Vulkan components do not provide PS5 services or replace the ARM64 CPU backend needed here.

## Build

Requirements: Python 3, Java 17 with `javac` or Eclipse ECJ, Android SDK platform 36, build tools 36.0.0, Android NDK 28.2.13676358 (r28c). No Gradle or external Android library dependencies are needed.

```bash
python3 build-apk.py \
  --sdk /absolute/path/android-sdk \
  --ndk /absolute/path/android-sdk/ndk/28.2.13676358 \
  --keystore /absolute/path/private/novaps5-development.keystore \
  --output /absolute/path/NovaPs5-0.1.0-dev-arm64.apk
```

With only a JRE, add `--ecj /absolute/path/ecj.jar`. The build accepts the official archive layouts `android-16` and `android-36` under the SDK path. ARM64 is the default; `--abi x86_64` is available for emulator UI testing, not for delivery to the Adreno device.

The development key is created if missing (alias `novaps5dev`, password `android`). Preserve this key privately for compatible app updates. It is a development identity, not a production signing arrangement. Signing keys are excluded from source and Git.

The library links with a 16 KB ELF page alignment; the APK targets API 36 and supports API 28+. The app is landscape. Device testing on Adreno 840 has not been performed in this workspace.

## Tests

```bash
python3 -m pip install unicorn
python3 tests/test_arm64.py
```

The tests compile the portable native code, check rejected instructions and malformed ELF bounds, assert the Kyty controller ABI offsets, and independently execute 160 translated integer blocks as ARM64 and x86-64 arithmetic using Unicorn. `RET` is the test-block boundary, not an implemented guest-stack return.

See `docs/VALIDATION.md` and the release manifest for the actual verification performed. No commercial-game compatibility claim follows from these checks.

## License and origin

GPL-2.0-only. KytyPS5 is based on the MIT-licensed original Kyty. Notices are preserved in `LICENSES/`; the included controller data layout is derived from the user's supplied KytyPS5 snapshot `df5b9b9`. The original snapshot is included under `vendor/kytyps5` as a reference, outside the APK build. See `docs/UPSTREAM.md` for provenance.

Upstream source: https://github.com/KytyPS5/KytyPS5

The source package is a self-contained new local NovaPs5 project. No GitHub repository has been published by this build.
