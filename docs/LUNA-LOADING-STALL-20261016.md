# October 16 Luna loading stall and controller output

Device report: versionName 0.9.36-android, NX809J/SM8850/Android 16, PPSA36257.
The owner reports no crash, remaining on the loading screen at approximately
1 FPS. The supplied later heartbeats report 3.5 and 5.1 game FPS and increasing
game frames (1896 to 1973). These counters do not prove loading completes or
identify the visible scene.

The no-window message precedes a period of frozen presentation. That background
pause cannot by itself explain the earlier foreground loading-screen behavior.
Later frames progress again. The pasted stack tail begins after the main and
GPU-worker stacks, so it cannot locate their foreground bottleneck.

Thread 13616 is in KernelBatchMap2 -> RenderContext::UnmapMemory ->
GuestGpu::SendCommandSync. The real source removes a command from m_commands
before executing it and releasing the caller's semaphore. Therefore zero
commands pending does not prove that command has completed. UnmapMemory can
wait in CommandScheduler::Finish, WaitPriorityOperations, and cache invalidation.
Neither that stack nor a sleeping SuspendPoint caller establishes a deadlock.
No GPU wait/completion behavior is changed on this evidence.

The existing controller implementation fills the guest PadData pointer directly.
Repeated native field stores fault when this pointer requires guest translation.
The latest hostemu counts rise by roughly 1238 across 77 game frames (about 16
emulated accesses/frame), with PadReadState fields prominent. Counts alone are
not elapsed-time measurements and do not prove this is the 1 FPS bottleneck.

The controller patch builds the exact same zero-initialized 120-byte packet in
host-local storage, then publishes it through the existing GuestMemory::Copy.
This preserves buttons, axes, touch, sensors, connection state, timestamp,
reserved bytes and padding. Both PadReadState and each PadRead packet share
this initializer. The copy handles noncontiguous guest slots and still faults
on an inaccessible destination. Return values, handles, sampling and input
semantics are unchanged. No renderer, JIT, guest layout or wait path is modified.

Host tests compile the actual patched initializer, the original initializer for
differential comparison, the real PadData/ControllerState declarations, and
the production NovaGuest/GuestMemory copying helpers. They check 726 packet
comparisons across six input/connection variants and all 119 crossing alignments,
guard bytes, and bounded guest-destination translations. The normal negative
tests require SIGSEGV for protected and unmapped backing. ASan catches an
unmapped synthetic guest address in its shadow gap before the CPU store;
the sanitizer test requires that exact WRITE-107/address report rather than
accepting an arbitrary sanitizer failure. Both normal and ASan/UBSan runs pass.
Local LeakSanitizer is unsupported under tracing; only the local run sets
detect_leaks=0. CI keeps its normal sanitizer configuration.

Source-only CI runs the existing Android compilation and ARM64 regression jobs,
plus controller tests before Kyty compilation. A commit tagged [source-only]
deliberately skips APK packaging; it is not a released or device-tested fix.
The last published APK remains versionCode 85, source 56282b0.

Next evidence required: export the complete boot-log text file, including the
entire latest foreground freeze report, beginning with MainThread and the GPU
worker stacks, its preceding heartbeats, shader/pipeline timing and guest thread
table. The pasted tail starts at tid 13580 and omits the relevant earlier
threads. Capture while the game window remains visible; preserve existing caches
and app data. Inspect the actual GPU-worker frame before changing synchronization
or calling the loading stall fixed. The CheckpointName writer is still unproven.
