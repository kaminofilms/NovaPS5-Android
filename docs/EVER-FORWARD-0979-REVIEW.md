# Ever Forward 0.9.79 candidate: exact scope

Applies after 0.9.78. Complete C++ hunks: ever-forward-0979.patch.
Repeatable fail-closed patch: tools/ci/patch-0979-ever.py.

1. Readbacks: NOT bypassed. RenderContext::HandleFault passes fault_size=1.
The 64 KiB FaultWindowBytes path subsequently invalidates CLEAN tracker windows;
it does not provide the CPU store width. ReadbackClassification::promoted means
tracker callback larger than original request. ZeroCopy is incremented when
copies.empty(): it is NOT a host-visible allocation counter. Existing
DownloadBufferMemory already intersects tracker pages with exact GPU-modified
ranges. Existing NovaDeferWriteFault uses guard bands, excludes image aliases,
and snapshots/restores dirty bytes asynchronously; not every disjoint request
qualifies. Direct overlaps retain GPU completion ordering. REP/scatter/cross-page
writes and subsequent untrapped stores invalidate the assumption that a disjoint
fault address permits dropping the dirty remainder of a page. No automatic
host-coherent promotion or stale-result substitution implemented.

2. Periodic submission: graphicsRun.cpp NovaPeriodicSubmit defers only its own
opportunistic flush while NovaRendering() until max(configured threshold,4096).
At the default 1024 threshold, 90,960 draws imply about 89 periodic flushes, not
5,304. Explicit flush/readback/flip/ring-wrap paths remain. 4096 limits this
counter, not all draws in an actual render pass. 0.9.78 already expanded bounded
read-only CPU snapshot streaming to 64 KiB. Writable/BDA/texel ownership is not
redirected blindly. No transfer is hoisted across its producers/consumers.

commandScheduler.h/.cpp: Flush carries source_location to Submit. With
NOVA_SUBMIT_REASONS=1, a fixed 64-entry table reports scheduler/file/line/count,
plus overflow every five seconds, instead of attributing the cause to the GPU
timestamp hook. Logging is off by default; storage is bounded. No shader or
memory-order semantics change. The hook at 446 follows Submit; it does not
independently decide when to submit.

3. image.cpp: partial-subresource read->read merging accumulates ALL reader stages
and accesses; same-layout/same-access early-outs preserve stages even with merge
opt-out. Write dependencies and layout changes remain. 0x600=depth/stencil READ
(0x200)|WRITE(0x400); 0x620 adds SHADER_READ. Layout 4 is DEPTH_STENCIL_READ_ONLY,
not GENERAL (1). The conservative write bit cannot be treated as read-only from
a log alone; pipeline write enables, aspects and descriptor layouts need audit.
Rasterization-order attachment extensions/input attachments do not implement an
arbitrary texture-sampling dependency or allow skipping real layout transitions.

4. semaphore.cpp: Signal broadcasts only if WakeWaiters made a waiter ready.
WakeWaiters still walks the identical ordered waiter list and consumes the same
counts. Multiple newly ready waiters still receive SignalAll; replacing it with
SignalOne could wake the wrong waiter. Cancel/delete broadcasts unchanged. Wait
already has a count-available fast path under its mutex. No speculative spin,
no CPUID/core-mode change, no hardcoded Oryon core mask. Worker counts do not
prove which guest CPU-count query configured Unity. Guest pool clamp remains
unimplemented.

5. submitDone/EOP: NOT synthesized. An empty host pending queue is not evidence
that a guest EOP interrupt should exist. Real accepted/submitted/completed and
published event generations must establish the missing edge; filter -14 event
identity/payload/subscription must be retained. No false events or forced
startup completion added. Startup freeze remains unresolved.

Validation: tests/test_0979.py extracts and runs the actual production periodic
submit and semaphore Signal/WakeWaiters bodies under ASan/UBSan; verifies active
4096 budget, inactive configured budget, disabled policy, no-waiter signal,
insufficient-count signal, multiple waiters, exact consumption, and deletion.
Leak detection is disabled for the restricted process-inspection environment.
This is not a threaded cancellation/lifetime test. Native build log records
compile/link status. No phone run or 60 FPS claim; no new APK for this candidate.

CPU/GPU/scope intervals overlap. Removing ALL 1.069 seconds from an otherwise
unchanged five-second workload gives at most approximately 5/(5-1.069)=1.27x
throughput under that simplified serial model; it is not a 15-to-60 FPS proof.
GMEM traffic needs driver/hardware evidence, not only render-pass counts.
