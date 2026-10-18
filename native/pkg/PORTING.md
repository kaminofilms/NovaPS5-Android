# KytyPlus package parser: isolated port, not yet enabled in the Android app

Source: Coder787-source/KytyPlus at dc5f5d98285e3a29302dd232e18a433fb7cfdf83 (main inspected 2026-10-18).
License: GPL-2.0; full upstream license retained in LICENSE.

This directory ports the PKG/PFS parser into a standalone C++20 module. It does
not replace Nova's core, change FEX, register Android imports, or install games.
It is intentionally not linked into the production APK yet.

Changes from upstream:
- Emulator-independent stderr logging adapter.
- Fix dangling local-array pointer in executable-recovery header inspection.
- Refuse raw-body-only results and heuristic carved-file recovery as successful
  installations. Recovering eboot.bin alone does not reconstruct a game filesystem.
- Fix a printf argument type and a synthetic fixture string-copy length.
- Add a negative regression for an invalid PFS body being reported as installed.

Local validation: direct g++ C++20 build with ASan + UBSan and return-local-address
and printf-format diagnostics treated as errors. LeakSanitizer is disabled because
this runner does not permit its process/thread inspection. No leak result claimed.
CMake configuration is provided but CMake was unavailable locally.

Remaining gates before Android UI activation:
- Bound memory use and implement streaming extraction for large files. The source
  reserves whole file/PFSC buffers; it is not ready for phone-sized memory budgets.
- Refuse truncated/partial extraction; upstream counts some incomplete writes.
- Audit finalized-image/PFS scanner offsets, nested block traversal and symlinks.
- Register supported decompression backends explicitly; do not load desktop DLLs.
- Private staging, storage-space checks, cancellation, atomic install publication,
  and title-aware update handling without overwriting saves or shader caches.
- Android NDK build, SAF importer/library integration and device validation.

Encrypted retail data is not decrypted by this module. Synthetic parser tests do
not establish real-package compatibility, game boot success or improved FPS.
