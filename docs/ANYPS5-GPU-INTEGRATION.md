# Nova PS5 0.9.14: AnyPS5 GPU completion adaptation

This release adapts a coherent subset of AnyPS5 synchronization technology into the
existing Android Kyty renderer. It does not import the complete AnyPS5 renderer or
shader compiler and does not establish that either Unreal title reaches a menu.

## Reference and license

AnyPS5: https://github.com/boykopovar/AnyPS5
Inspected reference commit: 131171e77218a26d5746a8074a8216ec66f4dcb0.
The upstream GPL version 2 license is preserved in LICENSES/AnyPS5-GPL-2.0.txt.
Copyright and authorship remain with the AnyPS5 contributors. Nova's top-level
GPL-2.0 and the original Kyty MIT notice are retained. The adaptations below were
written for Nova on 2026-10-15; they are modifications, not verbatim imported files.

Reference components:
- core/libs/prx/libSceAgcDriver/Execution/src/Pm4.cpp: RELEASE_MEM label sizing and timestamp semantics.
- core/libs/prx/libSceAgcDriver/Execution/src/Driver/Packets/PacketMemory.cpp:
  label writes and EOP interrupts ordered after recorded Vulkan work.
- core/shader/recompiler/SpirvBackend/src/SpirvMemory/SpirvFormatConvert.cpp:
  EmitDeviceAtomicMemoryBarrier, device-scope acquire/release visibility without a control rendezvous.

## Changes

Android CI builds an external pinned Kyty checkout, not vendor/kytyps5. Therefore
patches/kyty-anyps5-gpu-completion.patch is checked and applied to the EFFECTIVE
source after all existing Android transforms. Editing vendor alone has no effect
on the resulting APK. tools/ci/build-android-kyty.sh enforces this application.

1. Actual 32/64-bit EOP label stores now wait for the existing scheduler's real
   Vulkan timeline completion before publishing to guest memory. Earlier priority callbacks retire before this packet; its IRQ runs after
   the label write. This adapts AnyPS5 PacketMemory's drained CPU-store fallback,
   rather than adding a second Vulkan buffer/memory ownership system.
   GuestMemory::Copy remains on the GPU thread, preserving tracked-page fault
   handling and high guest VA mapping. Subsequent GPU uploads see the new label.
2. Timestamp values are sampled at completion rather than while recording.
3. Even non-interrupt labels drain their recorded work so CPU and cross-queue
   pollers can progress. This adds GPU/CPU synchronization and may reduce FPS;
   performance requires device measurement. Unknown event types remain rejected.
   Valid 0x2b/0x2d cache-writeback completions can carry an IRQ, matching their
   non-cache forms. Removed the previous WAIT_REG_MEM timeout-success bypass:
   unsatisfied waits remain suspended instead of pretending the producer finished.
4. Existing RDNA -> IR -> SPIR-V stays in place. S_WAITCNT_VSCNT(0) now emits an
   OpMemoryBarrier at Device scope with AcquireRelease, UniformMemory and
   ImageMemory semantics, instead of an execution subgroup OpControlBarrier.
   It no longer requests subgroup capability solely for store completion.
   S_BARRIER's real workgroup barrier remains unchanged. No new desktop-only
   Vulkan extension or feature is required by these changes.
5. graphics_fps_index is passed as NOVA_FPS_CAP at launch and consumed on the actual
   Vulkan presentation thread. 30/40/60/90/120/unlimited are supported (presentation
   caps, not simulation-rate overrides). Existing linear Vulkan blit is bilinear.
   Internal resolution, FSR EASU/RCAS and sharpening remain unimplemented and their
   controls are disabled. The saved configuration schema is retained.

## Build and source distribution

CI retains the native Android ARM64 build, FEX, SDL3, AAudio, package identity,
driver selector, touch controls, save paths and signing key. Version code is 62.

The release must include NovaPS5-build-source.tar.gz (this repository and build
scripts), Kyty-Android-corresponding-source.tar.gz (the actual patched renderer
and initialized dependencies plus adrenotools), and
FEX-Android-corresponding-source.tar.gz (actual patched FEX and initialized source
dependencies). The existing scripts identify pinned dependencies and build flags.
These archives accompany the binary even when this repository is private.
License texts and these notes are packaged in the APK assets/licenses directory.

## Validation and limits

Tests compile production EOP and SPIR-V fence-emission bodies into host harnesses.
They check GPU-completion-before-store, store-before-IRQ, 32/64-bit sizing, timestamp timing,
non-IRQ completion progress and rejection of unsupported events. spirv-tools
validates a minimal compute module containing the actual emitted fence operands;
this does not validate every generated game shader or execute Adreno Vulkan.
Existing startup, release-packet and FEX tests remain in the pipeline.

No physical Android device or PS5 game files are available to the build runner.
Super Meat Boy 3D PPSA31162 and Luna Abyss PPSA36257 remain unverified. Dead Cells
is also untested for this release: unchanged CPU/audio code is not regression proof.
No full AnyPS5 RDNA backend, FSR, resolution scaling, new PM4 opcode suite or
comprehensive device-lost recovery is claimed.

GPU write tracing is disabled in normal releases. Consequently the watchdog's
"0 GPU writes" is not evidence of zero GPU label execution. NOVA_GPU_WAIT queue
state is useful, but must be correlated with submission, waits and actual frames.
