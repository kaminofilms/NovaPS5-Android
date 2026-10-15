# NovaPS5 0.9.26: Persistent Vulkan pipeline cache and shader metadata

## Why this change
PPSA31162 on SM8850 / Turnip 26.3 in 0.9.25 shows 1.1–2.5 game FPS
after the AGC packet/cursor fault reductions. Latest on-device report:
- Frames 127 at first 4-second freeze; guest heartbeats 2.5 FPS then 1.1/1.7.
- Host access count 36,991 at the first freeze, 116,485 at the last heartbeat.
- Top remaining named CPU hotspot ShaderReadVertexMetadata with repeated
  Bionic memcpy SIGSEGV/aliasing sites.
- Shader counts continue increasing and a native SDL thread is blocked in
  `adreno_drawctxt_wait`, consistent with an unresolved driver/GPU wait
  alongside shader/CPU stalls.

## Actual behavior fixed
Upstream Kyty rejects patched ("-dirty") builds, but Nova's pinned
Android base patch already removes that gate. The remaining missing piece
was persistence on forced process exit. Nova 0.9.26 also uses a distinct
`NovaPC26` signature prefix:
a cache from an older renderer or incompatible GPU/driver is refused. Cache
is scoped to the PS5 title ID, from the game's param metadata (Android
provides a validated fallback if system content is not yet populated).
The file lives in the existing app-private `kyty/_PipelineCache` working
directory and survives game-process restarts and APK upgrades.

Also, Android GameActivity's Exit Game immediately calls killProcess, so
the old destructor-only Save() never ran in normal use. The renderer now
writes a snapshot after the 16th compiled pipeline and every 64 after that,
using the existing checked checksum + atomic rename, **without destroying
its live Vulkan cache handle**. Standard shutdown still closes the cache.
Snapshots run only on the owning renderer's serialized pipeline creation
path, not on GPU completion callbacks. This does not bypass Vulkan waits,
change event queues, or reuse outdated shader logic.

ShaderReadVertexMetadata now translates guest-owned fixed-size header and
16-bit direct resource offset arrays to bounded native aliases before
memcpy; when memory crosses guest mapping slots, existing wrapped memcpy
retains correct cross-slot copy semantics.

## Validation and expectations
Build tests enforce the patch anchors and assert version/device/title
cache key and snapshot invariants; the native Kyty build compiles all
modified code. These changes are intended to improve *repeat launch*
pipeline warmup and remove a measured high-frequency CPU memory trap.
The first launch must still compile previously unseen guest shaders, and
the game may remain GPU/driver/CPU limited at very low FPS.
Driver-cache snapshots do **not** store decoded guest programs, and
actual FPS uplift is unverified until comparable on-device runs.

Monitor messages beginning `Vulkan pipeline cache:` on successive
launches: first `initializing` then `saved` snapshots, next `loading`
and `loaded ... bytes`. If they remain disabled, investigate title ID,
build variant and Vulkan create-cache errors. Do not clear app storage
between comparable runs or the persistent cache will be deleted.
