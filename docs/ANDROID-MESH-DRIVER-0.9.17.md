# Nova PS5 0.9.17: compute mesh driver for Adreno 8xx

The 0.9.16 APK bundled Turnip 20260923. That predates MaxsTechReview's
2026-09-27 compute implementation of VK_EXT_mesh_shader. Kyty correctly rejects
guest mesh draws when the selected driver does not expose meshShader.

0.9.17 bundles the Android/adrenotools A8xx build from:
https://github.com/The412Banner/Banners-Turnip/releases/tag/v26.3.0-20261012

Archive: Turnip-v26.3.0-20261012-A8xx.zip

SHA-256: 4893e09fef65271c434965cb8d5380a783115ca9c481cce8dfb81ae8f7395efc

Mesa source: 1f4952878d78caba95afcb4efa1a1dfaf4fbc692

Driver builder, patch stack and build recipes at the release tag:
https://github.com/The412Banner/Banners-Turnip/tree/3da8d41882195051db1283d9b37563a3709231f4

Mesh patch (MaxsTechReview, rebased by The412Banner):
https://github.com/The412Banner/Banners-Turnip/blob/3da8d41882195051db1283d9b37563a3709231f4/patches/a8xx-winnative/0001-tu-Emulate-VK_EXT_mesh_shader-with-compute.patch

The driver compiles task/mesh stages as compute, writes geometry to a ring,
and generates a vertex shader to read the output. Mesh render passes use sysmem.
The extension is advertised only for supported chips/shared-memory sizes.
Nova retains Vulkan feature queries and all per-shader output/workgroup/LDS
limits. This is a driver-level fallback, not a newly written Kyty fallback.
Other GPU families and the system-driver selection are unaffected.

The stable bundled driver ID remains unchanged. A revision marker now triggers
staged replacement after an APK upgrade; previously ensureBundled returned early
whenever an older valid driver was already extracted. A failed extraction keeps
the previous driver. A stopped directory swap is recovered on the next call.
Explicitly selected system/imported drivers remain selected.

CI checks the archive SHA-256 before building and inside the signed APK, ELF
architecture/page alignment, and presence of the compute mesh implementation.
These checks cannot prove physical-device feature advertisement or game rendering.
The upstream release also describes the driver as experimental and device-untested.

Device acceptance: select the bundled driver, launch Super Meat Boy 3D, confirm
the log identifies 20261012 and reports Vulkan MeshEXT limits, then verify an
actual rendered scene and input. Game boot/rendering is unverified until then.
