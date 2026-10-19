# Ever Forward performance changes in 0.9.48

Owner logs from 0.9.47 show roughly 6 FPS after warmup, with thousands of readbacks and queue-poll suspensions per five seconds. Inclusive timers overlap and cannot be summed into a frame-time budget. These logs do not establish a fill-rate bottleneck or that Unity accepted a lower resolution.

## Correct the compiled-out settings

`KYTY_NOVA_FEX` is defined by a header, not globally by the build. The configuration and rendering translation units did not include that header, so the Android presentation override, resolution request and dimension trace were excluded. Use explicit Android/ARM64 guards. The previous extracted-getter test forced the missing macro and failed to catch this defect.

A new test compiles the complete production configuration translation unit without that macro, testing desktop and Android/ARM64 configurations, Ever Forward and another title. APK verification checks that the linked native library contains all new feature markers. Neither test proves PS5 Unity accepts standalone-player arguments. Actual render-area logs are required to establish acceptance; Android output size is unchanged.

## Port selected upstream work

Source: KytyPS5 commit [d58aefde490d192950a24eb7e6cce008adc6afef](https://github.com/KytyPS5/KytyPS5/commit/d58aefde490d192950a24eb7e6cce008adc6afef), renderer synchronization/allocation optimization.

The port queues CPU-dirty BDA ranges and synchronizes their intersections with mapped ranges instead of repeatedly scanning every mapped range. Newly registered buffers and mappings are queued. Dirty transitions precede queuing; taking pending ranges atomically exchanges the queue under its own mutex, so a concurrent dirty event is processed by this or the next drain. Existing synchronization, ownership, memory fault and GPU completion paths remain responsible for correctness.

BDA stream buffers use VMA suballocation rather than forcing dedicated allocations. Both changes apply only to `PPSA04703`; `NOVA_EVER_BDA_SYNC=0` restores the original path for comparison. Other titles retain their original scan/allocation path. No presentation-lock removal, pipeline-cache format change or speculative memory-order relaxation is included.

The port is a potential reduction in CPU bookkeeping and allocation overhead. Its benefit depends on the game's BDA usage and requires device measurement.

## Verification and limits

- Upstream memory-tracker dirty-range and concurrent-drain tests run against production tracker/page-manager code and real protected host pages.
- The range-selection probe extracts the production synchronization routine and verifies mapped intersections, mapping holes and clean drains. It records selected ranges; it does not run Vulkan buffer uploads or verify rendered GPU contents.
- Both suites and the complete configuration test run with AddressSanitizer/UndefinedBehaviorSanitizer. The sanitizer harness uses lower host virtual addresses to avoid ASan shadow-memory collisions.
- Existing cooperative-label tests and the Vulkan production-completion-poll regression remain unchanged. The latter validates real timeline/buffer-write publication ordering, not full BDA rendering.
- New `queue_poll_wait` timing measures the actual PM4 wait call while all queues are blocked. The wait interval and real completion predicates are unchanged. Existing suspend-call timings did not include this sleep.
- Native compilation and APK checks must pass before release. No phone runtime result or 30 FPS claim follows from host tests.

## Device comparison

Update with the existing signing key. Keep the same scene, driver and cache state. Select Ever Forward's 960x540 experimental request, relaunch, and capture the full startup plus at least 30 seconds after warmup. Check `NOVA_RESOLUTION: Unity launch request`, actual render areas, `NOVA_BDA`, `queue_poll_wait` and FPS. Compare Game default in the same scene. Mixed-resolution passes (e.g. shadows) can persist; smaller output alone is not evidence of smaller main render targets. If dimensions do not change, a game-specific internal render-scale integration is still required.
