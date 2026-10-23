# Kyty upload integration — NovaPS5 0.9.65

Input: KytyPS5-KytyPS5-2026-10-23-9dcff95.zip, revision 9dcff95e809ec43ba66f56648164070f4b16348f.
Compiled Nova baseline: 0.9.64, repository commit 5474e56b15c4c243f22f763d38c48aeff0e30afc, Kyty base df5b9b92be7dfd463b47756b707d6d356a9f0550.

## Included in this update

Port the uploaded revision's DPP write fix: avoid preserving an old vector-register value for full-mask DPP writes that overwrite all active lanes, and use the upstream mask/row-shift write predicate. This addresses an upstream packed-ancillary shader compilation crash. Adopt the equivalent emitter helper refactor from that revision so the write predicate matches its tested source.

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

MasterPS0/PS5Themes publishes theme archives for listed console firmware versions. Its repository tree contains only a short README. No standalone Sony dashboard engine or offline PUP decryption implementation was found in that repository. Theme binary contents have not been inspected or incorporated.
