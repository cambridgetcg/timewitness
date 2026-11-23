#!/usr/bin/env -S python3 -I
"""clock-line: give the model a watch.

A Claude Code hook for UserPromptSubmit. It also works for SubagentStart: it
reads the event name from `hook_event_name` in its input (it takes no flags).
It adds one short line to the model's context: the local date, time of day and
zone, and, when it matters, how long it has been since anything last happened
in this session and how old the session is.

Why: the harness tells the model the date once at the start and again when the
day rolls over. It never says the time of day, the zone, or how long a pause
was. A session can sit for three days and the model's next turn starts as if no
time had passed.

The pause is measured from the last record written by the person or the model
(`user` or `assistant`, which includes tool results). Bookkeeping records and
hook records are skipped: the harness writes them while nobody is working, and
counting them made a nine-day silence read as two days.

It reads only record types and timestamps from the session transcript (never
message text), writes nothing, makes no network request, and always exits 0.
"""
import datetime
import json
import os
import re
import sys

TAIL_BYTES = 262144
TAIL_WINDOWS = (TAIL_BYTES, 2097152, 16777216)  # read further back only when needed
HEAD_BYTES = 65536
ACTIVITY_TYPES = ("user", "assistant")
GAP_MIN_S = 10 * 60          # say nothing about pauses shorter than this
SESSION_AGE_MIN_S = 6 * 3600  # say nothing about session age below this
TS = re.compile(rb'"timestamp"\s*:\s*"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"')
MAYBE_ACTIVITY = re.compile(rb'"type"\s*:\s*"(?:user|assistant)"')


def parse(ts):
    return datetime.datetime.fromisoformat(ts.decode().replace("Z", "+00:00"))


def span(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{m} min"


def last_activity(p, size):
    """Time of the last record written by the person or the model, or None.

    Reads back from the end of the file. Only a line whose top-level "type" is
    user or assistant counts; a quick byte search skips the other lines without
    parsing them."""
    for window in TAIL_WINDOWS:
        start = max(0, size - window)
        with open(p, "rb") as f:
            f.seek(start)
            lines = f.read().split(b"\n")
        if start > 0:
            lines = lines[1:]  # the first piece is the end of a longer line
        for raw in reversed(lines):
            if not MAYBE_ACTIVITY.search(raw):
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("type") not in ACTIVITY_TYPES:
                continue
            ts = rec.get("timestamp")
            if isinstance(ts, str) and TS.fullmatch(b'"timestamp":"' + ts.encode() + b'"'):
                return parse(ts.encode())
        if start == 0:
            break
    return None


def transcript_times(p):
    """(first timestamp in the transcript, time of the last user or assistant
    record), each None when it cannot be read."""
    try:
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            head = f.read(HEAD_BYTES)
        first = TS.search(head)
        first = parse(first.group(1)) if first else None
    except (OSError, ValueError):
        return None, None
    try:
        last = last_activity(p, size)
    except (OSError, ValueError):
        last = None
    return first, last


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    event = data.get("hook_event_name") or "UserPromptSubmit"
    now = datetime.datetime.now().astimezone()
    off = now.utcoffset() or datetime.timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    offs = f"UTC{sign}{abs(mins) // 60}" + (f":{abs(mins) % 60:02d}" if abs(mins) % 60 else "")
    zone = now.tzname() or ""
    line = f"Clock: {now:%a %d %b %Y, %H:%M} {zone} ({offs})."

    if event == "UserPromptSubmit":
        first, last = transcript_times(data.get("transcript_path") or "")
        utc_now = now.astimezone(datetime.timezone.utc)
        if last is not None:
            gap = (utc_now - last).total_seconds()
            if gap >= GAP_MIN_S:
                line += f" {span(gap)} since the last activity in this session."
        if first is not None:
            age = (utc_now - first).total_seconds()
            if age >= SESSION_AGE_MIN_S:
                line += f" Session began {span(age)} ago."

    json.dump({"hookSpecificOutput": {"hookEventName": event, "additionalContext": line}}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
