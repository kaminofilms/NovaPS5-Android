#!/usr/bin/env python3
"""Bound native views at measured guest-access sites; retain guest addresses."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
def once(s,a,b):
    if s.count(a)!=1: raise SystemExit(f'NOVA_ACCESS: anchor count {s.count(a)}: {a[:90]}')
    return s.replace(a,b,1)
p=root/'src/libs/agc.cpp';s=p.read_text()
s=once(s,'return Pm4::PacketSizeDw(packet[0]);','return Pm4::PacketSizeDw(*GuestMemory::Ptr(packet, sizeof(*packet)));')
start=s.index('int KYTY_SYSV_ABI AgcSetPacketPredication(');end=s.index('\n}',start)
b=s[start:end];b=once(b,'\tLOGF("\\t packet0', '\tpacket = GuestMemory::Ptr(packet, sizeof(*packet));\n\tLOGF("\\t packet0');s=s[:start]+b+s[end:]
s=once(s,'\t\tconst auto cmd_id = packet[0];\n\t\tpacket[0]         = (cmd_id & ~1u) | predication_bit;', '\t\tauto* view = GuestMemory::Ptr(packet, sizeof(*packet));\n\t\tconst auto cmd_id = view[0];\n\t\tview[0] = (cmd_id & ~1u) | predication_bit;')
start=s.index('static uint32_t* get_agc_wait_packet(');end=s.index('\n}',start)+2
s=s[:start]+'''static uint32_t* get_agc_wait_packet(uint32_t* cmd) {
    if (cmd == nullptr) return nullptr;
    const auto header = *GuestMemory::Ptr(cmd, sizeof(*cmd));
    if (KYTY_PM4_LEN(header) != AGC_WAIT_USER_DATA_BEGIN_DW ||
        !AgcIsInternalDataPacket(header, cmd + 1)) return nullptr;
    const auto* view = GuestMemory::Ptr(cmd, uint64_t{4} * sizeof(*cmd));
    auto* wait = cmd + AGC_WAIT_USER_DATA_BEGIN_DW;
    const auto wait_header = *GuestMemory::Ptr(wait, sizeof(*wait));
    const auto op = (wait_header >> 8u) & 0xffu;
    const auto len = KYTY_PM4_LEN(wait_header);
    const auto tag = view[2] & 0xffff0000u;
    if (KYTY_PM4_R(wait_header) != 0u ||
        !((op == Pm4::IT_WAIT_REG_MEM && len == 7u && tag == AGC_WAIT_USER_DATA_BEGIN_32_TAG) ||
          (op == Pm4::IT_WAIT_REG_MEM_64 && len == 9u && tag == AGC_WAIT_USER_DATA_BEGIN_64_TAG))) return nullptr;
    return wait; // original guest pointer, used by packet patchers
}'''+s[end:]
s=once(s,'KYTY_PM4_R(cmd_id) != 1u || payload[0] != AGC_INTERNAL_DATA_REGISTER)', 'KYTY_PM4_R(cmd_id) != 1u)')
s=once(s,'\tconst auto size_dw = KYTY_PM4_LEN(cmd_id);\n\tif (size_dw == AGC_WAIT_USER_DATA_BEGIN_DW)', '\tpayload = GuestMemory::Ptr(payload, sizeof(*payload));\n\tif (payload[0] != AGC_INTERNAL_DATA_REGISTER) return false;\n\tconst auto size_dw = KYTY_PM4_LEN(cmd_id);\n\tif (size_dw != AGC_WAIT_USER_DATA_BEGIN_DW && size_dw != AGC_INTERNAL_DATA_PACKET_SIZE_DW) return false;\n\tpayload = GuestMemory::Ptr(payload + 1, sizeof(*payload));\n\tif (size_dw == AGC_WAIT_USER_DATA_BEGIN_DW)')
# payload now points at tag. Translate from the original address separately to
# retain the slot-crossing fallback; never advance a native alias across a slot.
start=s.index('bool AgcIsInternalDataPacket(');end=s.index('\n}',start)
b=s[start:end].replace('payload = GuestMemory::Ptr(payload, sizeof(*payload));','const auto* guest_payload = payload;\n\tpayload = GuestMemory::Ptr(payload, sizeof(*payload));').replace('GuestMemory::Ptr(payload + 1,','GuestMemory::Ptr(guest_payload + 1,').replace('payload[1]','payload[0]');s=s[:start]+b+s[end:]
start=s.index('int KYTY_SYSV_ABI AgcCreateShader(');end=s.index('\n}',start)
b=s[start:end]
b=once(b,'auto* h = static_cast<Shader*>(header);','auto* h = GuestMemory::Ptr(static_cast<Shader*>(header), sizeof(Shader));')
b=once(b,'auto update_addr = [](auto& m)', 'auto update_addr = [](auto& m, uintptr_t guest_base, const void* native_base)')
b=once(b,'reinterpret_cast<uintptr_t>(m) + reinterpret_cast<uintptr_t>(&m)', 'reinterpret_cast<uintptr_t>(m) + guest_base +\n\t\t\t    (reinterpret_cast<uintptr_t>(&m) - reinterpret_cast<uintptr_t>(native_base))')
for field in ['cx_registers','sh_registers','user_data','specials','input_semantics','output_semantics']:
    b=once(b,f'update_addr(h->{field});',f'update_addr(h->{field}, reinterpret_cast<uintptr_t>(header), h);')
b=once(b,'if (h->user_data != nullptr) {','if (h->user_data != nullptr) {\n\t\tauto* data = GuestMemory::Ptr(h->user_data, sizeof(ShaderUserData));')
for field in ['direct_resource_offset']+[f'sharp_resource_offset[{i}]' for i in range(4)]:
    b=once(b,f'update_addr(h->user_data->{field});',f'update_addr(data->{field}, reinterpret_cast<uintptr_t>(h->user_data), data);')
b=once(b,'*dst = h;', '*GuestMemory::Ptr(dst, sizeof(*dst)) = static_cast<Shader*>(header);')
s=s[:start]+b+s[end:]
s=once(s,'\tfor (auto lo_index = 0u; lo_index < num_regs; lo_index++) {','\tregs = GuestMemory::Ptr(regs, uint64_t{num_regs} * sizeof(*regs));\n\tfor (auto lo_index = 0u; lo_index < num_regs; lo_index++) {')
p.write_text(s)
p=root/'src/graphics/guest_gpu/graphicsRun.cpp';s=p.read_text()
s=once(s,'const auto* results = reinterpret_cast<const volatile uint64_t*>(address);','const auto* results = reinterpret_cast<const volatile uint64_t*>(\n\t\t\t    GuestMemory::Ptr<uint64_t>(reinterpret_cast<uint64_t>(address), 32u * sizeof(uint64_t)));')
s=once(s,'value = *reinterpret_cast<const volatile uint64_t*>(address);','value = *reinterpret_cast<const volatile uint64_t*>(\n\t\t\t    GuestMemory::Ptr<uint64_t>(reinterpret_cast<uint64_t>(address), sizeof(uint64_t)));')
p.write_text(s)
print('NOVA_ACCESS: native wait validation, predication and shader relocation; guest ABI retained')
