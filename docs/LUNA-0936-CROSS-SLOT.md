# Luna libc cross-slot load: device evidence and regression

The 2026-10-16 NX809J log reaches 959 game frames, with sampled game FPS
roughly 3–5.5, then faults at libc.prx+0x3fe8. This establishes rendered game
frames, not which scene was visible or that startup is fully fixed.

The exact guest bytes `c5 fa 6f 7e 70` decode as
`vmovdqu xmm7,[rsi+0x70]`. RSI is `0x903fffff83`, so the 16-byte read starts
at `0x903ffffff3`: 13 bytes before the guest slot boundary `0x9040000000`.
The preceding native instructions translate that start address with delta
`0xffffff8044000000`, giving host address `0x1083fffff3`. The native
`ldr q23,[x20]` therefore crosses into `0x1084000000`, the reported fault
address. Translation of only the first byte cannot represent this read when
adjacent guest slots have separate host backing windows.

The downstream FEX patch retains the complete guest address for 128-bit FPR
LoadMem and LoadMemTSO through a NovaLoad128 operation. Loads contained in one
slot retain a native vector load. Boundary loads translate each of 16 byte
addresses with acquire table reads, accumulate into reserved temporary vectors,
then commit the allocated vector. No native condition flags, allocated source
registers, guest pointers or stack state are changed. TSO vector-load barriers
are preserved. Missing/protected backing memory still faults at a byte read
mapped to the original guest RIP; no exception handler advances the PC.

This correction covers those 128-bit load operations. It does not claim to
solve cross-slot stores, 256-bit loads, paired/masked memory operations, or REP
bulk operations. SIMD/SVE/TSO store encodings and scalar watchpoints are untouched.

ARM64 tests use the exact Luna instruction and all 15 crossing alignments,
with a readable poisoned host neighbor that would silently return wrong data
under first-byte-only translation. They check output and ZF, plus separate
unmapped/protected next-slot runs checking a real SIGSEGV, unchanged output,
and the exact guest RIP. Both TSO configurations run in CI.

The pasted device log contains no constructor registration or store-intent
records. It does not identify a CheckpointName writer or establish the earlier
float-100 corruption's cause. The next device run must still provide startup
NOVA_LUNA_PROFILE/NOVA_LUNA_OBJECT messages, any NOVA_STORE_INTENT records,
and the complete next fault or successful scene progression.

Meat Boy reaches gameplay according to the device report, then logs 1.0–1.1
game FPS. The earlier 37.3 sample is not steady-state performance. Shader counts
continue rising and available memory falls to 772 MB. Repeated host-emulated
AgcCreatePrimState accesses are visible, but these counts are not timing data;
none alone establishes the bottleneck. No renderer optimization or FPS fix is
claimed by this memory-correctness patch. Preserve caches for a repeat capture.
