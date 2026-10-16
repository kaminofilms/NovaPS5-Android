# Ever Forward wait costs and Dead Cells regression — versionCode 88

## New device evidence

The owner's versionCode 87 Ever Forward PPSA04703 capture (09:13:33, process
13293) shows warmed gameplay heartbeats at 2.3–3.4 FPS. A sampled frame from the
21-second attached video shows the game rendered and the overlay at 2 FPS.
The renderer thread 13351 spends roughly 3.3–4.1 seconds in MasterSemaphore::Wait
per five-second window (about 67–81%); presentation thread 13350 spends roughly
6–22 ms presenting per window. These are inclusive host timings, not GPU
execution timestamps. Shader warmup causes early one-second dispatch/shader
spikes, but later shader totals fall to roughly 0.17–0.46 seconds per window while
wait time remains high. Pipeline lookup/creation is generally only 9–57 ms.
Thousands of submissions occur per window. Cache I/O / variant lookup changes
have not produced an established sustained gameplay speedup.

Dead Cells PPSA15552 (09:15:48, process 14280) has two distinct events: early no-window
pause around 91 frames subsequently recovers; later it reaches heartbeats
20.5/34.1/45.0 FPS, then stops at 1,585 game frames waiting for an actual label:
queue(event 0), address 0x20edb76d0, 64 bits, equality func3, ref1, full mask,
current0. A sleeping PriorityOperationsThread does not establish the producer
or prove a semaphore implementation deadlock. The last-known-working build and
a complete exported log have not been supplied for this regression. No verified
root cause or freeze fix is claimed.

## Source inspection and changes

All relevant MasterSemaphore::Wait callers were traced in staged Kyty. Candidate
sources include the end-of-pipe CPU label fallback (Finish before publication),
GPU-dirty buffer readback, stream-buffer reuse, fault-buffer reuse, and frame /
resource retirement. The existing aggregate timer cannot distinguish them.
AnyPS5 PacketMemory at 82ddae75b6761757f3d3ba9c0723647469270f76 uses GPU label
writes, deferred labels and a drained CPU fallback. Transplanting deferred label
publication requires coherent guest/cache tracking and cannot safely be replaced
by simply dropping Kyty's Finish calls.

VersionCode 88 therefore makes only the following bounded changes:

1. Async pipeline-cache disk writes and MRU variant selection are enabled only
   when NOVA_CACHE_TITLE_ID is PPSA04703. Dead Cells and other titles restore the
   preceding synchronous cache-write and first-match lookup behavior. Timing
   reporting remains enabled. The idle writer thread still exists; this is not
   a complete rollback of versionCode 87 or proof that its changes caused the freeze.
2. Ever Forward may reuse an already-completed real timeline point when the
   current command buffer has no recorded commands, both callback queues are
   empty, and no priority callback is active. The current recording is retained.
   No tick is advanced or fabricated. Recorded work, incomplete ticks, callbacks
   or non-Ever titles keep the original Submit + Wait + BeginNext + Pop path.
   The EOP fallback no longer calls Handle merely to mark nonexistent commands
   as work for Ever Forward. It still finishes all prior real work, retires earlier
   priority callbacks, writes the requested data, and delivers the requested IRQ.
3. Inclusive cost scopes identify eop_drain, readback, ring_reuse and fault_reuse.
   These scopes overlap existing draw/dispatch/shader/wait scopes; never sum them
   as exclusive time. They will establish the source of remaining device waits.
4. Dead Cells retains a bounded 4,096-entry GPU packet-write history. The existing
   implementation had removed ring writes at build staging, so the earlier message
   saying an environment variable could enable it was misleading for an installed
   release APK. The message now describes actual runtime recording behavior.
   The ring records original GPU packet values; it does not dereference speculative
   guest memory or set the stalled label. It does not capture arbitrary CPU/JIT writes.

The missing Dead Cells label remains a genuine unsatisfied wait. No forced
completion, timeout-success conversion, wait predicate change, shader alteration,
cache wipe or backend replacement is made.

## Tests and release

