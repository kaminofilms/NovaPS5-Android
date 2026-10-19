# NovaPS5 0.9.50 regression recovery

## Historical evidence

Personal Context recovered the owner's 0.8.1 Dead Cells 60 FPS report and 0.9.10 logs reaching game_fps 57.7 (later 53–57) with system Vulkan and AnyPS5 NGS2 audio. GitHub confirms 0.8.1 commit 6d7ae3c983d089157a1580133813cbd89bee6c3a, versionCode 39, successful workflow 38552822429. Both builds use native Kyty pinned to df5b9b92be7dfd463b47756b707d6d356a9f0550 plus NovaFEX; AnyPS5 provides audio, not the complete graphics backend. 0.9.10 commit is 0514188c4fe64f21661ca980a927fb4711a88995.

The old patch contains immediate CPU stores for EOP labels and diagnostic WAIT_REG_MEM timeout bypasses. The 0.9.14 synchronization patch replaces these with real completion followed by a CPU store. Restoring the whole old patch would therefore reintroduce incorrect completion. The newer owner log spends approximately 3.6–4.1 seconds per five-second window inside eop_drain; these inclusive timings are not independent GPU-duration measurements and cannot prove the entire FPS deficit.

## Changes

Dead Cells now records supported constant EOP labels as actual GPU transfer commands with barriers and immutable staging data. Guest CPU faults and PM4 reads reconcile the producer's real timeline before using the bytes. Pending known labels suspend their PM4 queue cooperatively, allowing independent producer queues to progress. IRQs remain ordered after real completion. Timestamp, texture, unaligned and unsupported label cases retain the drained fallback. No guest wait predicate, clock or GPU completion is fabricated. The path logs NOVA_DEADCELLS after successful label recording.

The 0.9.49 raster integration unconditionally called CommandScheduler::Current from Image::Transit, unlike the existing EndRendering path which checks Active. Current asserts on an inactive scheduler even if scaling is disabled. The revised transition short-circuits unless scaling is enabled and the scheduler is active. A production-body host regression exercises startup, external command buffers, native/360/540/720 settings, empty barriers and preflush ordering. This proves the code hazard and its correction; the owner's 0.9.49 crash tail is still needed to match their exact failure.

The old experimental resolution preference is no longer inherited: the new raster_resolution_v2 preference defaults to native. Users may explicitly select lower raster sizes again. Dead Cells receives a one-time per-game 60 FPS presentation cap migration so an inherited 30/40 cap cannot mask the test. Subsequent user edits remain respected; global and other-title caps are untouched. The activation log includes the effective cap and presentation mode and is included in shared key lines. Saves, caches, driver selection, package and signing identity remain intact.

## Validation and limits

Existing production completion/readback/label tests rerun after enabling the Dead Cells profile, including exact predicates, independent queue progress, overwrite/invalidation, mutation during waits, CPU fault publication, timestamp fallback, IRQ order and unrelated-title isolation. They also run with ASan/UBSan. Real Vulkan tests exercise label staging/overwrite/readback and timeline publication; scaler tests cover native and three lower raster sizes. Android compilation and signed APK feature verification are required before release.

No owner-device 0.9.50 boot or 60 FPS measurement exists yet. The older baseline used system Vulkan whereas the recent owner run used bundled Turnip, so restoring the same Kyty renderer is not sufficient evidence of equivalent performance. This release changes the identified synchronization bottleneck without silently changing driver selection.
