#!/usr/bin/env python3
"""Regression for delete-during-registration accounting."""
from pathlib import Path
import re
import sys

source = (Path(sys.argv[1]) / "src/graphics/presentation/videoOut.cpp").read_text()

remove = re.search(
    r"static void RemoveVideoOutEventQueue\(.*?\n\}(?=\n\nstatic void TriggerVideoOutEvents)",
    source,
    re.S,
)
register = re.search(
    r"static int RegisterVideoOutEvent\(.*?\n\}(?=\n\nstatic int DeleteVideoOutEvent)",
    source,
    re.S,
)
assert remove and register
assert "active_flip_registrations.fetch_add" not in source
assert "active_flip_registrations.fetch_sub" not in source
assert remove.group(0).count("active_flip_registrations.store") == 1
assert register.group(0).count("active_flip_registrations.store") == 2

# Publication must happen while the same mutex protecting the queue is held:
# once at insertion, and again on KernelAddEvent rollback. This closes the old
# callback-before-fetch_add window without changing KernelAdd/Delete/Trigger calls.
insert = register.group(0).index("queues.push_back(registration)")
publish = register.group(0).index("active_flip_registrations.store", insert)
unlock = register.group(0).index("\n\t}", publish)
kernel_add = register.group(0).index("KernelAddEvent", unlock)
assert insert < publish < unlock < kernel_add
assert "KernelTriggerEvent" not in remove.group(0)
assert source.count("KernelTriggerEvent(registration->handle") == 1
assert source.count("KernelAddEvent(eq, event)") == 1
assert source.count("KernelDeleteEvent(") >= 2

print("PASS 0989 flip-registration accounting has no callback underflow window")
