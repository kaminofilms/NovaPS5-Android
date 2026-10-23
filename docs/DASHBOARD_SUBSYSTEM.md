# Original dashboard ingestion: experimental host subsystem

This adds compileable C++20 building blocks, not a booted Sony dashboard or a new APK feature. The existing APK/game path is untouched. The library is deliberately opt-in until firmware-specific import, IPC, runtime and database profiles are verified. No Sony code/assets/keys or third-party libraries are included.

## Build and check

Host dependencies: C++20 compiler, CMake 3.22+, SQLite3 development files, nlohmann_json 3.11+.

```
cmake -S native/dashboard -B build-dashboard -DCMAKE_BUILD_TYPE=Debug
cmake --build build-dashboard
ctest --test-dir build-dashboard --output-on-failure
```

The eight implementation files live at the requested src/core paths. CMake exports nova_dashboard. They use host APIs deliberately; they must not be registered as Sony guest symbols without ABI wrappers and verified NIDs.

## Implemented behavior

- Mount policy: read-only /system and /system_ex, writable /data, /user and /system_data; title-specific read-only pfsmnt mounts. Guest paths are bounded to mount roots; traversal and escaping symlinks are rejected. This is a resolver/policy, not a replacement for Kyty's entire VFS. All file operations must route through it (including rename/unlink/mkdir and already-open descriptors) before claiming enforcement. Concurrent hostile filesystem mutation requires descriptor-relative openat/openat2 handling; callers must keep the imported dump immutable while using this resolver.
- Explicit firmware profile supplies executable/library/bundle paths. No invented shell path is automatically launched. ELF64 x86-64 identification and RNPS classification produce a preflight report, not proof of ELF loadability, Hermes validity or runtime compatibility.
- Observed RNPS request layout: uint64 buffer, int32 size, int32 error, total 16 bytes. ioctl 0xc0105203 operates on an in-place buffer; the supplied specification's output-descriptor field does not exist in the inspected tool. Guest memory is copied through adapter callbacks; no guest pointer dereference occurs. The adapter supplies descriptor identity and maps host results to verified guest errno/status conventions. Encrypted/unknown inputs and absent verifiers never succeed. Recognized plaintext requires a real runtime verifier. Text/Hermes magic recognition alone is insufficient. This supplies no cryptographic decryption or JavaScript engine.
- ShellCore host model: bounded per-destination queues, configured user, explicit registry values, catalog checks and rollback-aware launch callback. Unknown values stay unknown. No undocumented IPMI packets, registry numeric IDs, app IDs, device graphics/audio operations or OOBE completion are fabricated. Existing UserService/SystemService functions already exist in the core and should be extended via verified adapters, not shadowed.
- Database scanner: bounded JSON, validated IDs, localized title/version, optional artwork/audio, symlink containment and duplicate reporting. Synchronizer uses an explicit verified schema profile, validates columns, creates a SQLite backup, binds metadata, and transactionally updates/inserts. It does not guess tbl_appbrowse schemas, delete unrelated rows, or synthesize an app.db. Work on a stopped/quiesced database. Adapter must refresh real firmware service caches and verify schema/triggers for the selected firmware. A backup path must be new and exclusively owned by the caller.

## Corrections to the supplied title map

The community RNPS map lists Home as NPXS40002, Control Center NPXS40003, Settings NPXS40008, Game Hub NPXS40033, JSCD NPXS40000 (libSceRnpsBundle.sprx), Shell UI 2 NPXS40087 and JavaScript launcher NPXS40141. It does not establish that NPXS40002 is a standalone SceShellUI ELF at the proposed path. These mappings remain research references, not a substitute for inspecting a specific dump.

## Remaining adapters before original dashboard bring-up

1. Inventory a readable dump, identify the real entry executable and dynamic imports, select its verified profile, and invoke the existing ELF loader.
2. Wire mounts and descriptor access policy into every Kyty file operation. Implement RNPS fd ownership and NovaFEX guest-memory callbacks.
3. Supply the matching RNPS engine/bridges and a verifier for its actual JS/Hermes version. Dispatch validated plaintext to that runtime.
4. Decode the shell's actual IPMI services, method numbers, buffers, status values and lifecycle. Bind the host service model through verified ABI wrappers. A host queue alone cannot satisfy a guest IPMI handshake.
5. Verify the selected firmware app.db schema and service cache behavior. Supply layout mappings, then test titles/launch transitions on a real shell. GPU device ioctls cannot be replaced with success returns.
6. Compile with Android dependencies, integrate the opt-in entry into the APK and test on device. The host workflow is not an APK build or shell boot test.

## References and provenance

- https://www.psdevwiki.com/ps5/RNPS
- https://github.com/zecoxao/decrypt_rnps/blob/master/source/main.c (observed request layout; inspected blob 80d7262dc1b260a13e4d3ffd9e53e3f9bcfe1e4c)
- https://www.psdevwiki.com/ps5/Param.json
- Base: kaminofilms/NovaPS5-Android perf/0952-eop-drain, 5474e56b15c4c243f22f763d38c48aeff0e30afc.

All code added here is original Nova host-side implementation. Synthetic tests cover malformed/encrypted bundles, guest bounds, read-only policy, traversal, queues, failed launch handoff, optional assets, JSON parsing and SQLite rollback. No proprietary dashboard has been executed.
