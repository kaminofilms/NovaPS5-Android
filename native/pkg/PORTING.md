# Android PKG importer: experimental supported subset

Source: Coder787-source/KytyPlus dc5f5d98285e3a29302dd232e18a433fb7cfdf83.
GPL-2.0; full license retained in LICENSE. Nova-specific adaptations are in the
accompanying build-source archive.

The Java importer, JNI library and build wiring are present. Add game offers
folder import or PKG installation. Imported game data is held under the app's
external-files games directory. Existing folders and ELF launching remain.

Supported subset: decrypted, ordinary PKG containers containing a supported
plaintext PFS tree and a decrypted x86-64 ELF eboot.bin. Finalized-image layouts,
whole-image PFSC and encryption are rejected. Compressed inodes/streams larger
than 64 MiB are rejected explicitly. This is not universal PS5 PKG compatibility.
PKG patch/DLC merging is not implemented; this importer must not be described as
an update manager. A package reaching the library does not prove the game boots.

Safety and resource behavior:
- Plain files are streamed by filesystem block rather than buffered in full.
- Bounded compressed streams, directory walks, names and block maps.
- Truncated payloads and incomplete block chains fail installation.
- Temporary filesystem image removed after successful validation.
- No raw-body or heuristic file-carving success path.
- Validate extracted file counts, paths, exact sizes and ELF class/machine.
- Fresh staging directory, source FD held open, same-directory rename publication.
- Failed staging removed; no overwrite of existing installations, saves or caches.
- Only stock zlib backend registered. No desktop plugin DLL loading.

Local checks: native parser/installer ASan+UBSan regressions; full native JNI
library compiled for the host using OpenJDK headers; edited Java sources compiled
against Android API 36 with the unchanged game-activity declaration stubbed.
LeakSanitizer disabled locally because runner process inspection is unavailable.
CMake + NDK r28c Android ARM64/API 33 build also passes locally. ELF checks
confirm AArch64, the JNI export, Android-only shared dependencies and 16 KiB
LOAD alignment. The dedicated CI job failed before any steps; no CI pass claimed.
No Android runtime, real PKG or game FPS result is implied by host checks.

Remaining: full APK validation, phone import test, full-game runtime validation,
streaming large PFSC inodes and audited finalized-image support, explicit update
package identification/merge, cancellation and interrupted-install recovery.
