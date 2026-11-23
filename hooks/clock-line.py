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

It reads only timestamps from the session transcript (never message text),
writes nothing, makes no network request, and always exits 0.
"""
import datetime
import json
import os
import re
import sys

TAIL_BYTES = 262144
HEAD_BYTES = 65536
GAP_MIN_S = 10 * 60          # say nothing about pauses shorter than this
SESSION_AGE_MIN_S = 6 * 3600  # say nothing about session age below this
TS = re.compile(rb'"timestamp"\s*:\s*"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"')


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


def transcript_times(p):
    """(first timestamp, last timestamp) in the transcript, or (None, None)."""
    try:
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            head = f.read(HEAD_BYTES)
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
            else:
                f.seek(0)
            tail = f.read()
    except OSError:
        return None, None
    first = TS.search(head)
    last = None
    for m in TS.finditer(tail):
        last = m
    return (parse(first.group(1)) if first else None,
            parse(last.group(1)) if last else None)


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
