# Runtime approach and remaining work

The 0.2 preview translates the whole Windows/x86-64 Kyty process through the ARM64 Wine/FEX integration. This preserves Kyty's existing x86 guest-entry ABI, instruction patches and PS5 service code in the translated process rather than rewriting them as a new ARM64 backend. It still requires validation: translating ordinary Windows software does not establish correct Kyty guest signals, self-modifying code, memory mappings, PS5 services or shaders.

The Android side supplies folder access, installation, lifecycle, an in-app compositor, gamescope/Xwayland, Linux Vulkan/Turnip and controller routing through the pinned DroidDeck session platform. The bounded Nova integer-block translator is used only for diagnostics and is not the game CPU backend.

## Device-test milestones

1. Install the engine, launch its Kyty `--help` preflight through Wine/FEX, and examine `session.log`. Confirm executable permissions, FEX DLL integration and prefix initialization.
2. Check that a small redistributable guest or known-supported test reaches Kyty execution and its own Vulkan frame. Verify imported-module bindings, TLS, exception handling and code invalidation.
3. Use EverForward's actual boot log to identify unsupported SELF payloads, modules/services, guest instructions or shaders. Inspecting its title metadata cannot determine compatibility.
4. Validate Adreno's Linux Vulkan driver, feature requirements, image formats, subgroup behavior and synchronization. The Android diagnostic triangle does not test PS5 shader translation.
5. Verify audio, touch/hardware-pad mapping, pause/resume, storage access, saves and sustained memory use.
6. Measure game-produced frame rate and frame time before tuning. The 720p/60 Hz settings are targets only. Missing runtime correctness cannot be fixed by an FPS cap.

A future native ARM64 Kyty port would need backend-aware x86 entry, TLS/signals, memory protection, ABI callbacks and loader integration. The complete-process FEX route is a practical experiment, not evidence that those problems disappear.
