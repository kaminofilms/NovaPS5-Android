#!/usr/bin/env python3
"""Port KytyPS5 099de8d exact-word WRITE_DATA publication with Nova VA translation."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'src/graphics/guest_gpu/graphicsRun.cpp'
s=p.read_text()
a=s.index('#if defined(KYTY_NOVA_FEX)',s.index('void CommandProcessor::WriteData('))
b=s.index('\n}\n',a)
old=s[a:b]
if old.count('GuestMemory::Copy(dst, src,')!=1 or old.count('if (write_one_address)')!=1:
    raise SystemExit('WRITE_DATA publication anchor changed')
s=s[:a]+'''// Upstream 099de8d: a completion word may be reused immediately by its
	// consumer. Publish each word once; memcpy may perform overlapping stores.
	// Translate each dword separately so adjacent guest slots need not be
	// adjacent in host memory. Retain normal page protection/fault handling.
	const auto source = reinterpret_cast<uint64_t>(src);
	const auto target = reinterpret_cast<uint64_t>(dst);
#if defined(KYTY_NOVA_FEX)
	const auto last = *GuestMemory::Ptr<const uint32_t>(source + uint64_t{dw_num - 1} * 4, 4);
	NovaNoteGpuWrite(dst, last, static_cast<uint32_t>(m_interrupt_event_id), 'D');
#endif
	for (uint32_t i = 0; i < dw_num; ++i) {
		const auto offset = uint64_t{i} * sizeof(uint32_t);
		const auto word = *GuestMemory::Ptr<const uint32_t>(source + offset, sizeof(uint32_t));
		auto* output = GuestMemory::Ptr<uint32_t>(target + (write_one_address ? 0 : offset), sizeof(uint32_t));
		*static_cast<volatile uint32_t*>(output) = word;
	}'''+s[b:]
p.write_text(s)
print('PM4 WRITE_DATA: exact volatile dword stores; per-word guest translation; normal faults preserved')
