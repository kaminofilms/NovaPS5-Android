#!/usr/bin/env python3
"""Fill controller packets locally, then publish through the guest copy helper."""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/libs/controller.cpp'
s = p.read_text()
assert 'NOVA_CONTROLLER_OUTPUT' not in s, 'controller patch already applied'
anchor = '#include "common/common.h"'
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + '\n#include "common/guestMemory.h"')
start = s.index('static void pad_fill_data(')
end = s.index('\n}\n', start) + 2
body = s[start:end]
anchor = '\tEXIT_IF(data == nullptr);'
assert body.count(anchor) == 1
body = body.replace(anchor, anchor + '''

	// NOVA_CONTROLLER_OUTPUT: do not fault once per field on a high guest pointer.
	// The original packet initializer clears every byte, including padding.
	auto* const guest_output = data;
	PadData local_output;
	data = &local_output;''')
assert body.endswith('\n}')
body = body[:-2] + '''
	// Copy also handles a packet spanning separately backed guest VA slots.
	// Do not substitute a direct host view: the 120-byte packet may cross a slot.
	GuestMemory::Copy(guest_output, &local_output, sizeof(local_output));
}'''
s = s[:start] + body + s[end:]
p.write_text(s)