Normal and ASan/UBSan local tests pass for Ever, Dead Cells and missing-title
profiles. Production MRU lookup, current resource/callee/layout checks and writer
lifetime tests remain. The actual production Finish body is tested over all 32
combinations of recorded work, pending ordinary callbacks, queued priority
callbacks, active priority callbacks and incomplete prior ticks. Only the
completed-empty Ever case elides a submit. Tests check unchanged current/known
ticks on that branch and retained submission/wait behavior otherwise.
The production GPU history block is exercised through wraparound and 20,000 writes
while a snapshot-reader thread runs for all profiles. Ring publication and both
freeze/wait readers use one mutex; readers copy bounded immutable snapshots and
release the lock before printing or inspecting queues. This prevents data races
between the GPU owner and the freeze-report thread.
Python/shell/whitespace checks pass. First CI attempt 38907384520 stopped in
test_gpu_completion.py because its extracted production EOP body now depends on
the actual render-profile header. The harness was updated to include that header
and execute its unchanged GPU-before-store/IRQ/timestamp/unsupported-event checks
for Ever, Dead Cells and missing-title profiles; all pass locally. No assertions
were removed. The intermediate corrected-harness run was superseded before
release by the synchronized ring/snapshot correction. Source compilation and APK
Kyty/SDL/NovaFEX compilation and normal/sanitized regression gates passed on
the final run. SPIR-V fence validation, RELEASE_MEM dispatch, GPU-before-store
completion tests and native AArch64 tests passed. APK packaging and signature/manifest/native-library verification passed. The
downloaded artifact SHA-256 matches the release metadata; libmain.so contains
all four new wait-reason strings and the corrected Dead Cells history message.

Source: 34431465ef6caa7f3af1ed65bb64d734b46a3d94
CI: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38908600203
Branch: fix/novaps5-0936-luna-watchpoint

Changed repository paths:

- tools/ci/patch-ever-render-costs.py
- tools/ci/novaRenderCosts.h
- tests/test_ever_render_costs.py
- tests/test_gpu_completion.py
- .github/workflows/android-native.yml
- docs/EVER-DEAD-CELLS-SYNC-20261016.md
- docs/HANDOFF-0.9.36-WATCHPOINT.md

The build script still applies one consolidated renderer patch. In addition to
versionCode 87 staged paths, it now edits guest_gpu/graphicsRun.cpp and renderer/
cache/bufferCache.cpp, streamBuffer.cpp and faultManager.cpp. The protected
0.9.35 baseline, native ARM64 architecture, application ID, signing identity,
cache formats and game saves remain unchanged.

## Continuation prompt

Continue NovaPS5 native Android ARM64, branch fix/novaps5-0936-luna-watchpoint.
Read this file and the preceding Ever performance handoff. Ever Forward remains
the performance priority, but the reported Dead Cells regression must be tracked.
Luna remains paused. VersionCode 87 did not establish a gameplay speedup.

Install versionCode 88 over the existing app, retain all caches/saves/drivers,
and capture full Diagnostics → Export for each title, keeping current and
previous game sections separate. For Ever, compare the same warmed gameplay area
and group the new eop_drain/readback/ring_reuse/fault_reuse scopes by tid/window.
Do not add inclusive scopes or call host wait duration GPU shader execution time.
No empty-fence skip count is currently logged, so a FPS change alone does not
prove this optimization caused it. Further GPU label batching requires proper
coherence and callback lifetime implementation plus actual ordering tests.

For Dead Cells, distinguish the recoverable no-window event from the later
0x20edb76d0-style label wait. Inspect recent original GPU writes and watched
producer lines; absence from this ring is not proof that no CPU/JIT writer exists.
Obtain the last-known-working version and complete guest/main/GPU thread stacks
before attributing the regression to a commit or selecting a broader rollback.
Never change 0 to 1 merely to get past the wait. Report whether gameplay recovers
on the phone; the scoped rollback and empty-fence proof are not a verified fix.
Return real CI and APK identifiers and no unmeasured 30/60-FPS promise.

## Published APK

https://github.com/kaminofilms/NovaPS5-Android/releases/download/v0.9.36-android-3443146/NovaPS5-0.9.36-android-arm64.apk

- Version name: 0.9.36-android; versionCode: 88
- APK size: 20,613,740 bytes
- SHA-256: b570c8c247d682efa078e16d8aaa4802a20cebc2e6bacf7bf6fc5ef02b985234
- Package: com.kaminofilms.novaps5; ARM64 only
- Signing certificate SHA-256: 21882443635874231d80b57100a172d2f090b25047e6fa068edc29734cda2ae0
- APK Actions artifact: https://github.com/kaminofilms/NovaPS5-Android/actions/runs/38908600203/artifacts/12049333014
- CI run 38908600203 completed successfully at source 34431465ef6caa7f3af1ed65bb64d734b46a3d94.

The app ID, signing identity and higher versionCode support an update over earlier
development APKs. Installation, Dead Cells recovery and Ever Forward frame-rate
change on NX809J remain unverified. This is not a confirmed 30/60-FPS release or
a verified root-cause fix for the Dead Cells freeze.
