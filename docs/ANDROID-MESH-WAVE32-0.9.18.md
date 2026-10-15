# Nova PS5 0.9.18: mesh wave64 packing

The 0.9.17 device test loaded the compute-mesh driver, but PPSA31162 stopped at
the host workgroup limit: 192 invocations, 192 output vertices, 64 primitives,
2176 LDS dwords. The pinned driver allows 128 invocations per mesh workgroup.

Kyty already supports executing two guest wave64 halves per invocation on a
host subgroup of 32, including mesh outputs and logical local invocation IDs.
0.9.18 selects that path when a native 64-wide subgroup exceeds the host limit
and a required 32-wide subgroup fits. The reported draw then uses 96 physical
invocations for all 192 guest invocations. Output counts and LDS are unchanged.

The device must advertise subgroupSizeControl, the mesh stage in
requiredSubgroupSizeStages, and a range containing 32. The Vulkan feature is
enabled at device creation and the mesh pipeline requests the same subgroup
size used by the compiler. The existing static shader key includes that size.
All original invocation, output and LDS limit checks remain active.

The host regression compiles the actual selector header, tests the reported
192-thread case, supported/unsupported limits and feature gates, and verifies
the two-half logical index mapping covers every guest lane exactly once.
CI applies the patch to the real Android build sources before testing/building.
Game rendering remains unverified until another physical-device test.
