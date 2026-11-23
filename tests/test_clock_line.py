"""Offline tests for hooks/clock-line.py, the Claude Code hook that gives the
model one line with the time, the zone and the length of a pause.

Each test writes a small transcript with timestamps set relative to now, runs
the hook as Claude Code would (JSON on standard input), and reads the line.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "clock-line.py")
UTC = datetime.timezone.utc


def stamp(seconds_ago):
    t = datetime.datetime.now(UTC) - datetime.timedelta(seconds=seconds_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)


def rec(kind, seconds_ago, **extra):
    d = {"type": kind, "timestamp": stamp(seconds_ago)}
    d.update(extra)
    return json.dumps(d, separators=(",", ":"))


class ClockLine(unittest.TestCase):
    def run_hook(self, lines=None, payload=None):
        path = ""
        if lines is not None:
            f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
            f.write("\n".join(lines) + "\n")
            f.close()
            path = f.name
            self.addCleanup(os.unlink, path)
        if payload is None:
            payload = json.dumps({"hook_event_name": "UserPromptSubmit", "transcript_path": path})
        p = subprocess.run([sys.executable, "-I", HOOK], input=payload, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        return out["additionalContext"]

    def test_line_has_date_time_and_zone(self):
        line = self.run_hook()
        self.assertRegex(line, r"^Clock: \w{3} \d{2} \w{3} \d{4}, \d{2}:\d{2} \S* \(UTC[+-]\d+(:\d{2})?\)\.$")

    def test_pause_is_measured_from_the_last_assistant_record(self):
        line = self.run_hook([rec("user", 3600), rec("assistant", 1800)])
        self.assertRegex(line, r" (29|30) min since the last activity in this session\.")

    def test_bookkeeping_and_hook_records_do_not_count_as_activity(self):
        # The fault found on 2026-11-23: a pr-link record written days after the
        # last turn made a nine-day silence read as two days.
        line = self.run_hook([
            rec("user", 3 * 86400 + 7200), rec("assistant", 3 * 86400 + 5400),
            rec("pr-link", 86400), rec("frame-link", 86400),
            rec("system", 3000, subtype="away_summary"),
            rec("attachment", 20, attachment={"type": "hook_additional_context"}),
            rec("queue-operation", 2),
        ])
        self.assertRegex(line, r" 3 d 1 h since the last activity in this session\.")

    def test_a_nested_type_field_is_not_mistaken_for_a_turn(self):
        line = self.run_hook([
            rec("assistant", 7200),
            rec("attachment", 60, attachment={"type": "user", "timestamp": stamp(60)}),
        ])
        self.assertRegex(line, r" (1 h 59|2 h 0) min since the last activity")

    def test_short_pause_says_nothing(self):
        line = self.run_hook([rec("user", 400), rec("assistant", 180)])
        self.assertNotIn("since the last activity", line)

    def test_no_turn_yet_says_nothing_about_a_pause(self):
        line = self.run_hook([rec("attachment", 9000), rec("pr-link", 8000)])
        self.assertNotIn("since the last activity", line)

    def test_tool_results_count_as_activity(self):
        line = self.run_hook([rec("assistant", 5000), rec("user", 1500, toolUseResult={"ok": True})])
        self.assertRegex(line, r" (24|25) min since the last activity")

    def test_reads_further_back_when_the_tail_is_all_bookkeeping(self):
        filler = [rec("frame-link", 500, pad="x" * 1000) for _ in range(400)]  # about 400 KB
        line = self.run_hook([rec("assistant", 2 * 86400 + 3 * 3600 + 1800)] + filler)
        self.assertRegex(line, r" 2 d 3 h since the last activity")

    def test_broken_lines_are_skipped(self):
        line = self.run_hook([rec("assistant", 1800), '{"type":"assistant","timestamp":"not a time"}',
                              '{"type":"user", broken'])
        self.assertRegex(line, r" (29|30) min since the last activity")

    def test_session_age(self):
        line = self.run_hook([rec("user", 7 * 3600 + 120), rec("assistant", 30)])
        self.assertRegex(line, r" Session began 7 h [0-3] min ago\.")
        self.assertNotIn("since the last activity", line)

    def test_garbage_input_still_gives_a_line_and_exit_0(self):
        line = self.run_hook(payload="this is not json")
        self.assertTrue(line.startswith("Clock: "))

    def test_missing_transcript_gives_a_line(self):
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "transcript_path": "/nonexistent/x.jsonl"})
        line = self.run_hook(payload=payload)
        self.assertTrue(line.startswith("Clock: "))
        self.assertNotIn("since", line)


if __name__ == "__main__":
    unittest.main()
