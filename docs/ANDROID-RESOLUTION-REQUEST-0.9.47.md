# Ever Forward resolution requests — 0.9.47

This is an experimental Unity Player launch request, not a universal renderer
scaler. A PS5 Player can ignore the arguments. No actual lower-resolution game
rendering or FPS improvement is established by host tests or successful CI.

Select Ever Forward > Graphics > Game resolution request: Game default,
1920x1080, 1280x720, 960x540 or 640x360. Save, then restart the game. Other
profiles retain existing behavior. Unsupported titles receive no added guest
arguments. Resetting the profile restores Game default.

The launch sends the selected dimensions through Unity's -screen-width and
-screen-height arguments. It does not shrink the Android surface, rewrite
render-target descriptors, force GPU completion or alter game files/saves.
The loader copies all argv strings into the mapped main guest stack rather
than passing tagged Android heap pointers to x86-64 guest code. Argument count,
individual length and aggregate length are bounded. Existing argument values
and ordering are preserved; the selected width/height request is appended.

The NOVA_RESOLUTION startup line labels the request as unverified. On Ever
Forward, bounded NOVA_RESOLUTION actual render area lines report real Vulkan
render-pass dimensions, attachment/layer counts and pass frequencies every
five seconds. They include depth/shadow/offscreen passes, not just the final
image. Compare Game default and a selected request at the same scene, with a
warm cache. A smaller Android window is not evidence of reduced game rendering.
Unchanged main-pass dimensions mean this request did not achieve scaling.

Normal and ASAN/UBSAN host tests execute request parsing, title isolation,
argv copying and the production loader stack-layout block. They cover all
four choices, invalid values, bounds, string lifetime, null termination,
alignment and pointers within the guest-owned allocation. Full Android
compilation/APK verification is handled by android-native.yml.

Unity references:
https://docs.unity3d.com/2019.4/Documentation/Manual/PlayerCommandLineArguments.html
Pathea tags Ever Forward as Unity:
https://patheagames.itch.io/ever-forward-demo

Remaining: device confirmation that the PS5 Player consumes the request. If it
does not, a verified title patch or renderer scaling implementation is required.
Neither 30 FPS in Ever Forward nor the Dead Cells missing-label hang is fixed
by this experimental request mechanism.
