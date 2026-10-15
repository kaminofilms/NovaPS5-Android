# Android AGC packet writes (0.9.21)

The 0.9.20 PPSA31162 run reached gameplay but reported 0.5–0.6 game FPS
in its late heartbeats. Native high-address access samples repeatedly named
AgcDcbCopyData and AgcDcbWaitRegMem. The available-memory readings also fell
below 1 GiB, and shader counts continued increasing. These observations do
not establish which cost dominates total frame time.

This build stages the copy and 32/64-bit wait packets in local arrays, then
writes the complete packet through NovaGuest::Copy. That helper translates
the destination and splits copies at guest slot boundaries. The original
guest command pointer is returned. Packet sizes, control fields, labels,
references, masks, poll intervals, and end markers remain identical. GPU
waits and completion ordering are retained.

The runtime overlay is applied after the 0.9.20 memory fast path, rather than
only editing the vendored source that the Android build does not compile.
test_agc_packet_fastpath.py compiles both the original vendor builders and
the patched builders, comparing 21,760 packet cases, plus allocation failure
and invalid-size cases. Synthetic inaccessible guest pointers cross into
noncontiguous slot backing through the production memory wrapper. Sentinel
checks detect writes beyond the allocated packet.

Retains the bundled Turnip driver and AnyPS5-derived adaptations from prior
versions. This change does not establish a fix for the reported visual
artifacts. Physical-device FPS gains, 30/60 FPS, and game compatibility
remain unverified until this APK is tested on the phone.
