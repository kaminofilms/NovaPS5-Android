# NovaPS5 runtime timing — 0.9.51

Baseline: 6bfa332ad6c67de0b70b243f2263191baa6ed417, native Kyty/NovaFEX.
Affected title named by owner: Wonder. The earlier Ghost of Tsushima attribution
and its title ID are not treated as verified identification for Wonder.

## Changes

- Watchdog FPS divides device flip deltas by measured monotonic elapsed time.
  Presentation FPS and game flip FPS remain separate.
- Watchdog thread count uses the registry mutex, avoiding a concurrent vector read.
- NOVA_PROCESS_CPU reports all-process CPU milliseconds and average occupied cores.
  This includes rendering, audio, guest runtime and other native threads.
- NOVA_FEX_PROFILE=1 enables exclusive guest-runtime versus native-call timing.
  CallGuest and GateDispatch scopes restore the prior domain through nested calls.
  The clock is monotonic wall time plus thread CPU time. The default is off to
  avoid adding clock reads to every native gate in normal performance runs.
- NOVA_FEX_TIME reports completed exclusive slices. Open intervals appear only
  after another boundary. Therefore these deltas are not exact window utilization.
  They can include a slice that started before the reported heartbeat window.
  Off-CPU includes both blocking and descheduling; it is not specifically Vulkan
  waiting. Guest-runtime CPU includes JIT, lookup, execution and fault handling.
  It does not isolate those components or count guest instructions.

No synchronization, memory ordering, renderer selection, saves or caches change.

## Findings and work remaining

The existing AnyPS5 bridge selects Kyty unless NOVA_GPU_BACKEND=anyps5 is explicitly
set. Removing AnyPS5 has not been justified by comparative device measurements.
The integration documentation describing an AnyPS5 default is stale.

The checked-in PipelineCache::GetGraphicsPrograms still fatally rejects disabled
mesh shaders and workloads exceeding host limits. Replacing that with an uncaught
exception would also terminate the GPU thread/process. A recoverable failure needs
an integrated session cancellation/error boundary, including pending GPU commands,
CPU waiters and presentation state. This patch does not claim that boundary or a
compute mesh translator. No essential geometry is skipped and no false success is
introduced. Native feature/limit negotiation and compute geometry translation
remain to be completed and validated against the staged source used by CI.

BufferCache::DownloadBufferMemory already enumerates modified ranges, records
staging copies and barriers, defers CPU publication and waits on completion ticks.
This patch does not duplicate that mechanism or weaken its required waits. Writer
attribution, duplicate readback reuse and lock splitting need further source and
trace analysis before changes can safely be made.

The existing raster proxy policy explicitly checks PPSA04703 (Ever Forward).
Removing the title guard alone does not prove copy, aliasing, attachment or shader
coordinate compatibility for other games. No global scaler expansion is claimed.

## Verification

Host C++17 production-helper tests pass for nested callbacks, exact exclusive
accounting, disabled profiling, thread-local isolation, invalid clock samples and
real sleep/off-CPU measurement. The existing backend selection test passes.
ASan+UBSan helper test passes with leak detection disabled locally because this
sandbox denies LeakSanitizer access to /proc task data. LeakSanitizer's initial
sandbox failure is not a code test pass. CI runs ASan+UBSan with its normal default.

Full Android compilation, original core tests, package/signature verification and
APK publication must be checked in the workflow results. No phone validation,
Wonder boot/geometry result, new FPS measurement or speedup is established here.
