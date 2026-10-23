# Overdrive in Nova's game library — experimental PS5 guest

Requested behavior: extract a PS5 application folder into the user's games directory, scan it in Nova, and launch it through Kyty/NovaFEX like a game. This work does not add a replacement Android store screen.

## Input and output

Upstream Overdrive 1.0.9, exact uploaded revision `ce407214eee01df732d859434085ebea1399ef70`. The build fetches that public commit; dependencies remain pinned by its lock file.

The experimental workflow builds `Overdrive-Nova-PS5-guest-experimental.zip` with `PPSA99058/eboot.bin` (the plaintext linked x86-64 PS5 ELF), `sce_sys/param.json`, artwork, fonts, bundles, notices and resources. Extract the folder under a game-library root and scan that root using Nova. Keep the entire folder together.

The expected title is Overdrive, `PPSA99058`. Naming an ELF `eboot.bin` matches Nova's existing scanner; no new Android frontend or container installer is involved. Nova 0.9.65 is a separate APK build and does not itself include this guest.

## Guest profile changes

- Replace Lapy/elevation requests with a real read/write proof of Nova's already mapped `/app0`, `/download0`, and `/temp0` sandbox directories. Failure keeps the capability unavailable.
- Resolve app API paths `/data` into this title's `/download0`, and `/cache0` into its `.cache`. Refuse parent traversal, unmapped paths, and truncated output. This adapter is not a kernel-wide filesystem security boundary; guest POSIX access still depends on Nova's VFS.
- Bundle the builder's public CA certificates and use `/app0/nova/ca-bundle.pem`. Keep curl/OpenSSL certificate and hostname verification. Record the certificate bundle SHA-256 in `nova/guest-profile.json`.
- Do not compile or ship the filesystem elevation helper. Keep the pinned network compatibility code, using its actual dependency variable when elevation is disabled.
- Return an explicit unsupported error for console ELF-loader requests. No launch of PKG installation, browser-capture or extraction worker payloads on Android localhost.
- Disable automatic self-update checks that could replace the guest-specific executable with the stock console image.

All React components, catalog handling, software rendering, PS5 OpenGL presentation, controller code and most public PS5 imports remain upstream. Their presence is not evidence of successful emulation.

## Validation and remaining work

Local C++20 tests exercise the actual replacement filesystem implementation: missing-mount failure, successful file read/write proof, cleanup, aliases, boundary/traversal rejection, and explicit payload-service failure. Python tests also apply the actual source transformations to the uploaded revision and reject repeated application.

The PS5 build job is an experimental compilation gate. Compilation does **not** establish that Nova renders the UI or that browsing, downloading or installation works. There is no owner-device boot result for this exact guest. `runtime_tested` remains false.

In particular, HLE coverage for the exact guest's imports, PS5 OpenGL/AGC presentation, disk usage/mount enumeration, networking and certificate loading must be measured on Nova. ShadowMount+ is not running in Nova: images are not automatically mounted or installed. PKG promotion, browser-host capture, external payload workers and automatic image self-replacement are unavailable in this profile. Downloading a file does not make that game compatible with the emulator.

## How the linked projects help

- MyLuxy/overdrive: the actual app source, UI, catalog, queues and reproducible PS5 builder.
- half144/ps5-react: QuickJS/Embedded React runtime and documented native API. It is distinct from Sony RNPS and the original dashboard.
- drakmor/ShadowMountPlus: useful reference for image types and install/mount API behavior; its console kernel mounter is not an Android implementation.
- EchoStretch/kstuff-lite: console loader/kernel behavior reference; firmware-specific payloads cannot be inserted into Nova as an ARM64 library.
- darkxex/ps5-homebrew-catalog: native-app metadata, developer release URLs and hashes; not a runtime or game compatibility list.

Preserve upstream licenses, `NOTICE`, attribution terms and third-party notices. CI emits the modified source and dependency source/download archives alongside the guest build. No Sony firmware files or theme dumps are incorporated.
