# Linux Kyty / FEX Android runtime

Active path: Nova Android → pinned DroidDeck linuxfs-r9 → standalone FEX 2610 → pinned Linux Kyty df5b9b9. Wine and Proton are absent from this launch path. Existing Windows files and the ps5-boot-api branch are retained.

The Linux executable is taken from successful run 38324155342 / commit 802adeb479110a76b590a0f56747b41c049b3adb. Its SHA-256 is e594d71bb9c60ff47d2ac1e1ee4b9c21eca7ad1ba949d1943a7644eabc2f846c. The executable interpreter is /lib64/ld-linux-x86-64.so.2; DT_NEEDED lists libm.so.6, libstdc++.so.6, libgcc_s.so.1 and libc.so.6.

runtime-linux/dependencies.json pins public FEX PPA and Ubuntu Noble package URLs and SHA-256 values. Package copyrights are preserved within the runtime. FEX source is MIT licensed and pinned to 14c92681f4d62cf84d901460e0358de09c8847a7. Ubuntu library source packages are available from the corresponding Ubuntu archive source indexes. DroidDeck source and licensing remain in this repository.

FEX executes inside DroidDeck's existing ARM64 Linux/proot environment. Guest libraries live in opt/novaps5/linux-runtime/guest; host FEX binaries and thunks live separately under linux-runtime/host. Vulkan and audio thunks forward calls to the host libraries; the ARM64 ICD is consumed by the ARM64 host Vulkan loader, never directly by the x86 loader. x86 X11 libraries communicate with the existing compositor over its display socket.

The installer checks every regular runtime file and core checksum, stages updates, retains the previous runtime until publication, installs permissions, and keeps writable Kyty configuration directories. The selected game remains a Linux /storage path without Windows drive conversion. The boot log captures stages A-D, a fixed-address memory diagnostic with errno, Vulkan physical-device enumeration, then the stage E game attempt and process exit status. Stages F and G require actual guest execution and rendered-frame evidence.

The supplied Linux core's memory implementation scans occupied mappings and attempts fixed non-replacing reservations. No unproven guest-pointer remapping or core memory changes are applied. The separate memory diagnostic records page size and errno for a guest-range reservation; it does not assert the core is compatible with Android's available virtual address space.

CI verifies the APK and runs FEX A-D on an ARM64 Linux runner. This is not Android hardware evidence. Neither Dead Cells guest execution nor gameplay is claimed. On the Red Magic device, select the extracted PPSA15552 folder, press Play, then export Diagnostics and the session boot log after the first attempt. Preserve the first failure and all prior NOVA_STAGE lines.

The CI APK uses a new temporary development signing identity. Back up app data before uninstalling an existing differently signed build; existing runtime installation may otherwise be lost. Future releases should use the user's persistent signing secret when available.
