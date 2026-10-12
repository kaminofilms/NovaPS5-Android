# NovaPs5 0.2.0-runtime validation

## Passed

- Verified the official Kyty Windows release, DroidDeck 0.1.7 APK, its matching source-tag archive, Linux root and ARM64 GE-Proton archives by SHA-256. Pins are recorded in release.json.
- Ran the full Linux/x86-64 Kyty `--help` CLI on the build host.
- Ran the ARM64 Wine `--version` command using a userspace ARM interpreter; returned Wine 11.0 (Staging). This checks the binary/dependencies only, not Wine/FEX game execution.
- Compiled Nova Java, desugared to DEX and compiled the native Android diagnostic library for ARM64/API 28. No GPL-2-only Kyty controller header is linked into this new library.
- Built the APK through the included pinned-platform build script. Matched all four compile-only backend class/method declarations against the original platform's real DEX. Confirmed the added DEX defines only Nova classes, with no backend stubs packaged.
- Tested flat ELF64 and both recognized SELF magics with readable embedded ELF headers, malformed segment counts, truncation and wrong machine types. Passed the portable C++ inspector checks.
- Verified the packaged Kyty archive hash, launcher shell syntax, conservative FEX settings, unique ZIP entry names and ARM64 native ELF machine type.
- Audited the actual ARM64 Proton tar: 9,578 entries, 1,884 safe relative symlinks, no hard links or unsupported entry types. All members fit the installation root.
- Verified versionCode 2, NovaPs5 label, com.kaminofilms.novaps5 launcher/package, ARM64 ABI, minimum API 28 and target API 28.
- Verified APK v3 signature and same certificate as 0.1: 118656f8a3e3f5a2633b8cf49de6494ccb8eefcd30f2df662c6bdbc4f1a7b829. Checked ZIP alignment. Nova diagnostics and principal compositor/session libraries use 16 KB LOAD alignment; inherited PulseAudio-related binaries use 4 KB.
- The user supplied screenshots of 0.1 importing EverForward, identifying Adreno 840 / system Vulkan 1.4.295 and displaying its metadata. Those screenshots validate the earlier UI/import foundation.

## Not verified

- Installation of this 0.2 APK, runtime extraction, storage permissions and first-launch behavior on the user's phone.
- End-to-end ARM64 Wine/FEX → Windows Kyty execution. The attempted host-side userspace-interpreter run did not complete; its nested native child execution was unavailable. No successful ARM device runtime test is claimed.
- EverForward or any PS5 game boot, complete SELF payload support, PS5 services, guest signals/TLS, shaders, audio, input or saves through the translated process.
- Sustained gameplay FPS or complete 16 KB Android compatibility.
- A native ARM64 Kyty build. This release translates the existing x86 core instead.
- The newer droid-runtime fork's full Gradle build; dependency retrieval blocked completion. The delivered APK uses the separately checked pinned-platform build path.

## Next evidence

Install the update, allow file access, press Play, and export Diagnostics after the attempt. In session.log, NOVA_CORE/NOVA_TARGET mark the launch script, the Kyty help output marks Wine/FEX preflight success, and NOVA_LAUNCH marks the actual game request. An absence of these markers or a subsequent error identifies the next layer to fix. A valid 60 Hz configuration is not a 60 FPS gameplay result.

Historical 0.1 validation is preserved under docs/history.
