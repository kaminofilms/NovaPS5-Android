Experimental Nova PS5 Android ARM64 runtime build.

Nova's Java and native diagnostic code is compiled from source. The SHA-256-pinned DroidDeck Android session platform and full Kyty Windows core are verified dependencies; matching platform/core source is preserved in this repository. ARM64 Wine/FEX and the Linux root are installed from pinned upstream releases on first Play.

This automated package build does not verify PS5 game boot, Vulkan guest rendering or gameplay FPS on a physical device. The initial configuration targets 720p output and 60 Hz presentation.

CI uses a temporary development signing key. It differs from the preserved private key used for the APK delivered in chat, so a CI APK cannot update that installed application. No private signing key is stored in the repository.

First preparation needs about 1.4 GB of downloads and at least 6 GB free internally. No Steam login is required. Export Diagnostics after a boot attempt to capture preparation and session logs.
