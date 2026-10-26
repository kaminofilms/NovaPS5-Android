#!/usr/bin/env python3
"""Apply observability-only flip lifecycle telemetry after the 0985 overlay."""
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
repo = Path(__file__).resolve().parents[2]
patch = repo / "patches" / "0987-flip-lifecycle.patch"
source = root / "src/graphics/presentation/videoOut.cpp"

if not source.is_file() or not patch.is_file():
    raise SystemExit("0987: source or patch is missing")

before = source.read_text()
if "state_name=%s" not in before or "flip_publish_calls" in before:
    raise SystemExit("0987: expected post-0985 source exactly once; no source written")

subprocess.run(["git", "-C", str(root), "apply", "--check", str(patch)], check=True)
subprocess.run(["git", "-C", str(root), "apply", str(patch)], check=True)

after = source.read_text()
required = (
    "recording_age_ms=%llu",
    "gpu_blockers=%u cpu_blockers=%u",
    "flip_publish_calls=%llu",
    "flip_registration_enoent",
    "m_due_false_attempts++",
    "request->ready_tick = Common::Timer::QueryPerformanceCounter()",
)
if any(token not in after for token in required):
    raise SystemExit("0987: post-apply verification failed")
print("0987: real flip lifecycle telemetry enabled; no completion/event is synthesized")
