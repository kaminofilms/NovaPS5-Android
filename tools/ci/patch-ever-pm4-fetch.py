#!/usr/bin/env python3
"""Fetch exact PM4 bytes coherently without faulting on adjacent GPU label pages."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);p=root/'src/graphics/guest_gpu/graphicsRun.cpp';s=p.read_text()
def edit(old,new):
 global s
 if s.count(old)!=1: raise SystemExit('NOVA_PM4_FETCH: changed anchor: '+old[:90])
 s=s.replace(old,new,1)
edit('\treturn {GuestMemory::Ptr(commands.data(), commands.size_bytes()), commands.size()};',
     '\t// Keep guest identity for exact coherent fetches; translating here loses it.\n'
     '\tif (NovaRender::EverProfile()) return commands;\n'
     '\treturn {GuestMemory::Ptr(commands.data(), commands.size_bytes()), commands.size()};')
helper='''// Copy one packet, not its protected page or the remainder of the command list.
// TryReadBufferBacking waits only for GPU-dirty bytes that intersect these bytes.
// Adjacent label writes must not make the parser download an otherwise clean packet.
static const uint32_t* NovaReadPm4Packet(const uint32_t* guest, uint32_t remaining,
                                        std::vector<uint32_t>& scratch) {
	NovaRender::Scope nova_packet_cost(NovaRender::Cost::Pm4Fetch);
	EXIT_IF(remaining == 0);
	const auto address = reinterpret_cast<uint64_t>(guest);
	uint32_t header = 0;
	EXIT_IF(!LibKernel::Memory::TryReadBufferBacking(address, &header, sizeof(header)));
	const auto count = header == 0x80000000u ? 1u : Pm4::PacketSizeDw(header);
	EXIT_IF(count == 0 || count > remaining);
	scratch.resize(count);
	scratch[0] = header;
	if (count > 1 && ((header >> 8u) & 0xffu) == Pm4::IT_NOP &&
	    KYTY_PM4_R(header) == Pm4::R_ZERO) {
		EXIT_IF(!LibKernel::Memory::TryReadBufferBacking(address + 4, &scratch[1], 4));
		// CpOpNop consumes only the first payload word for ordinary padding.
		// Marker/custom NOPs retain full payload reads and their side effects.
		if ((scratch[1] & 0xffff0000u) != 0x68750000u) return scratch.data();
	}
	if (count > 1) {
		EXIT_IF(!LibKernel::Memory::TryReadBufferBacking(
		    address + sizeof(header), scratch.data() + 1, uint64_t(count - 1) * sizeof(header)));
	}
	return scratch.data();
}

'''
edit('void CommandProcessor::ProcessPm4(Pm4Execution& execution) {',helper+'''void CommandProcessor::ProcessPm4(Pm4Execution& execution) {
	std::vector<uint32_t> nova_packet;
	if (NovaRender::EverProfile()) nova_packet.reserve(64);''')
edit('''		const auto* const packet        = cursor.commands.data() + cursor.offset_dw;
		const auto        total_dw      = static_cast<uint32_t>(cursor.commands.size());
		const auto        remaining_dw  = total_dw - cursor.offset_dw;''','''		const auto        total_dw      = static_cast<uint32_t>(cursor.commands.size());
		const auto        remaining_dw  = total_dw - cursor.offset_dw;
		const auto* const guest_packet  = cursor.commands.data() + cursor.offset_dw;
		const auto* const packet = NovaRender::EverProfile()
		    ? NovaReadPm4Packet(guest_packet, remaining_dw, nova_packet) : guest_packet;''')
# Diagnostics retain the real command-list identity; never subtract a cursor
# offset from the temporary packet allocation.
edit('reinterpret_cast<uint64_t>(packet - offset), total_dw, offset,',
     'reinterpret_cast<uint64_t>(cursor.commands.data()), total_dw, offset,')
edit('auto* const base       = packet - offset;',
     'auto* const base       = GuestMemory::Ptr(cursor.commands.data(), cursor.commands.size_bytes());')
bp=root/'src/graphics/host_gpu/renderer/cache/bufferCache.cpp'
bs=bp.read_text()
anchor='\tNovaRender::Scope nova_cost(NovaRender::Cost::Readback);'
if bs.count(anchor)!=1: raise SystemExit('NOVA_PM4_FETCH: readback attribution anchor changed')
bs=bs.replace(anchor,anchor+'\n\tNovaRender::Scope nova_origin_cost(is_write ? NovaRender::Cost::ReadbackWrite : NovaRender::Cost::ReadbackRead);',1)
p.write_text(s)
bp.write_text(bs)
print('NOVA_PM4_FETCH: Ever-only exact coherent packet copies avoid adjacent-label page faults')
