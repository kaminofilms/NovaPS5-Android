# Local test APK authorization — 0991

The owner explicitly authorized packaging the implemented source candidates for phone testing before the outstanding device gates are complete. This changes the packaging gate for an experimental test APK only; it does not mark any unfinished six-task implementation complete or establish a performance result.

Source base: branch fix/wonder-native60-no-apk at 82fe54da70a692db3b7973e81bd756bfbf6c6589; recovered 0968 corresponding-source archive, followed by overlays 0969, 0971, 0974, 0976, 0978 through 0989. The 0968 fiber patch is already present in this recovery archive and is not applied twice. Current frontend retains the landscape Welcome Hub and original com.kaminofilms.novaps5 identity. Fixed novaps5dev signing key retained. No Actions started.

A fresh local build is in progress with NDK r29, Android API 33, rebuilding NovaFEX and the AnyPS5 renderer with the same toolchain. The recovered prebuilt libmain.so and libnova_anyps5_renderer.so both import the unavailable __hash_memory symbol against r29 libc++ and are rejected for delivery. Final rebuilt import/provider audit, APK package/version/signature/ZIP/alignment checks are required before sharing.

Host checks passed in this run: six completion candidate suites (worker policy, descriptor/push/vertex binding cache, read-only depth policy, simulated frame hints, owned audio snapshots, ContextPush validation), real periodic-submit/semaphore bodies, flip lifecycle/registration diagnostics, bounded CRI attribution, audio policy/queue tests and bundled Turnip driver validation. These are not phone/GPU/FPS tests.

Unresolved: writable GPU resource ownership and safe DMA scheduling; real image feedback hazards; on-device binding-cache correctness/performance; exact flip/EOP freeze cause; live translated CRI hotspot attribution; Android ADPF/worker lifecycle and sustained thermals. ADPF/worker policies remain opt-in. No 30/60 FPS claim; no forced frame generation or FSR. The owner will supply device results.

This file records authorization and pre-package status, not a completed deliverable. Append final verification and artifact hashes only after the corresponding checks pass.
