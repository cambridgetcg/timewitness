"""Make live stamps for the timewitness stamp tests and the README width measurement.

Run: python3 -I tests/fixtures/stamps/make_stamp_fixtures.py OUT_DIR
Every stamp is made by the real command line, with the working directory set
to OUT_DIR so that only relative file names appear in any output. It needs
UDP to the Roughtime servers and takes about 35 s. The files in this folder
were made by this script on 2026-11-23 and copied here; its log is
make-log.json (the stamp JSON printed to standard output is not repeated in
the log). Running it again makes new stamps with new times, so the tests,
which assert facts about these recorded stamps, would need the new files'
numbers.
"""
import json
import os
import subprocess
import sys
import time

TW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "timewitness.py")
out = os.path.abspath(sys.argv[1])
os.makedirs(out, exist_ok=True)
log = []


def tw(*args, stdin=None):
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-I", TW] + list(args), cwd=out, capture_output=True, text=True,
                       input=stdin)
    took = time.monotonic() - t0
    log.append({"args": list(args), "exit": p.returncode, "seconds": round(took, 3),
                "stdout": p.stdout if not args[0] == "--stamp" or "--out" in args else "(stamp json)",
                "stderr": p.stderr})
    if p.returncode != 0:
        sys.stderr.write("FAILED %s\n%s\n%s\n" % (args, p.stdout, p.stderr))
    return p


def write(name, text):
    with open(os.path.join(out, name), "w", encoding="utf-8") as f:
        f.write(text)


# A short conversation: 2 replies to 1, 3 replies to 2, 4 is unrelated and
# made at once, 5 comes about 15 s later.
msgs = {
    "m1.txt": "Proposal: run the nightly job at 02:00 UTC from now on.\n",
    "m2.txt": "Agreed, 02:00 UTC works for me.\n",
    "m3.txt": "Recorded: nightly job moves to 02:00 UTC.\n",
    "m4.txt": "Unrelated note: the cache was cleared.\n",
    "m5.txt": "Follow-up, later: the first 02:00 run is scheduled.\n",
}
for k, v in msgs.items():
    write(k, v)
tw("--stamp", "m1.txt", "--out", "o1.json")
tw("--stamp", "m2.txt", "--ref", "o1.json", "--out", "o2.json")
tw("--stamp", "m3.txt", "--ref", "o2.json", "--out", "o3.json")
tw("--stamp", "m4.txt", "--out", "o4.json")
time.sleep(15)
tw("--stamp", "m5.txt", "--out", "o5.json")

# One stamp with every exchange recorded, for the replay test.
tw("--stamp", "m1.txt", "--record", "stamp-record.json", "--out", "recorded.json")

# Ten stamps for the width measurement, one after another, about 1 s apart.
rows = []
for i in range(10):
    p = tw("--stamp", "-", stdin="width measurement stamp %d\n" % (i + 1))
    if p.returncode == 0:
        rows.append(json.loads(p.stdout))
    time.sleep(1)
with open(os.path.join(out, "widths-10.jsonl"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, sort_keys=True) + "\n")
with open(os.path.join(out, "make-log.json"), "w", encoding="utf-8") as f:
    json.dump(log, f, indent=1)
print("made %d width stamps; %d commands, %d failed" % (len(rows), len(log), sum(1 for x in log if x["exit"])))
