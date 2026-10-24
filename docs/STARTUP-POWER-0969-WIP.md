# Startup and sustained power changes — work in progress

No APK or workflow dispatch is authorized until the requested fixes are ready.
Neither PPSA27581 nor PPSA03671 has a verified successful boot with these changes.

## Implemented

* Android host-backed `KernelStat` uses native metadata instead of enumerating
  directories and packing directory entries. Archive stat keeps its prior path.
  Native metadata preserves file size, timestamps, type and block count. Linux
  errno is explicitly mapped to guest errors. No negative-result cache is used.
* Sampled stat entry/exit diagnostics identify guest/host paths, duration and
  failure, including slow path resolution. This is needed to distinguish slow
  repeated FUSE calls from a stuck request in the Hellblade log.
* Remove the detached thread that reasserts a device-wide KGSL max-clock override
  every second. Clear that legacy override during GPU initialization. The frontend
  ignores old saved turbo settings and removes the toggle. Android controls clocks
  and thermal throttling. No voltage writes or undervolting are implemented.
* Prevent negative vblank sleep debt from producing a burst of catch-up events
  after long frames. Preserve idle presentation's late-frame condition separately.
  Guest clocks, game simulation and frame-generation settings are not altered.

## Verification

`python3 tests/test_0969_startup.py <patched-kyty-root>` compiles native metadata
checks and executes the production pacing expression in a 100 ms stall regression.
Full Android Java frontend compilation also passed against API 36 and the same SDL
Java glue used in 0.9.68. No full ARM64 core build or device tests have run.

## Unresolved blockers

* Hellblade: main guest thread was in `KernelStat` / `__fuse_simple_request` at
  the freeze snapshot; this does not establish a permanent filesystem deadlock.
  APR events were idle, not evidence of a specific lost completion.
* Wolverine: null object dereference at guest RIP `0x90382d471` (`mov rax,[rdi]`,
  RDI=0). No proven allocator, graphics or fiber cause. No skip/null bypass applied.
  Need to trace writes to the object slot using the matching executable or a
  targeted runtime trace before selecting a repair.
* Low-FPS motion: GPU forced clocks do not accelerate a guest simulation clock.
  Uneven real frame delivery can feel like bursts; the vblank defect is a concrete
  candidate, not confirmation of the entire cause. No FPS gain is claimed.
