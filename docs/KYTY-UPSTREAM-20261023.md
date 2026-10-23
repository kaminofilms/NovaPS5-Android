# Kyty upload integration — NovaPS5 0.9.65

Input: KytyPS5-KytyPS5-2026-10-23-9dcff95.zip, revision 9dcff95e809ec43ba66f56648164070f4b16348f.
Compiled Nova baseline: 0.9.64, repository commit 5474e56b15c4c243f22f763d38c48aeff0e30afc, Kyty base df5b9b92be7dfd463b47756b707d6d356a9f0550.

## Included in this update

Port the uploaded revision's DPP write fix: avoid preserving an old vector-register value for full-mask DPP writes that overwrite all active lanes, and use the upstream mask/row-shift write predicate. This addresses an upstream packed-ancillary shader compilation crash. Adopt the equivalent emitter helper refactor from that revision so the write predicate matches its tested source. Bump the driver/shader cache signature to NovaPC65DPP so cached pre-fix shaders are not reused. Reuse the unchanged NovaFEX/FFmpeg artifacts from successful run 39865101483 only after verifying their source/build recipes match the baseline; re-run ARM64 bridge tests and rebuild the changed Kyty library.

The Android core remains on the pinned Nova base with its existing native/FEX, synchronization, scaler, cache and driver patches. This is a targeted upstream fix, NOT a full update of Kyty to 9dcff95. No PS5 dashboard assets or runtime are added.

## Full merge assessment

Comparing the uploaded source to Nova's pinned upstream identified 280 changed files. A three-way merge against the exact source from successful CI run 39865101483 produced 30 conflicted files. Those conflicts are not silently resolved by choosing either side. Remaining files:

- CMakeLists.txt
- src/common/emulatorConfig.cpp
- src/graphics/guest_gpu/graphicsRun.cpp
- src/graphics/host_gpu/memoryTracker.cpp
- src/graphics/host_gpu/renderer/cache/bufferCache.cpp
- src/graphics/host_gpu/renderer/cache/bufferCache.h
- src/graphics/host_gpu/renderer/cache/streamBuffer.cpp
- src/graphics/host_gpu/renderer/cache/textureCache.cpp
- src/graphics/host_gpu/renderer/cache/textureCache.h
- src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp
- src/graphics/host_gpu/renderer/pipeline/pipelineCache.h
- src/graphics/host_gpu/renderer/renderCompute.cpp
- src/graphics/host_gpu/renderer/renderContext.cpp
- src/graphics/host_gpu/renderer/renderDraw.cpp
- src/graphics/presentation/videoOut.cpp
- src/graphics/presentation/window/swapchain.cpp
- src/graphics/presentation/window/vulkanWindow.cpp
- src/graphics/presentation/window/window.cpp
- src/graphics/shader/recompiler/backend/spirv/SpirvEmitter.cpp
- src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp
- src/graphics/shader/recompiler/backend/spirv/spirvEmitterInternal.h
- src/graphics/shader/recompiler/backend/spirv/spirvEmitterModule.cpp
- src/graphics/shader/recompiler/ir/passes/ShaderInfoCollection.cpp
- src/kernel/fileSystem.cpp
- src/kernel/memory.cpp
- src/kernel/memoryAddressSpace.inc
- src/libs/agc.cpp
- src/libs/libAmpr.cpp
- src/libs/libVideoOut.cpp
- src/libs/ngs2.cpp

The broader merge is pending. Its APIs and Nova behavior require a separate port and validation.

## PS5Themes lead

Inspected PS5Theme02-fix.7z from MasterPS0/PS5Themes release 1.0. Size: 186,931,849 bytes; SHA-256: 9bca0157bf639cd7204d6325cb77d038acdf1dc6ba53f39b9885035c2ff465b6 (matches published release digest).

The archive contains 590 paths, including dashboard artwork, four AT9 files, metadata and two application.ps.bundle files. It contains no .elf, .sprx or eboot.bin. Both bundles start with RNPSHEDR version 2 and remain protected:

- NPXS40037: PlayStation Plus, 3,922,560 bytes, manifest RNPS 0.63.4-6.23, twinTurbo=true.
- NPXS40063: Explore, 3,631,248 bytes, manifest RNPS 0.63.4-6.16, twinTurbo=true.

These are evidence about assets and runtime versions, not decrypted Home/Control Center bundles. Scripts use WinSCP/FTP to replace files on an existing console. No downloaded script was executed and no theme assets/binaries are incorporated into Nova.
