#!/usr/bin/env python3
"""Structural regression for observability-only ready/present/event diagnostics."""
from pathlib import Path
import re
import sys

source = (Path(sys.argv[1]) / "src/graphics/presentation/videoOut.cpp").read_text()

report = re.search(r"void NovaReport\(\) \{(.*?)\n\t\}", source, re.S)
assert report, "NovaReport missing"
report_body = report.group(1)
assert "KernelTriggerEvent" not in report_body
assert "RequestState::Ready" in report_body  # blocker classification only
assert "->state =" not in report_body and ".state =" not in report_body
assert "pending=%d" not in report_body and "gcq=%d" not in report_body
assert "recording_age_ms=%llu" in report_body
assert "gpu_blockers=%u cpu_blockers=%u" in report_body
assert "flip_publish_calls=%llu" in report_body
assert "active_flip_regs=%u" in report_body

trigger = re.search(
    r"static void TriggerVideoOutEvents\(.*?\n\}(?=\n\nstatic void DeleteVideoOutEvents)",
    source,
    re.S,
)
assert trigger, "TriggerVideoOutEvents missing"
trigger_body = trigger.group(0)
assert "kind == VideoOutEventKind::Flip" in trigger_body
assert "flip_registration_ok.fetch_add" in trigger_body
assert "flip_registration_badf.fetch_add" in trigger_body
assert "flip_registration_enoent.fetch_add" in trigger_body
assert "active_flip_registrations.fetch_add" not in source
assert "active_flip_registrations.fetch_sub" not in source
assert source.count("active_flip_registrations.store") >= 4
assert "active_flip_registrations.store(0" in source

assert source.count("request->ready_tick = Common::Timer::QueryPerformanceCounter()") == 1
assert source.count("request.presenting_tick = Common::Timer::QueryPerformanceCounter()") == 1
assert "m_presented_groups++" in source
assert "m_due_false_attempts++" in source

# The saved event state prevents a close/reopen from racing the report's shared_ptr read.
assert "std::shared_ptr<VideoOutEventState> events;" in source
assert "r.events     = cfg.events;" in source
assert "const auto& events = *r.events;" in source

print("PASS 0987 flip lifecycle diagnostics preserve real completion/event semantics")

