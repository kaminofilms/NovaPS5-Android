# Guest fibers on the Android ARM64 host (0.9.68)

The Wolverine PPSA03671 session in wolvy.txt aborted in FiberRun with “Fiber context switching is only implemented on x86_64”. That error is in the previous-game section; the latest-game section is a different Hellblade run. The USB folder was successfully opened before the fiber failure.

The Android HLE now implements FiberRun, FiberSwitch and FiberReturnToThread with guest continuations. Its small x86-64 wrappers run under the existing NovaFEX translator. The native callbacks save the guest continuation using the established GetGuestCallContext API and return a tagged context pointer; the translated wrapper restores the guest registers, stack and floating-point controls. It never migrates a suspended ARM64/C++ call stack. No NovaFEX binary or translator recipe is changed.

The guest FiberObject remains its existing size. An untagged anonymous mapping stores each continuation (Android heap/emulated-TLS pointers can carry tags that guest x86 code cannot use), and reinitialization/finalization releases the old sidecar. Fibers retain the existing atomic ownership rules. A separate callback executes on the destination stack before publishing the departing fiber as idle, preventing another thread from resuming a still-active stack. Thread-local fiber ownership is refreshed on the resuming thread. Entry arguments, resume values, thread return values and termination/error results are carried through the original API. A naturally returning entry transitions to terminated and returns the existing STATE error.

The patch preserves the native x86-64 implementation. An ARM64 fiber without an explicit stack returns INVALID; dynamically supplying missing context storage is not implemented by this API surface. Stack and executable addresses remain guest addresses, including Nova guest-VA translated addresses. Shared-data copies use NovaGuest::Copy. Existing guest-pointer validation behavior is retained; this change does not make arbitrary corrupt guest pointers valid.

## Validation

The regression runner extracts the actual patched fiber definitions from libKernel.cpp and executes the exact production x86-64 wrapper bytes with a SysV gate adapter on the build host. It verifies Run/Switch/yield/resume, entry and resume arguments, returned values, nested-run/self-switch errors, termination, concurrent ownership rejection, MXCSR/x87 control words, callee-saved state and 64 migrations between host threads. It runs at O0/O2/O3 with UBSan. Assembly generation and immediate patch offsets are checked against switch.S. This harness substitutes the gate adapter; it does not claim to execute FEX or Wolverine.

CI builds the actual Android Kyty library, runs the existing ARM64 NovaFEX tests, checks external folder resolution, builds/signs the APK using the fixed key and verifies the APK and packaged driver. The 0.9.67 USB/SD changes remain included. The native log emits NOVA_FIBER when creating a translated switching wrapper.

Wolverine boot and gameplay require another device run. This resolves the observed x86-only fiber implementation gap; it does not establish that later game subsystems are supported. Hellblade’s separate startup hang and the other titles’ readback/performance stalls are not fixed by this patch.
