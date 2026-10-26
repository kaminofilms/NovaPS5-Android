#!/usr/bin/env python3
"""Make flip-registration telemetry a mutex-protected projection of the queue."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
source = root / "src/graphics/presentation/videoOut.cpp"
if not source.is_file():
    raise SystemExit("0989: videoOut.cpp is missing")

text = source.read_text()
if "active_flip_registrations.fetch_sub" not in text or text.count(
    "active_flip_registrations.fetch_add"
) != 1:
    raise SystemExit("0989: expected post-0987 registration telemetry exactly once")

replacements = (
    (
        """\tif (entry != queues.end()) {
\t\tqueues.erase(entry);
\t\tif (registration->kind == VideoOutEventKind::Flip) {
\t\t\tstate->active_flip_registrations.fetch_sub(1, std::memory_order_relaxed);
\t\t}
\t}
""",
        """\tif (entry != queues.end()) {
\t\tqueues.erase(entry);
\t\tif (registration->kind == VideoOutEventKind::Flip) {
\t\t\tstate->active_flip_registrations.store(
\t\t\t    static_cast<uint32_t>(queues.size()), std::memory_order_relaxed);
\t\t}
\t}
""",
    ),
    (
        """\t\t\tqueues.push_back(registration);
\t\t\tadd_queue = true;
""",
        """\t\t\tqueues.push_back(registration);
\t\t\tif (kind == VideoOutEventKind::Flip) {
\t\t\t\tevent_state->active_flip_registrations.store(
\t\t\t\t    static_cast<uint32_t>(queues.size()), std::memory_order_relaxed);
\t\t\t}
\t\t\tadd_queue = true;
""",
    ),
    (
        """\t\tif (added != queues.end()) {
\t\t\tqueues.erase(added);
\t\t}
\t} else if (result == OK && add_queue && kind == VideoOutEventKind::Flip) {
\t\tevent_state->active_flip_registrations.fetch_add(1, std::memory_order_relaxed);
\t}
""",
        """\t\tif (added != queues.end()) {
\t\t\tqueues.erase(added);
\t\t\tif (kind == VideoOutEventKind::Flip) {
\t\t\t\tevent_state->active_flip_registrations.store(
\t\t\t\t    static_cast<uint32_t>(queues.size()), std::memory_order_relaxed);
\t\t\t}
\t\t}
\t}
""",
    ),
)

for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit("0989: expected source anchor exactly once; no source written")
    text = text.replace(old, new, 1)

if "active_flip_registrations.fetch_" in text:
    raise SystemExit("0989: incremental registration accounting remains; no source written")
source.write_text(text)
print("0989: flip-registration count follows the mutex-protected queue; event semantics unchanged")
