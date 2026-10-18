# Ever Forward cooperative PM4 label waits

The owner's 0.9.44 trace measured 3.7–6.5 game FPS. The serialized GPU-command
thread spent roughly 2.2–3.1 seconds per five-second window inside EOP-label
reads, including real Vulkan timeline waits. Those are inclusive CPU timings,
not a measurement of GPU execution duration. Shader compilation also caused
separate hitches, including a 1.52-second call. No 30 FPS result is established.

0.9.45 changes only Ever Forward (`PPSA04703`). Before a `WAIT_REG_MEM` packet
reads a tracked constant label, the cache can poll its real producer tick:

1. Submit the recorded producer if its tick is still the current command buffer.
2. Query the actual Vulkan timeline without a host semaphore wait.
3. Also check that priority guest-memory publications through that tick finished.
4. If either dependency is pending, suspend this PM4 execution at the same packet.
   The existing round-robin guest-queue scheduler can process another queue.
   When all queues are blocked, its existing 100-microsecond wait bounds retries.
5. On retry, resolve current label metadata again. Overwrites and invalidations
   therefore cannot make an earlier constant stand in for a newer producer.
6. Once ready, use the existing coherent read and original mask/reference/function
   predicate. Unsatisfied predicates remain suspended.

The polling path never publishes guest bytes, clears GPU ownership, signals a
semaphore, or advances the PM4 cursor. Unknown/GPU-generated values, texture
overlap, invalid ranges and unsupported widths keep the existing readback path.
Other titles retain their original behavior, including the Super Meat Boy profile.
Kyty remains the default native Android renderer; NovaFEX and the experimental
AnyPS5 integration remain packaged. Saves, caches, application ID and signing
certificate are unchanged.

Validation executes the production polling, label lookup, kernel routing and
PM4 wait bodies with deterministic timeline fixtures. Cases cover producer
submission exactly once, unfinished/finished ticks, active and queued prior
publications, later publications, independent queue progress, 32/64-bit values,
all supported predicates, overwritten/invalidated labels, unknown data, textures,
bounds and unrelated titles. Address/undefined-behavior sanitizer runs are also
required. A separate Vulkan test uses the production poll with a real queue
submission, timeline semaphore and GPU buffer write. It explicitly tests that
GPU completion does not bypass a pending CPU publication.

The full Android build and existing tests remain required. These tests establish
ordering and integration properties; only device traces can establish FPS or
gameplay correctness. This change does not add shader precompilation or change
NovaFEX's memory model.
