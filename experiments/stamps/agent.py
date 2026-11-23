#!/usr/bin/env python3
"""One agent in the stamp experiment. The driver starts it under a clock (true, or faked by
libfaketime) and sends it one JSON command per line on standard input. For each command the
agent reads its own clock, writes a message that states that reading, and stamps the message
with timewitness's own command line code (`--stamp FILE --out STAMP [--ref STAMP ...]`), run
inside this process so that the faked clock keeps ticking from one message to the next.

It answers one JSON line per command on standard output. Every answer carries a pair of
readings taken together: the agent's wall clock and its monotonic clock. The monotonic clock
is not faked (on macOS libfaketime leaves it alone; on Linux the driver sets
FAKETIME_DONT_FAKE_MONOTONIC=1) and is shared by every process on the machine, so the driver
can turn any monotonic reading into true time and measure how far the agent's wall clock is off.

    python3 -I agent.py NAME PATH/TO/timewitness.py     (working directory: where files go)
"""
import contextlib
import datetime
import importlib.util
import io
import json
import os
import sys
import time

name, tw_path = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("timewitness", tw_path)
tw = importlib.util.module_from_spec(spec)
sys.modules["timewitness"] = tw
spec.loader.exec_module(tw)


def say(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")
    sys.stdout.flush()


def pair():
    """Wall and monotonic clock read back to back (monotonic, wall, monotonic; the midpoint is kept)."""
    m0 = time.monotonic()
    w = time.time()
    m1 = time.monotonic()
    return w, (m0 + m1) / 2


def stamp_text(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")


w, m = pair()
say({"hello": name, "pair_wall": w, "pair_mono": m, "python": sys.version.split()[0],
     "faketime_env": bool(os.environ.get("FAKETIME")), "tool_version": tw.TOOL_VERSION})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    cmd = json.loads(line)
    if cmd.get("quit"):
        break
    m_start = time.monotonic()
    read_wall, read_mono = pair()
    text = cmd["text"].replace("{clock}", stamp_text(read_wall))
    with open(cmd["msg"], "w", encoding="utf-8") as f:
        f.write(text)
    argv = ["--stamp", cmd["msg"], "--out", cmd["stamp"]]
    for r in cmd.get("refs", []):
        argv += ["--ref", r]
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = tw.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 2
        except Exception as e:  # recorded, never raised: the driver must get an answer
            code = "exception %s: %s" % (type(e).__name__, e)
    m_end = time.monotonic()
    w, m = pair()
    say({"id": cmd["id"], "agent": name, "exit": code, "read_wall": read_wall, "read_mono": read_mono,
         "start_mono": m_start, "end_mono": m_end, "pair_wall": w, "pair_mono": m, "text": text,
         "stdout": tw.scrub(out.getvalue()), "stderr": tw.scrub(err.getvalue())})
