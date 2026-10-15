# Native AGC packet generation (0.9.22)

The 0.9.21 phone run still reported 0.5–0.6 game FPS. Its late host-emulated
access total rose by over two million per heartbeat, while the displayed
instruction addresses accounted for only a small fraction. These cumulative
totals from different phone runs are not a controlled performance comparison.

The fault tracker previously retained only the first 48 instruction addresses.
It now uses 2,048 hash buckets, at most 16 probes per access, exact total
accounting, and an explicit untracked-access count. This both bounds the
per-fault bookkeeping work and allows later busy sites to appear in reports.
No allocation, locks, or symbol resolution occur in the fault handler.

The functional change extends native command-buffer views to 52 AGC packet
builders: register updates, indexed/auto/indirect draws, dispatch, queue state,
data writes and copies, predication, and other packet types. Existing staged
RELEASE_MEM, DCB COPY_DATA, and WAIT_REG_MEM paths are retained. For a packet
contained in one guest slot, native code writes directly through the translated
backing. The guest command pointer, embedded addresses, sizes, partial writes,
and cursor advancement remain unchanged. Ranges crossing a slot boundary
retain the existing fault-emulated behavior rather than assuming contiguous
native backing. Direct register-array readers also translate their input view.

When the command-buffer object is translated and already has enough capacity,
allocation reads and advances its native backing directly. Capacity exhaustion
uses the original method with the original guest receiver, preserving grow
callbacks, reserved space, and failures. GPU waits and completion semantics
are unchanged.

test_agc_native_packets.py executes 20 actual builders against the original
vendored implementations over 10,240 cases. Guest command and register mappings
are inaccessible while shared native aliases remain writable/readable. The
tests compare bytes including untouched padding, pointers, and cursors, then
exercise grow callback identity, failure, and slot-boundary fallback. The
earlier 21,760 copy/wait cases remain in the build. A separate production-code
tracker test covers late hot sites, concurrent exact counts, and overflow.

Build/test success does not establish a phone FPS gain, 30/60 FPS, or a visual
artifact fix. This remains a native Android Kyty/FEX build with the same bundled
Turnip and prior AnyPS5-derived adaptations.
