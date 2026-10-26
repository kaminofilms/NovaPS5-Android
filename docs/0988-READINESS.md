# 0988 AudioOut2 guest caller attribution — APK BLOCKED

Read 0987-READINESS.md for the remaining six-task gates. No APK was built and no
GitHub Actions workflow was started. This change supplies evidence for the unresolved
CRI CPU investigation; it does not claim an audio/FPS root cause is fixed.

## Source change

`native/audio/GuestGateCost.h` and `tools/ci/patch-0988-cri-attribution.py` add
`NOVA_CRI_ATTRIBUTION=1` profiling around the actual `AudioOut2ContextPush` function.
The flag defaults off. When enabled, a thread-local table retains eight exact guest
return RIPs plus one overflow bucket. Every overflow call and its timings remain
accounted for; the table never grows or allocates on each push.

Each completed push records thread CPU and monotonic wall time, blocking/async mode,
the original success/not-ready/invalid result, and explicit grain sleep duration.
Reports occur on a returning push after a five-second observation window and include
the actual native TID and guest return RIP captured through the existing NovaFEX API.
RIP zero means no captured guest context; the overflow row has `mixed=1`.

The original device submission, queue updates, mutex release sites, return values,
and sleep period remain intact. No new sleeps or successful stubs are introduced.
The report measures native ContextPush execution only. Wall time includes waits;
CPU time excludes time the thread is asleep. It does not sample translated code
between HLE calls, resolve a RIP to a guest module, or identify a CRI mix/decode loop.
Combine it with existing NOVA_AUDIO_PROFILE and per-thread CPU telemetry; do not add
their overlapping intervals as exclusive costs. Diagnostic clock/log costs perturb
the enabled run, so compare performance with attribution disabled afterward.

## Recovery and validation

Workspace maintenance removed the former core tree and toolchain. Completed source
through 0987 remains in GitHub. Library search found the prior 0.9.77 APK but no
matching source checkpoint, so it was not used as a new deliverable or source.
The actual vendor/kytyps5/src/libs/libAudio2.cpp was recovered from this branch
(blob 91fb83671bec4e4c17a31a28476dbec9dadd43cc). Its ContextPush body matches the
earlier recovered Android body; applying 0984 then 0988 succeeds.

ASan/UBSan tests pass for the real extracted ContextPush body with attribution off
and on: invalid handles, destruction during unlocked sleep, async full queue,
device clock path and grain queue pacing. Additional actual-header tests cover
caller zero, deduplication, more than eight callers, overflow timing retention,
clock rollback, report reset, disabled capture, enabled simulated guest capture,
and unchanged return values. Leak detection is disabled for the restricted host.

The test uses a simulated NovaFEX capture function, not a live guest. This checkpoint
has not been recompiled with the Android NDK after cleanup, fully linked, run with
live FEX/CRI audio, or measured on Adreno. Earlier 0987 ARM64 checks do not certify
this new header. Full overlay-chain recovery/application remains a validation gate.

## Remaining gates

GPU-written/BDA/storage ownership and safe transfer scheduling remain unresolved.
Read-only depth/G-buffer dependencies and binding cache lifetimes still need actual
GPU validation. The exact presentation/EOP freeze edge still needs a device trace.
CRI guest hotspot attribution still needs live caller data and guest code sampling.
ADPF/worker policy still needs Android lifecycle, cpuset, thermal and performance
validation. A full current Android core link and current Welcome Hub frontend
recovery are required before packaging. No native 30/60 FPS result is claimed.
