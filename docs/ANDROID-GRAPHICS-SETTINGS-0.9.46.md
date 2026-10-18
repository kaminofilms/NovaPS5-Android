# Android graphics controls, 0.9.46

Settings > Graphics defaults applies globally. A selected game has a Graphics
button for title overrides; Use global defaults removes the overrides. Save
applies on next launch. Existing FPS preferences remain the fallback until an
explicit cap is selected. Saving per-game settings snapshots the displayed
values; resetting that profile restores inheritance.

Presentation chooses Mailbox, FIFO or Immediate; the existing Vulkan path
falls back to FIFO when unsupported. The cap limits presentation and never
raises the guest game limit. Disk cache disables Kyty shader artifact reads
and writes plus Mesa shader caching without deleting saved artifacts. Vulkan
pipeline caches remain enabled. Pipeline libraries can be disabled for driver
comparison; enabling still requires the existing feature/fast-link checks.

Settings are exported before SDL/native initialization in each fresh game
process, and effective requested values appear in the engine log. Native host
and ASAN/UBSAN tests execute production presentation and cache selection code.
Android Java/native compilation and APK checks run in CI. Device FPS remains
unverified.

Internal resolution scaling and asynchronous shader workers are not present.
The unused shader optimization config field is deliberately not exposed.
No switch disables correctness-critical memory readback, cache invalidation or
GPU completion. This update makes no claim of fixing Dead Cells' stalled label
or achieving 30 FPS in Ever Forward.
