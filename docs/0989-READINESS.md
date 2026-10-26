# 0989 flip registration accounting — APK BLOCKED

No APK was built and no GitHub Actions workflow was started.

The 0987 diagnostic counter had a real race: a registration was added to the
mutex-protected flip queue, then `KernelAddEvent` ran without that mutex, and
only after it returned did the code increment `active_flip_registrations`.
The event queue can invoke its delete callback during that window. The callback
would erase the registration and decrement zero, wrapping the unsigned counter.

`tools/ci/patch-0989-flip-registration-count.py` makes the diagnostic count a
projection of the queue that already owns registration lifetime. Insertion,
delete callback, and failed-`KernelAddEvent` rollback each store
`queues.size()` while holding `VideoOutEventState::mutex`. There is no
increment/decrement pair and therefore no callback-before-increment window.
KernelAddEvent, KernelDeleteEvent, KernelTriggerEvent, flip state transitions,
guest EOP publication, and presenter behavior are unchanged. No completion or
event is synthesized.

The structural regression checks all three publication sites and ordering around
`KernelAddEvent`. It passes against the recovered production source after the
0968–0988 overlay chain. The twelve selected production translation units compile
to Android ARM64 objects with NDK r29 Clang 21/API 33, including the modified
`videoOut.cpp`; the real Android power API link probe also passes.

That is object-level validation only. It does not replace a full core link or
on-device flip/EOP validation.

All prior remaining gates in 0988 still apply: writable GPU buffer ownership and
safe transfers; real image feedback dependencies; binding-cache lifetime/GPU
validation; exact flip/EOP freeze tracing; live CRI attribution; Android ADPF and
worker-policy validation; full current core/frontend/signing recovery; and device
`game_fps`. Do not claim 30/60 FPS and do not package an APK yet.
