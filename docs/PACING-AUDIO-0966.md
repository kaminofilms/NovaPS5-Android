# NovaPS5 0.9.66: audio and generated-frame overhead

## Evidence from the four supplied 0.9.65 device reports

Each report includes a latest game log and a separately labelled previous-game tail. Analyze these separately; do not assign earlier performance to the latest run or sum overlapping/inclusive timings.

| Uploaded report | Latest-run evidence |
| --- | --- |
| Wonder Boy (PPSA27841) | Most gameplay heartbeats around 15–20 real FPS, with a temporary 32.5 FPS sample. Frame generation enabled at 3840x2160; roughly 9–13 ms average generation cost in many windows. |
| Super Meat Boy (PPSA31162) | Real FPS fluctuates, briefly reaches 50.8, then falls through 2.1/3.0/2.5 to 1.9. Readback calls exceed 200 ms, available memory drops below 1 GiB, and host-access emulation is active. Older run's 17–20 FPS samples are not this run's final gameplay. |
| Hollow Knight (PPSA34971) | Frame generation off; after loading, heartbeats around 50–59 real FPS, but these averages do not measure frame-time variance. |
| Ever Forward (PPSA04703) | Latest heartbeats about 10–18 real FPS, frame generation on. Report also contains a fatal unsupported vertex-buffer swizzle; this change does not implement that missing shader feature. |

`fps` includes generated presentation; `game_fps` counts real game frames. These reports do not establish stable native 30 FPS in all four games. GPU busy diagnostics sometimes exceed 100%, so they must not be interpreted as exact utilization percentages. The only AAudio underrun messages shown are startup messages; steady-state stuttering is reported by the user but not established by those messages alone. Audio queue timeouts are zero in the shown samples. Gain and channel volume are already 1.0/32768.

## Changes

1. Query SDL's actual opened device format, following shadPS4's surround/stereo distinction. If an 8/12-channel guest port feeds a mono/stereo device, reopen a two-channel stream and fold the PCM explicitly. Preserve the front channels, add center and surround at 0.7071, and add 12-channel height pairs at 0.5. Apply all original channel volumes/master/per-channel gains before folding; clamp output to representable range. Leave multichannel devices and native stereo paths intact. No change to guest sample counts, audio clocks, queue target or emulated time.
2. Bound optical-flow shared images to 1920x1080, preserving aspect ratio and never increasing smaller inputs. This reduces a 4K working image to one quarter of its pixels; game rendering, game FPS, swapchain output and internal-resolution settings remain separate. Extent comparison uses the bounded size so it does not recreate the engine every frame.
3. Do not activate generated frames if the driver lacks VK_GOOGLE_display_timing. The previous unpaced fallback could present generated bursts; fallback uses ordinary real-frame presentation and logs the reason.
4. Clear stale NOVA_FPS_CAP when inheriting defaults. Keep the user's saved frame-generation, cap, sync, readback, and resolution selections.

## Sources

- shadPS4 `src/core/libraries/audio/sdl_audio_out.cpp`, blob `c9a34c805643e225fcab55807849c097f6935bd3`: actual-device format check and explicit front/center/surround fold. Copyright 2024–2026 shadPS4 Emulator Project, GPL-2.0-or-later. Nova adapts it for its existing channel gains and 12-channel input. https://github.com/shadps4-emu/shadPS4/blob/main/src/core/libraries/audio/sdl_audio_out.cpp
- SDL audio queue byte counts refer to input format, not converted output: https://wiki.libsdl.org/SDL3/SDL_GetAudioStreamQueued
- Android's frame-pacing documentation explains buffer stuffing and uneven presentation. Swappy is not integrated by this patch: https://developer.android.com/games/sdk/frame-pacing

## Validation and limits

Host C++20/UBSan tests compile the actual modified production PCM conversion function and exercise individual channel impulses, silence isolation, 8/12-channel layouts, per-channel/master gain, clipping, S16 conversion and native-stereo bypass. They also test exact 4K/1080p/portrait extents and thousands of bounded sizes. Existing presenter-order tests remain enabled, with the additional display-timing requirement. Android CI rebuilds the modified Kyty core and verifies/signs the APK using the existing fixed key.

No device performance or smoothness result exists for 0.9.66 yet. This change does not resolve all readback stalls, shader compilation, memory pressure, Super Meat Boy's native 2–4 FPS sections, or the unsupported swizzle error. It does not contain the unfinished full Kyty merge or the experimental Overdrive guest. Test real FPS with frame generation off before comparing generated output.
