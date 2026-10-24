# Shared timing, output pacing and thermal work (source validation)

This work combines the 0.9.70 UI/installer tree (`261fc2c139b2061b3320e37a4d56f1c3e9ba4bec`) with startup/power commit `58277cb879cc39cc440babb0563bf7ad313e4441`. Native Android ARM64 Kyty + NovaFEX remains the architecture. USB/SD folder handling and signing material are unchanged. No APK was built or published for this work.

## Implemented

- Separate vblank and presentation workers. Slow rendering, frame generation and output caps no longer run inside the vblank worker. The shared monotonic deadline discards missed deadlines rather than replaying overdue events. Pause/resume rebases deadlines. Guest flip intervals, generation checks and existing queue backpressure remain; port locks are released across presentation so GPU stalls cannot hold vblank locks.
- Output caps apply at swapchain submission, including generated and repeated output. Guest clock APIs are unchanged. Completed guest flip groups, successful output submissions and generated submissions have separate counters. Heartbeats and repeated output do not increment game FPS. A submission is not evidence that a physical scanout completed.
- Bounded clock audit executes actual translated RDTSC/RDTSCP and CPUID leaf 15, comparing them with HLE TSC/process counters, process microseconds, host monotonic counter and the CPU-derived 100 MHz GPU reference-clock API. The reference-clock measurement is not a raw GPU timestamp query. Reports use up to 13 valid captures, at five-second intervals, within 36 attempts; long captures and pause transitions are excluded/rebased. Real flip intervals have a bounded 256-interval distribution with median/p95/p99/max.
- Automatic/Cooler/Performance controls use Android thermal status and headroom. Headroom polling never exceeds once per ten seconds across lifecycle restarts. Escalation disables frame generation and caps output at 60, then 30. Recovery requires 60 seconds of cool evidence and proceeds one level per 30 seconds. Cooler retains a 60 FPS output ceiling; Performance tolerates more headroom pressure but still responds to system thermal status. Missing readings do not cause unsupported recovery. User preferences remain stored and restore after recovery. No guest-clock changes or mid-frame render-size changes occur.
- Legacy saved turbo is ignored; the detached forced KGSL maximum-clock loop remains removed. Android retains clock, voltage and thermal authority. These are app-level workload controls, not undervolting.
- Hellblade uses native stat metadata and sampled duration tracing from the supplied commit. New bounded pending-call tracing records guest/host paths and resolve-versus-metadata stage even while a stat has not returned, through the existing freeze reporter. Native metadata preserves identity/ownership fields. This instrumentation does not establish the cause of a remaining freeze.
- Table-PFS installer handles explicit inode-table placement, unsigned 64-bit inodes, block-local directory padding and payload extents separately from allocation padding. Bounds errors include offsets/sizes/inode context. NAPS layouts fail explicitly instead of pretending they are ordinary inner PFS.
- The simpler 0.9.70 graphics sheet, resolution targets and frame-generation multipliers remain. The new power control uses that UI. Advanced settings remain separate.

## Audit findings and primary sources

