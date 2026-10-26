# 0.9.80 completion and scheduling candidate — APK BLOCKED

Latest checkpoint: read [0987-READINESS.md](0987-READINESS.md) before judging current readiness. The historical task list below describes the 0980 checkpoint. New binding, audio-lock, read-only-depth and invalid-context source candidates are saved; six host suites pass. Android/GPU/device gates remain open. No APK is ready.

User instruction: do not build an APK until the original six tasks and added
Ever Forward work are implemented and validated. No APK is produced here.

Saved implementation:
- native/power/FrameHints.h: opt-in NOVA_ADPF frame-recording hints, actual native
  renderer TID plus registered SDLThread/UnityGfxDeviceW guest TIDs; CRI excluded.
  Supports session creation failure, bounded retry, target updates, background
  detection at recording boundaries and RAII teardown. Honors NOVA_FPS_CAP and
  NovaRuntime thermal output cap. First indexed/auto/indirect draw starts a cycle;
  guest Flip ends it. This measures host frame RECORDING span, not GPU duration,
  whole guest simulation time, or per-thread CPU counters. Loading spans over
  one second are discarded. No clock-lock or core exclusivity claim.
- native/power/WorkerPolicy.h and WorkerAffinity.h: opt-in
  NOVA_WORKER_AFFINITY narrows only Job.Worker/Background Job. threads to at
  most six currently allowed CPUs while reserving the two highest-ranked CPUs
  from those workers. Ranks use cpu_capacity, falling back to cpuinfo_max_freq.
  Unknown/uniform topology or fewer than four allowed CPUs leaves affinity
  unchanged. CPU IDs are never guessed. Other threads/processes can still run
  on those CPUs; this is not exclusive ownership and not a CPUID/core-count clamp.
- tools/ci/patch-0980-completion-power.py: applies thread/frame hooks and changes
  QueueOperation priority notification from notify_one to notify_all on the
  shared condition variable. GPU timeline waits and callbacks remain ordered.
  This is notification hardening, NOT a demonstrated explanation of the
  observed freeze. Existing predicates may already exclude the suspected wrong-
  waiter scenario. No event is synthesized and no flip is force-retired.

Validation in this reconstruction:
- ASan/UBSan worker-policy tests: topology ranking independent of CPU IDs,
  restricted allowed sets, invalid and uniform topology, small CPU sets.
- Actual frame-hint implementation compiled/run against a SIMULATED Android
  service: real host native TIDs, guest registration, CRI exclusion, thermal
  budget, pause and RAII teardown. This is NOT Android service/device validation.
- Not yet validated: full patched Android core build, on-device hint support,
  thread-exit/reuse races under Android, complete suspended-frame lifecycle,
  cpuset changes after startup, runtime performance/thermal effects.
- Neither opt-in flag is enabled in the launch profile yet. This candidate is
  not wired into the default core build until integration checks are complete.

Six-task readiness:
1. CPU-owned read-only ring snapshots expanded in 0978. Arbitrary transfer
   hoisting, GPU-written zero-copy promotion and writable/BDA ownership redesign
   remain unimplemented. Disjoint fault-address telemetry cannot prove store width.
2. Whole/subresource reader stages corrected (0978/0979). Color/depth sampling
   layout redesign and feedback validation remain unfinished.
3. Existing pipeline/viewport/scissor caches audited; depth statistic is a scalar,
   not a table leak. Descriptor/push/vertex version-aware caches remain unfinished.
4. Real completion notification hardened in this candidate. Exact freeze edge,
   EOP event generation, callback publication and safe retirement remain unresolved.
5. NEON output fold and bounded SDL recovery implemented in 0978. Guest CRI hot
   function attribution and any native decode/mix replacement remain unresolved.
6. ADPF/worker scheduling source candidate saved; Android integration and device
   validation remain unfinished.

Do not describe all tasks as complete or promise 60 FPS. No APK may be packaged.
