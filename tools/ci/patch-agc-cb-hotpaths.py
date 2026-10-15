#!/usr/bin/env python3
"""Optimize measured 0.9.24 AGC hot paths, keeping every guest ABI pointer unchanged.

Apply AFTER all existing AGC native packet overlays. Exact anchors intentionally
fail closed if the upstream AGC implementation changes.
"""
from pathlib import Path
import sys

source = Path(sys.argv[1]) / "src/libs/agc.cpp"
original = source.read_text()
s = original

def replace_once(before: str, after: str, label: str) -> None:
    global s
    count = s.count(before)
    if count != 1:
        raise SystemExit(f"NOVA_AGC_PERF: {label}: expected one anchor, got {count}")
    s = s.replace(before, after, 1)

# All CommandBuffer fields stay guest-side. Only internal accesses use an
# in-slot native alias. This method can also be invoked on an already-native
# alias by allocate_guest_packet; translation is a no-op in that case.
replace_once(
    """\t[[nodiscard]] KYTY_SYSV_ABI uint64_t GetAvailableSizeDW() const {
\t\t// Interpret the signed cursor distance as an unsigned 64-bit DWORD count.
\t\tconst auto distance = static_cast<int64_t>(reinterpret_cast<uintptr_t>(cursor_down) -
\t\t                                           reinterpret_cast<uintptr_t>(cursor_up));
\t\tconst auto available = static_cast<uint64_t>(distance >> 2);
\t\tif (available <= reserved_dw) {
\t\t\treturn 0;
\t\t}
\t\treturn available - reserved_dw;
\t}""",
    """\t[[nodiscard]] KYTY_SYSV_ABI uint64_t GetAvailableSizeDW() const {
\t\t// The guest-owned CommandBuffer is hot: read all cursor fields from
\t\t// one native alias to avoid multiple ARM64 host fault roundtrips.
\t\tconst auto* state = GuestMemory::Ptr(this, sizeof(CommandBuffer));
\t\tconst auto distance = static_cast<int64_t>(reinterpret_cast<uintptr_t>(state->cursor_down) -
\t\t                                           reinterpret_cast<uintptr_t>(state->cursor_up));
\t\tconst auto available = static_cast<uint64_t>(distance >> 2);
\t\tif (available <= state->reserved_dw) {
\t\t\treturn 0;
\t\t}
\t\treturn available - state->reserved_dw;
\t}""",
    "CommandBuffer::GetAvailableSizeDW",
)
replace_once(
    """\tKYTY_SYSV_ABI bool ReserveDW(uint32_t num_dw) {
\t\tconst uint64_t remaining = GetAvailableSizeDW();
\t\tif (num_dw > remaining) {
\t\t\tif (callback == nullptr) {""",
    """\tKYTY_SYSV_ABI bool ReserveDW(uint32_t num_dw) {
\t\tconst uint64_t remaining = GetAvailableSizeDW();
\t\tif (num_dw > remaining) {
\t\t\tauto* state = GuestMemory::Ptr(this, sizeof(CommandBuffer));
\t\t\tif (state->callback == nullptr) {""",
    "CommandBuffer::ReserveDW alias",
)
# Limit substitutions to the ReserveDW function only (not other uses of callback).
begin = s.index("\tKYTY_SYSV_ABI bool ReserveDW(uint32_t num_dw) {")
end = s.index("\n\tKYTY_SYSV_ABI uint32_t* AllocateDW", begin)
method = s[begin:end]
assert method.count("reserved_dw") == 7, f"Unexpected ReserveDW fields: {method.count('reserved_dw')}"
assert method.count("bool result = callback(this, num_dw + reserved_dw, user_data);") == 1
method = method.replace("bool result = callback(this, num_dw + reserved_dw, user_data);",
                        "// Callback must receive the ORIGINAL guest pointer, never the host alias.\n"
                        "\t\t\tbool result = state->callback(this, num_dw + state->reserved_dw, state->user_data);")
method = method.replace(", reserved_dw);", ", state->reserved_dw);")
# A grow callback may update the guest object in place. Re-evaluate its contents.
# state is an alias of that storage, not a snapshot.
s = s[:begin] + method + s[end:]

replace_once(
    """\t\tauto* ret_ptr = cursor_up;
\t\tcursor_up += size_dw;
\t\treturn ret_ptr;
\t}""",
    """\t\t// The cursor value and returned packet pointer remain GUEST addresses.
\t\t// Only the cursor fields are accessed through an in-slot host alias.
\t\tauto* state = GuestMemory::Ptr(this, sizeof(CommandBuffer));
\t\tauto* ret_ptr = state->cursor_up;
\t\tstate->cursor_up += size_dw;
\t\treturn ret_ptr;
\t}""",
    "CommandBuffer::AllocateDW",
)

# A 5-DWORD native PM4 register packet is entirely contained in almost all
# slots. Native HLE helpers can patch it without trapping once per DWORD.
# Guest packet addresses must remain unchanged in all callers.
replace_once(
    """static bool is_native_reg_indirect_packet(const uint32_t* cmd, RegIndirectPacket type) {
\treturn ((cmd[0] >> 8u) & 0xffu) == reg_indirect_native_op(type);
}""",
    """static bool is_native_reg_indirect_packet(const uint32_t* cmd, RegIndirectPacket type) {
\tconst auto* view = GuestMemory::Ptr(cmd, uint64_t {5} * sizeof(uint32_t));
\treturn ((view[0] >> 8u) & 0xffu) == reg_indirect_native_op(type);
}""",
    "native indirect packet discriminator",
)

# Alias within each bounded helper so read/write operations share one native view.
for signature in [
    """static void reg_indirect_write_packet(uint32_t* cmd, uint64_t vaddr, uint32_t num_regs,
                                      RegIndirectPacket type) {""",
    """static int reg_indirect_patch_set_address(uint32_t* cmd, uint64_t vaddr, RegIndirectPacket type) {
\tEXIT_NOT_IMPLEMENTED(cmd == nullptr);""",
    """static int reg_indirect_patch_set_num_registers(uint32_t* cmd, uint32_t num_regs,
                                                RegIndirectPacket type) {
\tEXIT_NOT_IMPLEMENTED(cmd == nullptr);""",
    """static int reg_indirect_patch_add_registers(uint32_t* cmd, uint32_t num_regs,
                                            RegIndirectPacket type) {
\tEXIT_NOT_IMPLEMENTED(cmd == nullptr);""",
]:
    replace_once(signature, signature + "\n\tcmd = GuestMemory::Ptr(cmd, uint64_t {5} * sizeof(uint32_t));", signature.split("(")[0].strip())

# Indirect-buffer rewrite uses exactly 4 DWORDs, with the target address encoded
# as a GUEST address; only cmd accesses can be translated.
replace_once(
    """\tEXIT_NOT_IMPLEMENTED(cmd == nullptr);

\tauto op = (cmd[0] >> 8u) & 0xffu;
\tif (op != Pm4::IT_INDIRECT_BUFFER) {""",
    """\tEXIT_NOT_IMPLEMENTED(cmd == nullptr);
\tcmd = GuestMemory::Ptr(cmd, uint64_t {4} * sizeof(uint32_t));

\tauto op = (cmd[0] >> 8u) & 0xffu;
\tif (op != Pm4::IT_INDIRECT_BUFFER) {""",
    "AgcUnknownIkfdtRIqCE indirect buffer rewrite",
)

source.write_text(s)
print("NOVA_AGC_PERF: translated command-buffer cursor and indirect PM4 register-patch hot paths")
