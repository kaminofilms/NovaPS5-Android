# Luna CheckpointName constructor evidence

Input supplied by the owner: eboot.bin, 142064429 bytes.
SHA256: `9c0d061401900fa708bad3ce580a326f7316e8920b593e541da308b39a24ee29`.
The binary itself is not included in the repository or CI artifacts.

The SELF magic is `54 14 f5 ee`. Its embedded ELF64 x86-64 header starts at
SELF file offset 0x1a0. Six block-bearing payload entries are readable and have
stored size equal to expanded size and their referenced program-header file
sizes. Reconstruction used the same `(type & 0x800)` and `(type >> 20) & 0xfff`
mapping as Kyty's Elf64::LoadSegment. No decryption or code execution occurred.
The section header offset 0x3503ac00 lies outside this supplied file; the section
table is not available. Program headers and PT_DYNAMIC remain usable.

All addresses below are module-relative ELF virtual addresses. The loader adds
the actual module base; no fixed guest load address is assumed.

| Evidence | RVA |
| --- | --- |
| DT_INIT | 0x10 |
| Legacy constructor table endpoint referenced by DT_INIT | 0x75c8928 |
| ASCII CheckpointName literal | 0x67ba62c |
| UTF-16LE SaveGameInstanceData class name | 0x6663e2e |
| CheckpointName reflected property descriptor | 0x6f107c8 |
| Property pointer array | 0x6f112b0 |
| Pointer-array entry referencing CheckpointName descriptor | 0x6f112c8 |
| Class metadata pointer to property array | 0x6f114b8 |
| Class-registration routine | 0xf2f990 |
| Typed placement-constructor wrapper | 0xf2fc80 |
| Constructor first derived vtable store / registration boundary | 0xf2fca3 |
| Original 16-byte CheckpointName initialization store | 0xf2fca6 |
| Expected class vtable | 0x6f114f0 |
| Destructor implementation | 0xf3b5b0 |
| Destructor first vtable store / retirement boundary | 0xf3b5c4 |

DT_INIT_ARRAYSZ and DT_PREINIT_ARRAYSZ are both zero. DT_INIT disassembly walks
a legacy constructor-pointer table in reverse until a -1 sentinel. A search
limited to .init_array would not identify this constructor chain.

There are 739314 R_X86_64_RELATIVE relocations, 9150 R_X86_64_64, 23
R_X86_64_GLOB_DAT and 2346 R_X86_64_JUMP_SLOT entries. The CheckpointName literal
has ten relative relocation references, so its string address alone does not
select a unique object type. The descriptor at 0x6f107c8 is selected because its
encoded member offset is 0x38, and the property array ties it to the class whose
registration passes the SaveGameInstanceData name and constructor pointer.

Neighboring descriptors encode GameFlowVersionID +0x28, Day +0x2c, Stage +0x30,
CheckpointName +0x38 and CheckpointIndex +0x48. The class registration sets
object size 0x148 and alignment 8. Descriptor field decoding here is limited to
the confirmed non-boolean members; boolean descriptor layouts differ.

The constructor loads RBX from [RDI], passes that object to the base constructor,
then loads RAX with the class vtable. At 0xf2fca3 it stores RAX to [RBX]. At
0xf2fca6 it performs the original guest instruction
`vmovups xmmword ptr [rbx + 0x38], xmm0`, after zeroing xmm0. This initializes
the string's pointer/count/capacity together. This is original game code, not
an emulator-injected initialization or a fix for the reported corruption.

At the constructor boundary the callback uses spilled guest RBX as the object
and guest RAX as the expected vtable. It does not dereference the object or
FObjectInitializer. At the destructor boundary guest RDI is the object and RAX
is the same vtable. Retirement changes only the registry's atomic state; retired
slots are never reclaimed or silently reused. The existing 16-slot limit stays
bounded and a full registry is explicitly logged.

Runtime setup is restricted to main modules of PPSA36257 and checks six
independent spans: constructor bytes, class-registration bytes, UTF-16 class
name, ASCII property name, property-layout flags/offset and destructor bytes.
These checks are a version-specific code/layout signature, not a runtime hash
of the complete input. Unknown signatures reject without arming. Safe kernel
copies inspect only spans bounded inside the already mapped module.

The initialization instruction is SIMD. Production enables TSO. Neither SIMD
nor StoreMemTSO has been added to scalar tracing. Constructor-boundary
registration works independently of those store paths. A device trace can
therefore establish registration without necessarily capturing every later
writer. Do not disable TSO or broaden instrumentation silently.

This evidence establishes a type-specific registration site, not a live device
object address or the corrupting writer. Device logs must still show profile
acceptance, object registration and relevant NOVA_STORE_INTENT records before
attributing the reported 0x42c80000 value to an instruction or claiming a fix.

Reproduce read-only analysis with:

```bash
python3 -m pip install numpy capstone
python3 tools/analysis/inspect_luna_elf.py /path/to/eboot.bin --xrefs --output luna-inspection.json
```

The tool marks code references as candidate instruction boundaries and reports
its unsupported relocation variants. It does not execute, decrypt or modify
the supplied executable, and does not publish the executable.

Dynamic-symbol cross-check: DT_HASH reports 2375 symbols and 2375 buckets.
Searching their names for register/construct/checkpoint/factory/savegame found
no descriptive matches. Examples are NID-style names such as bzQExy189ZI#3#1.
The class identity above therefore comes from metadata linkage and instruction
operands, not an invented exported constructor symbol.

The resulting typed registration/lifetime integration passed Android ARM64
runtime tests and was released in NovaPS5 0.9.36 at source commit
55ad2a60abbedfa3f2df3002d5530908ca234a57, CI run 38890414120. This is not proof
that the full game booted or that the corrupting writer has been identified.
