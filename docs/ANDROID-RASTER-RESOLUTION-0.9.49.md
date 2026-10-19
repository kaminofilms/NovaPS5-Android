# NovaPS5 0.9.49 raster resolution

The 0.9.48 owner log confirms a 640x360 Unity launch request was ignored: dominant main passes remained 1920x1080. This release implements scaling inside Nova instead of relying on that request.

For Ever Forward PPSA04703, select **Internal raster resolution (experimental)** in per-game Graphics and restart. Native is the default; 720p, 540p and 360p select genuine smaller Vulkan color/depth attachments for eligible 1920x1080 raster passes. Viewport/scissor coordinates scale with them; fragment coordinates map back to the game's native coordinate space. Pass-boundary blits preserve LOAD contents and restore native-sized images for sampling, compute, copies and guest readback.

This is a raster bridge, not a universal image/compute scaler. Shadows and other dimensions remain native. MSAA, stencil, multilayer rendering, attachment feedback, shader storage writes, incompatible image views/formats, missing blit support and allocation failures fall back atomically to native rendering. Additional blits cost bandwidth, so a lower setting can be slower. Native mode and other titles retain the original push layout and rendering path.

`NOVA_RESOLUTION_RASTER` reports actual scaled draw counts and native fallback counts every five seconds. The existing actual-render-area trace reports the Vulkan pass dimensions. A selected setting alone is not evidence of activation. No owner-device performance result or 30 FPS claim exists for this build.

Validation runs production-source color/depth proxy and render-pass methods on Vulkan with synchronization validation: native/720p/540p/360p, four color attachments, depth, clear and LOAD preservation, reuse, native-size readback and the production fragment-coordinate emitter branch. Production policy and viewport/scissor tests exercise fallback, per-title isolation and inverted viewport height. Policy and PM4 exact-word publication tests run under ASan/UBSan. Full native source compilation and APK marker/signature/version checks run in CI. The Vulkan harness substitutes allocation and native image-tracker plumbing; it is not a full game or phone benchmark.

Also ports upstream 099de8dea62cbf17c8e06a6c24e72b38475d1566's exact-word WRITE_DATA publication semantics (source reference: tools/ci/patch-pm4-word-publication.py), preserving per-word Nova guest address translation. Real GPU completion is still required; this release does not skip completion or discard readback data. Existing caches and signing identity are retained.