- [shadPS4 time.cpp](https://github.com/shadps4-emu/shadPS4/blob/main/src/core/libraries/kernel/time.cpp) and [native_clock.cpp](https://github.com/shadps4-emu/shadPS4/blob/main/src/common/native_clock.cpp): maintain agreement between counter units, reported frequency and monotonic conversions.
- [Eden core_timing.cpp](https://github.com/eden-emulator/mirror/blob/master/src/core/core_timing.cpp): reviewed pause/event deadline treatment. No emulator source was copied into the deadline helper.
- [FEX pinned source](https://github.com/FEX-Emu/FEX/tree/14c92681f4d62cf84d901460e0358de09c8847a7): translated cycle counter reads the ARM generic counter; CPUID leaf 15 scales its frequency using the same TSC scale. Nova already forces SMALLTSCSCALE off. Source inspection therefore does **not** establish a frequency mismatch. The new translated probe still needs execution on ARM64 and clock-ratio logs on the target device.
- [Android Vulkan frame pacing integration](https://developer.android.com/games/sdk/frame-pacing/vulkan/add-functions): Swappy requires extension negotiation, queue mapping, JNI/window initialization, per-swapchain lifecycle, present replacement and synchronization ownership. **Swappy is not integrated.** Existing Vulkan/FIFO/compositor timing remains; frame generation is disabled without its required display-timing support. A future integration needs the complete lifecycle and fallback, not a single present wrapper.
- [Android thermal APIs](https://developer.android.com/games/optimize/adpf/thermal): polling limits, unavailable readings and supported workload adaptation informed the policy.
- [pkg-to-anyps5](https://github.com/awake-devel/pkg-to-anyps5), [LibProsperoPKG format documentation](https://github.com/SvenGDK/LibProsperoPKG), and KytyPlus NAPS extractor were studied for table placement and compressed logical-address mapping. No external decoder code was imported. Newest KytyPS5, KytyPlus and AnyPS5 changes were reviewed; unrelated GPU/synchronization changes were not blindly merged. Reddit/jailbreak discussions were discovery leads, not parser correctness evidence.

## Validation completed

| Check | Result and limit |
|---|---|
| Production timing headers | ASan/UBSan tests pass at 30/60/120 Hz, long and repeated 500 ms stalls, pause/resume epochs, ratios, bounded interval windows and workload caps. These are deterministic deadline tests, not a device scheduling benchmark. |
| Native Android compilation | Seven changed production ARM64 units compile with NDK r28c/API 33: Android JNI, videoOut, swapchain, Vulkan window, filesystem, clock audit and FEX clock probe. Full Kyty/FEX link not completed. |
| Android frontend | Full application and SDL Java sources compile against API 36. UI appearance is not device-verified. |
| PKG native library | Android ARM64 installer JNI shared library links, with 16 KiB page settings. No APK packaged. |
| PKG tests | Expanded table-PFS and legacy parser/install suites pass under ASan/UBSan; malformed bounds, traversal, compressed metadata and explicit unsupported NAPS rejection included. Fixtures are synthetic, not the user's failing package. |
| Startup tracing | Pending resolve/metadata snapshots, disabled tracing and lifetime cleanup pass ASan/UBSan. |
| Existing regression tests | Native stat, external USB/SD paths, fibers at O0/O2/O3, frame-generation guards and audio/frame-extent tests pass. Fiber tests do not establish Wolverine boot. |
| Thermal policy | Escalation, gradual recovery, unavailable sensors, Cooler floor and oscillation checks pass. No measured device heat reduction yet. |
| Clock probe | Assembled x86 bytes match embedded probe and preserve RBX. ARM64 translated execution test added but not run. |
| Overlay | Reverse/reapply roundtrip reproduces the exact patched production source. |

Reproducible entry points: `tests/test_0971_timing.py CORE`, `tests/compile_0971_android.py CORE NDK HEADERS GENERATED`, `tests/test_guest_clock_probe.py`, `tests/startup_stat_trace_test.cpp`, `tests/ThermalPolicyTest.java`, and the existing regression scripts. Production build applies patch 0971 after 0968/0969. Compilation validation supplies real dependency and generated shader headers.

## Evidence and unresolved issues

Supplied older 0.9.65 logs show large inclusive GPU readback/synchronization scopes in Meat Boy, Hollow Knight and Ever Forward, and large draw/present scopes in Wonder Boy. Shader compilation also spikes. These scopes overlap and cannot be added as independent costs; occasional GPU-busy values above 100% are not reliable utilization. They do not justify bypassing synchronization or attributing every slowdown to translation or heat. No new FPS gain is measured.

Wonder Boy's reported 14–16 real FPS and accelerated/bursty movement with frame generation off remain a device reproduction target. Thermal status none and battery 35–36°C do not establish thermal throttling. The new ratios distinguish clock disagreement from frame delivery; neither diagnosis is confirmed yet. The controls do not promise higher FPS or lower temperature.

**PKG is not fully fixed.** NAPS compressed inner files require logical mapping and Kraken decoding; SELF unwrapping is also not implemented by this work. The screenshot alone cannot determine whether its extent error is allocation padding, table placement, compression or truncation. Need the failing package's structural metadata (superblock, inode/layout information and detailed new error), and an appropriate legal fixture, to reproduce. Bounds checks remain enforced.

**Hellblade PPSA27581:** no verified game frames/boot. Native stat and pending-call path/stage tracing need new on-device logs to locate the FUSE wait. Idle APR activity does not establish a lost completion.

**Wolverine PPSA03671:** null RDI at guest RIP 0x90382d471 remains unresolved. No instruction skip or fabricated object was added. Requires the matching guest executable/symbol context and an initialization trace of the missing object. Last AGC activity alone is not causal evidence.

Remaining validation: full core/FEX link, actual ARM translated clock-test execution, target-device clock ratios and real/output FPS distributions, concurrent close/recreate/pause stress, thermal recovery and UI checks, and reproductions of the actual package and boot failures. No device-verified result or successful game boot is claimed.
