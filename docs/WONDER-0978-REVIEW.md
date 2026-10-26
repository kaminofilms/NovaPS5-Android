# 0.9.78 candidate: source audit, not a six-root-cause or 60 FPS claim

## Task 1 — bounded CPU snapshot path implemented
File: src/graphics/host_gpu/renderer/cache/bufferCache.cpp
Before: read-only CPU-dirty requests up to CACHING_PAGESIZE use the stream ring.
After: requests up to 64 KiB use it, except texel/image requests; GPU-modified
regions still fail both ownership guards. Alignment now covers uniform, storage
and four-byte requirements. Existing Map(...,false) lifetime tracking, flush,
Commit and offset binding remain. Failure falls back to original synchronized
copy. No DMA commands are hoisted. Non-overlap alone does not prove hoisting
safe: earlier dispatches/copies can produce the source or consume old data.
This does not eliminate every buffer upload pass break.

## Task 2 — identical-reader stage preservation implemented
File: src/graphics/host_gpu/renderer/image/image.cpp
Before: equal layout/access returns without recording the new destination stage;
that early return bypasses the read-to-read counter.
After: union the destination stage before returning and count eligible read-only
elisions. A later write must wait on all readers. Different-layout transitions
remain. Numeric layouts 5 and 2 are SHADER_READ_ONLY_OPTIMAL and
COLOR_ATTACHMENT_OPTIMAL, not depth layouts. GENERAL does not legalize sampling
an attachment being written; feedback support and descriptor/rendering layouts
must agree. No global GENERAL substitution or sampled-depth bypass implemented.
Partial-subresource reader-stage preservation remains to implement/test.

## Task 3 — audit, no unsupported cache rewrite
Files: context.cpp BindPipeline; dynamicState.h SetViewports/SetScissors;
renderDraw.cpp stable-depth block. Pipeline and viewport/scissor dirty tracking
already exist. The depth statistic is ONE thread_local uint64_t; no map, hashing
or per-frame allocation. Increasing it does not leak memory. Descriptor/push/
vertex state needs command-buffer-scoped invalidation and resource generations;
no pointer-only descriptor cache added. Inclusive shader costs can be nested in
draw scopes; do not add them as exclusive CPU time. No descriptor optimization
claimed in this candidate.

## Task 4 — no invented completion
Actual Kyty path: libs/agc.cpp AgcSuspendPoint ->
graphics/guest_gpu/graphicsRun.cpp GuestGpu::SuspendPoint. It uses a semaphore
and an existing GPU-memory-stall escape; it is NOT merely Android OS suspend.
The separately bundled AnyPS5 driver's Submit/Suspend path is distinct.
No flip events or completion labels are synthesized. A software queue length of
zero does not prove recorded/submitted work, callbacks and timeline dependencies
are complete. Need serials for request accepted/prepared/submitted/GPU-complete/
callback-published/retired to locate the lost edge before changing retirement.
The 12-second causal chain is not established by co-occurring log lines.

## Task 5 — NEON and bounded SDL recovery implemented, guest hotspot unresolved
Files: src/libs/audio.cpp; src/common/novaAudio/Float12Stereo.h.
Before: scalar double float12 stereo fold and up to 200 ms SDL queue wait per push.
After: AArch64 NEON weighted dot products with existing gains/weights/clipping,
scalar portability fallback; wait bounded to one PCM block, clamped 1..20 ms.
Existing timeout recovery clears stale SDL audio and submits current PCM. This
can produce an audible discontinuity; it is not precise oldest-frame eviction.
SDL_ClearAudioStream clears ALL queued input. Blocking sample-clock pacing in
AudioOutOutputs remains. Nonblocking pushes remain unchanged.
The queues logged by SDL are bytes. 30720 float-stereo bytes = 3840 frames =
80 ms at 48 kHz. Do not call those 30720 samples. Existing 40 ms target is not
increased to the requested 4096..6144-frame (85..128 ms) target.
Output CPU profiling measured only a few ms per five seconds, so vectorizing it
cannot reclaim the CRI thread's outside CPU. AudioOut2ContextPush releases its
mutex before queueing, and its fallback loop already sleeps. 777M FEX gates do
not establish that exact native function spins. Guest-PC/HLE boundary attribution
is still required. No hardcoded silence/skip-decode or unconditional-success stub.

## Task 6 — not implemented
No cores 2..7 mask assumed. Frequency snapshots do not establish the scheduler's
placement or throttling reason. An affinity restriction can reduce sustained
performance/thermal freedom. A proper ADPF implementation needs actual native
thread IDs, frame-boundary workload duration, target duration, lifecycle and
pause handling. No per-draw duration passed as a frame budget, and no forced
KGSL turbo restored. This candidate does not prevent Android downclocking.

## Verification
Host ASan/UBSan stereo-fold reference comparison: sample counts 0,1,3,256,512,513;
random PCM/gains, clipping and output sentinels; tolerance 1e-6. AArch64 NEON is
compiled by the real Android native build; runtime performance and sound quality
still require the phone. This test does not execute NEON on x86.
Native core rebuild result is recorded separately in native-compile.log.
No new APK or device 30/60 FPS claim.

Apply patch after 0976, with native/audio/Float12Stereo.h next to the patch repo.
The complete fail-closed replacement script is tools/ci/patch-0978-wonder.py.
