# Native AvPlayer worker entry routing

The owner's Hollow Knight trace (`PPSA34971`, 0.9.44) faults in all three native
AvPlayer workers: video decoder, audio decoder and demuxer. The reported guest
RIPs are outside the listed guest ELF modules, and their instruction bytes match
ARM64 function prologues. The source identifies a matching routing defect:
`Source::CreateWorker` sends C++ entry functions through `PthreadCreate`, whose
ARM64 `RunOnGuestStack` unconditionally invokes `NovaFex::CallGuest`. FEX then
decodes native ARM64 instructions as x86-64.

0.9.46 adds an internal `PthreadCreateNative` API used by AvPlayer workers. Its
explicit per-thread entry flag selects a direct native call on ARM64. Public
guest pthread creation always resets that flag to false and still invokes
NovaFEX. No address-range guess or global native bypass is introduced.

Both modes retain guest-stack and FS-base setup, registered thread identity,
exit unwinding, cleanup, join and stack retirement. This allows a native worker
to use the existing bridge when it needs to call guest code. The native creation
API is not registered as a guest import. AvPlayer's decoding, audio and video
logic is retained; movie playback is not skipped.

Tests execute the production ARM64 entry branch and creation wrappers with a
controlled guest-call interface. They check that native function pointers never
reach the x86-64 interface, guest entries do, nested bridge calls retain stack
and TLS setup, guest creation resets native mode on reuse, native and guest exit
paths unwind correctly, and three workers operate with thread-local state.
Normal and address/undefined-behavior sanitizer runs are required before the
Android compilation. These are routing regressions, not device gameplay tests.

The Ever Forward change from 0.9.45 remains included. There is no Dead Cells
performance change in this patch: the supplied crash report is Hollow Knight's
log and cannot establish the cause of Dead Cells' separately reported slowdown.
Hollow Knight's next loading stage and Ever Forward's FPS still require a
device trace; a successful build does not establish that either game is fixed.

PKG installation also enables plaintext superblock-first FIH containers. The
installer retains exact file-size/path/ELF checks and refuses data-first images
before invoking the recovery scanner. PFS image copying now detects incomplete
reads and failed writes. Package fixtures cover ordinary and finalized installs,
out-of-segment superblocks, truncation, and refusal without staging writes.
Encrypted and data-first finalized packages are not supported by this change.
