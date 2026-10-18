# Upstream port checkpoint — 2026-10-18

Nova parent: 7a9d0ade7c52a2a8575f62600ae0fd9287ddf9b9.
Kyty pin remains df5b9b92be7dfd463b47756b707d6d356a9f0550.
KytyPS5 inspected: 37df7f3278a41dde020a10daa74d8ae152ee8fb8.
KytyPlus inspected: dc5f5d98285e3a29302dd232e18a433fb7cfdf83.
AnyPS5 inspected: 9caecfd2d5a822be9daf84c69c7c33c7fafe52b9.

## Implemented in this checkpoint

1. Android UI/SAF -> native JNI -> supported PKG extraction -> atomic publication
   -> library insertion. Existing folder/ELF flow preserved.
2. Stream uncompressed PFS data and reject partial/truncated extraction. Bound
   PFSC memory and parser traversal. Full limitations: native/pkg/PORTING.md.
3. KytyPS5 FP16 signaling-NaN quiet-bit fix, applied to the existing Android
   source staging script without replacing the core or FEX. Exhaustive execution
   of the production classification IR: 131,072 encoding/lane combinations.
4. Dedicated source/parser/Android installer CI, with no APK generation.

## Latest-source review, not a full merge

KytyPS5 differs from Nova's pin across 170 src files (12,435 insertions and
3,330 deletions). KytyPlus comparison is recorded in KYTYPLUS-PORT-20261018.md.
The comparisons are change inventories, not a claim to have reviewed every line.

AnyPS5 is a desktop executable relinker, not an interchangeable Android ARM64
core. Inspected its DeferredLabels, WaitMemory and pipelined label-order tests.
Its batching depends on recorder, queued label table, guest-memory GPU lock and
completion-publication infrastructure that Nova does not share. Nova already
has a separate constant-EOP-label optimization. Copying AnyPS5's queue helpers
without adapting those dependencies would not be a valid performance port.
No new AnyPS5 GPU synchronization behavior is enabled in this checkpoint.

Other latest upstream shader/resource/loader/library updates are still pending
individual comparison against Nova's fully patched source and focused tests.
This checkpoint is not "all upstream updates merged".

## Validation and limits

Host parser/installer sanitizer tests include successful synthetic ELF installation,
truncated-payload refusal, path traversal rejection, raw-PFS false-success refusal
and nonempty-destination refusal. Java API compilation covers the edited launcher,
installer, library view and existing helper classes; the unchanged GameActivity
is represented only by its declaration. The complete APK is not built locally.
FP16 negative control: the original pin misclassifies quiet NaNs and fails the
exhaustive check; the port passes.

Only the dedicated no-APK workflow is authorized by this checkpoint's push.
No release workflow, APK build, version bump or device-speed claim is included.
No phone result demonstrates full speed. Future performance claims need same
scene, same-device gameplay FPS and readback/EOP timing comparisons.
