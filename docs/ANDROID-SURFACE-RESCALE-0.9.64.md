# Nova 0.9.64 experimental surface scaling

This change is an independent Nova implementation. CapyPS5 v0.0.1 (archive
commit `5d9aed98b4fd99652bfa8e92da53c00bbf374d52`) was studied as an architectural
reference, as authorized by the owner. Its implementation was not copied or
included. Reference project: https://git.capyps5.org/CapyPS5/CapyPS5 .

## Behavior

`Graphics > Resolution scale (experimental)` selects Automatic, Native, 75%,
50%, or 33%. Automatic selects 50% for detected Unreal games and Native for
others. Detection recognizes command-line markers, an Engine directory, IoStore
files, or Unreal's Content/Paks layout. A lone .pak file does not identify Unreal.
The launch variable is `NOVA_RESCALE_PERMILLE` (1000/750/500/330).

New eligible 2D color, depth/stencil and display allocations use ceil-rounded
smaller extents. Guest image metadata stays at native size. Images must be
single-sample, single-mip, single-layer, uncompressed, at least 1280x720, with
host format blit-source/destination support. CPU uploads promote an image to
native before copying guest data.

Raster viewports, scissors and render areas follow the backing size. Fragment
coordinates reuse Nova's existing guest-coordinate push-constant bridge.
Integer image coordinates use each binding's actual host/guest ratio. Image
size queries use the exact original dimensions, avoiding inverse-rounding error.
Normalized UVs remain unchanged.

This initial implementation uses shader specialization IDs **400 through 527**
for 32 bindings, four uint32 values each: guest width/height and host width/height.
Stage-specific payloads are part of pipeline equality and hashing and are copied
into background compile jobs. This deliberately differs from the proposed
push-mask design: Nova's existing 128-byte guest push block is preserved.
Specialization constants with equal defaults get distinct SPIR-V identities.
Translated shader caches use separate native64/rescale64 namespaces. Graphics
pipeline libraries are bypassed on this experimental path because their existing
sub-library keys do not describe these binding payloads.

## Conservative fallbacks

Mixed attachment ratios, shader writes to buffers or images, compute consumers,
storage descriptors, indirect/dynamic-mip descriptors and binding indices beyond
31 fall back to native. Uploads, readbacks, resolves and image/buffer copies also
promote affected images to native. Promotions preserve contents and defer old
backing/view deletion until the scheduler's GPU completion tick. Promotion is
permanent for that image's lifetime. Compute dispatch counts are unchanged.

Stencil is handled as its own aspect during promotion; depth/stencil transfers
use nearest filtering and the same format. Aliased attachment clears use backing
dimensions. Display copies already use actual backing dimensions, followed by
the presenter's existing linear upscale.

`NOVA_RESCALE` reports cumulative scaled allocations and promotions, including
the fallback reason. These are not counts of currently live scaled images.
The old compatibility scaler remains available. It is disabled while surface
scaling is active, so the factors cannot multiply.

## Auto Max FPS

The button saves FIFO, GPU turbo, 2x2 VRS, real GPU timing, Native resolution,
1080p output and frame generation off. Wonder Boy gets a 30 FPS presentation cap.
Existing synchronization/readback selections are preserved. The preset makes no
FPS guarantee. Choose 50% separately to test the new surface scaler.

## Validation and limitations

The overlay is applied after the 0.9.64 transition histogram and validates all
text anchors before writing any file. Local checks executed the real SPIR-V
builder, production Java settings with Android stubs, Unreal detection, extent
rounding, invalid input handling and attachment-ratio fallback rules. Host tests
also ran with address/undefined-behavior sanitizers (leak detection disabled in
the container). The shader image emitter and pipeline shader source were checked
with the host C++ compiler. Broader host syntax checking encounters existing
GCC/Vulkan-header aggregate-assignment incompatibilities; this does not replace
the Android NDK build.

**No device performance or visual correctness result is claimed. Native APK
compilation, packaging, signature verification and device testing remain required.**
Start with Ever Forward and Wonder Boy at 50%; compare NOVA_GPU_TIME, game_fps,
NOVA_RESOLUTION and NOVA_RESCALE in the same phone performance mode. Check UI,
stencil/depth effects and presentation. If a title mostly promotes back to native,
its coverage is limited and an FPS gain should not be assumed.

## Primary technical references

- Vulkan blit validity, aspect/format/sample/filter rules:
  https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdBlitImage.html
- Vulkan specialization data and unique constant IDs:
  https://docs.vulkan.org/refpages/latest/refpages/source/VkSpecializationInfo.html
- Vulkan shader specialization and unused map entries:
  https://docs.vulkan.org/spec/latest/chapters/pipelines.html

The existing signing key is not modified. Lossless.dll is not included; it
remains user-supplied.
