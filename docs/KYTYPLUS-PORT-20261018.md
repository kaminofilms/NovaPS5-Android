# KytyPlus import audit — 2026-10-18

Nova baseline: 99b5d5ecde8d40169a548a70e0623fa414382329 (0.9.38 documentation head).
Compiled Kyty pin: df5b9b92be7dfd463b47756b707d6d356a9f0550.
KytyPlus main inspected: dc5f5d98285e3a29302dd232e18a433fb7cfdf83.
Latest published release inspected: v4.3, published 2026-10-14.
Comparison: 325 src files, 58,635 insertions / 8,820 deletions.
This is a source inventory, not an assertion that every changed function has been reviewed.

## Findings

- KytyPlus explicitly inherits Unreal/Unity boot capability from upstream KytyPS5.
  There is no single Unreal/Unity enable flag. Compatibility is title-specific.
- The SPIR-V 1.5 / core ShaderLayer and ShaderViewportIndex selection highlighted
  in v4.3 already exists in Nova's pinned upstream emitter. Do not re-import it.
- Nova already has Android-specific persistent shader/pipeline cache changes and
  large Unreal shader-archive handling. Preserve those and compare cache formats
  before importing another implementation.
- KytyPlus advertises FSR EASU/RCAS, present/aspect controls, adaptive texture LOD
  and UMA detection. Its README calls many game-level performance benefits
  unvalidated; internal-resolution reduction and staging bypass are not fully
  wired. These are not demonstrated fixes for Nova's measured readback/EOP stalls.
- Desktop x86 instruction handlers do not replace NovaFEX's Android ARM64
  translation and guest-memory integration.
- Desktop Qt launchers, shadPS4 subprocess/window embedding and Windows path fixes
  are not direct Android features.
- Significant new HLE, loader, resource tracking and shader paths need individual
  review and targeted tests. Bulk copying would bypass Nova's translated-pointer,
  GPU completion, shader capability and device-specific behavior.
- No real-game Android result or FPS improvement is established by this import.

## Completed first source port

native/pkg is an isolated, emulator-independent C++20 PKG/PFS module with upstream
license and provenance. The host regression executable builds and passes with
ASan/UBSan (LeakSanitizer unavailable in this runner).
The invalid-filesystem negative control fails against the original upstream
raw-body success behavior and passes with Nova's stricter refusal.

The port corrects a dangling stack pointer in recovery header inspection and
does not treat carved files or raw body images as complete game installations.
It is deliberately not linked or exposed in the production APK.
See native/pkg/PORTING.md for remaining installer gates.

## Outstanding work

1. Installer: bounded streaming extraction, complete-write validation, scanner
   audit, private staging/atomic publish, SAF importer and Android library entries.
2. Shader/loader/HLE: compare individual compatible changes against the fully
   staged Android source, not just the unpatched Kyty pin.
3. Presentation/FSR: native Android surface integration and capability checks;
   keep currently unavailable settings disabled until there is an actual path.
4. Performance: measure readback/EOP changes using Ever Forward, Super Meat Boy
   and Luna device traces. No fabricated completion or weakened waits.
5. Android ARM64 compile, existing regression suite and device validation before
   any new APK release.

No APK build or workflow was started. Native runtime, saves, shader caches,
existing package ID and signing setup remain untouched by this source-only branch.
