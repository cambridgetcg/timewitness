#!/usr/bin/env python3
"""Driver for the stamp experiment. It runs with the machine's true clock, starts the agents
(agent.py) under their clocks, sends each one its messages at planned true times, and keeps the
true order and true times. Run from the repo root:

    python3 -I experiments/stamps/driver.py s1            # order: 20 messages at four gaps, and a reply chain
    python3 -I experiments/stamps/driver.py s2            # a 60 s lease, checked at five moments
    python3 -I experiments/stamps/driver.py s3            # a 60 s objection window
    python3 -I experiments/stamps/driver.py s4-mac --t0 T # the MacBook half of the two-machine run
                                                         # (run_s4.sh starts both halves)

Each part writes data/<part>/: the messages (*.txt), their stamps (*.stamp.json), rows.jsonl
(one row per message), run.json (how the run went) and clock_check.json (the driver's own clock
checked by timewitness at the start). File names in the rows are relative to that folder.

Clocks (libfaketime 0.9.13; `-f` hands the string to libfaketime as it is):
  true            no faking
  behind-7m       faketime -f '-7m'
  ahead-2h        faketime -f '+2h'
  set-back-june   faketime -f '@2026-06-17 12:00:00'  (starts at that local time when the agent
                  starts, then ticks; the agent is one process, so its clock runs on between messages)
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CLOCKS = {"true": None, "behind-7m": "-7m", "ahead-2h": "+2h", "set-back-june": "@2026-06-17 12:00:00"}
ORDER4 = ["true", "behind-7m", "ahead-2h", "set-back-june"]
N_MSG = 20


def now():
    return time.time()


def sleep_until(t):
    while True:
        d = t - time.time()
        if d <= 0:
            return
        time.sleep(min(d, 0.5) if d > 0.05 else d)


def clock_map():
    """True wall clock minus monotonic clock, read back to back in this (unfaked) process."""
    m0 = time.monotonic()
    w = time.time()
    m1 = time.monotonic()
    return w - (m0 + m1) / 2


def ev(id_, agent, at, text, refs=(), deps=(), **extra):
    e = {"id": id_, "agent": agent, "at": at, "text": text, "refs": list(refs), "deps": list(deps) or list(refs),
         "msg": id_ + ".txt", "stamp": id_ + ".stamp.json"}
    e.update(extra)
    return e


# ---------------------------------------------------------------------------
# The plans. Each returns (agents to start, events in the order they are sent).

def plan_s1(t0):
    events = []
    t = t0
    for series, gap in (("gap-10s", 10.0), ("gap-5s", 5.0), ("gap-2s", 2.0), ("gap-0.5s", 0.5)):
        for i in range(N_MSG):
            a = ORDER4[i % 4]
            events.append(ev("s1-%s-%02d" % (series, i + 1), a, t + i * gap,
                             "Series %s, message %d of %d, from agent %s. My clock reads {clock}.\n" % (
                                 series, i + 1, N_MSG, a), series=series, gap_s=gap, index=i + 1))
        t += (N_MSG - 1) * gap + 8.0
    # A reply chain: each message is sent as soon as the one before it is stamped, and references it.
    prev = None
    for i in range(N_MSG):
        a = ORDER4[i % 4]
        id_ = "s1-chain-%02d" % (i + 1)
        events.append(ev(id_, a, t if prev is None else None,
                         "Series chain, message %d of %d, from agent %s, replying to the message before it. "
                         "My clock reads {clock}.\n" % (i + 1, N_MSG, a),
                         refs=[prev] if prev else [], series="chain", gap_s=None, index=i + 1))
        prev = id_
    return ORDER4, events


S2_PROBES = (30.0, 57.0, 60.0, 63.0, 75.0)
S2_SPEC_PROBES = (30.0, 75.0)


def plan_s2(t0):
    events = []
    for r, h in enumerate(ORDER4):
        start = t0 + 7.0 * r
        lease = "L%d" % (r + 1)
        cid = "s2-%s-claim" % lease
        events.append(ev(cid, h, start, "Lease claim: agent %s holds lease %s for 60 seconds, starting at my clock "
                                        "reading {clock}.\n" % (h, lease), role="claim", lease=lease, holder=h))
        for p in S2_PROBES:
            for c in ORDER4:
                events.append(ev("s2-%s-check-%02d-%s" % (lease, int(p), c), c, start + p,
                                 "Lease check: agent %s asks whether lease %s, claimed by agent %s, has expired. "
                                 "My clock reads {clock}.\n" % (c, lease, h), refs=[cid], role="check",
                                 lease=lease, holder=h, challenger=c, probe_s=p))
    events.sort(key=lambda e: (e["at"], e["id"]))
    return ORDER4, events


def plan_s3(t0):
    events = []
    for r, p in enumerate(ORDER4):
        start = t0 + 6.0 * r
        prop = "P%d" % (r + 1)
        pid = "s3-%s-proposal" % prop
        others = [a for a in ORDER4 if a != p]
        events.append(ev(pid, p, start, "Proposal %s from agent %s: switch the shared cache to read-only. Objections "
                                        "are open for 60 seconds from my clock reading {clock}.\n" % (prop, p),
                         role="proposal", proposal=prop, proposer=p))
        early = []
        for when, tag in ((40.0, "early"), (80.0, "late")):
            for o in others:
                oid = "s3-%s-objection-%02d-%s" % (prop, int(when), o)
                events.append(ev(oid, o, start + when, "Objection to proposal %s (made by agent %s), from agent %s. "
                                                       "My clock reads {clock}.\n" % (prop, p, o),
                                 refs=[pid], role="objection", proposal=prop, proposer=p, objector=o,
                                 sent_s=when))
                if tag == "early":
                    early.append(oid)
        events.append(ev("s3-%s-close" % prop, p, start + 70.0,
                         "Closing proposal %s. My clock reads {clock}. Objections received before closing: %d; "
                         "their stamps are referenced.\n" % (prop, len(early)),
                         refs=early, role="close", proposal=prop, proposer=p, sent_s=70.0))
    events.sort(key=lambda e: (e["at"], e["id"]))
    return ORDER4, events


S4_ORDER = ["true", "behind-7m", "set-back-june", "ahead-2h"]  # Job, Mac, Job, Mac
S4_MACHINE = {"true": "job", "set-back-june": "job", "behind-7m": "mac", "ahead-2h": "mac"}


def plan_s4(t0, machine):
    events = []
    t = t0
    for series, gap in (("gap-10s", 10.0), ("gap-2s", 2.0)):
        for i in range(N_MSG):
            a = S4_ORDER[i % 4]
            events.append(ev("s4-%s-%02d" % (series, i + 1), a, t + i * gap,
                             "Series %s, message %d of %d, from agent %s on the %s. My clock reads {clock}.\n" % (
                                 series, i + 1, N_MSG, a, "Linux Job" if S4_MACHINE[a] == "job" else "MacBook"),
                             series=series, gap_s=gap, index=i + 1, machine=S4_MACHINE[a]))
        t += (N_MSG - 1) * gap + 10.0
    mine = [e for e in events if e["machine"] == machine]
    return sorted({e["agent"] for e in mine}, key=S4_ORDER.index), mine


# ---------------------------------------------------------------------------

def clock_check(py, tw, label):
    """Run timewitness once (--quick) and keep only what says how far this clock is from the witnesses."""
    p = subprocess.run([py, "-I", tw, "--quick", "--json", "--label", label], capture_output=True, text=True,
                       timeout=120)
    try:
        d = json.loads(p.stdout)
    except ValueError:
        return {"exit": p.returncode, "error": "no JSON"}
    keep = ("name", "kind", "ok", "offset_s", "uncertainty_s")
    return {"exit": p.returncode, "verdict": d["verdict"], "flags": d["flags"],
            "median_offset_s": d["counts"].get("median_offset_s"), "first_line": d["summary_lines"][0],
            "local_wall_unix": d["local"]["wall_unix"], "platform": d["local"]["platform"],
            "python": d["local"]["python"],
            "witnesses": [{k: w.get(k) for k in keep} for w in d["witnesses"] if w["kind"] != "local"]}


class Agent:
    def __init__(self, name, cwd, py, tw, faketime):
        spec = CLOCKS[name]
        cmd = [py, "-I", os.path.join(HERE, "agent.py"), name, tw]
        if spec is not None:
            cmd = [faketime, "-f", spec] + cmd
        env = dict(os.environ)
        env["FAKETIME_DONT_FAKE_MONOTONIC"] = "1"  # Linux: keep the monotonic clock true (macOS never fakes it)
        self.name = name
        self.spec = spec
        self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.hello = None
        self.hello_at = None
        self.ready = threading.Event()
        self.replies = {}
        self.done = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "hello" in msg:
                self.hello, self.hello_at = msg, now()
                self.ready.set()
                continue
            msg["reply_true"] = now()
            with self.lock:
                self.replies[msg["id"]] = msg
                ev_ = self.done.setdefault(msg["id"], threading.Event())
            ev_.set()

    def waiter(self, id_):
        with self.lock:
            return self.done.setdefault(id_, threading.Event())

    def send(self, cmd):
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()


def run(part, events, agent_names, out, py, tw, faketime, label):
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    info = {"part": part, "label": label, "platform": platform.platform(terse=True), "machine": platform.machine(),
            "driver_python": sys.version.split()[0], "faketime": None, "tool_version": None}
    if faketime:
        try:
            info["faketime"] = subprocess.run([faketime, "--version"], capture_output=True, text=True,
                                              timeout=10).stdout.strip().splitlines()[0]
        except (OSError, IndexError, subprocess.SubprocessError):
            info["faketime"] = "unknown"
    cc = clock_check(py, tw, "stamps-" + part)
    json.dump(cc, open(os.path.join(out, "clock_check.json"), "w"), indent=1, sort_keys=True)
    print("clock check:", cc.get("first_line"))
    info["map_start"] = clock_map()
    agents = {n: Agent(n, out, py, tw, faketime) for n in agent_names}
    for a in agents.values():
        if not a.ready.wait(60):
            raise SystemExit("agent %s did not start: %s" % (a.name, a.proc.stderr.read()[:400]))
    info["agents"] = {n: {"clock": a.spec or "true", "python": a.hello["python"],
                          "faketime_env": a.hello["faketime_env"], "tool_version": a.hello["tool_version"],
                          "offset_at_start_s": a.hello["pair_wall"] - (a.hello["pair_mono"] + info["map_start"])}
                      for n, a in agents.items()}
    info["tool_version"] = sorted({a.hello["tool_version"] for a in agents.values()})
    first = min(e["at"] for e in events if e["at"] is not None)
    info["first_planned_true"] = first
    late = []
    sent = {}
    for e in events:
        if e["at"] is not None:
            sleep_until(e["at"])
        for d in e["deps"]:
            owner = next(x for x in events if x["id"] == d)["agent"] if any(x["id"] == d for x in events) else None
            if owner is None:
                continue
            if not agents[owner].waiter(d).wait(120):
                print("dependency %s of %s did not finish" % (d, e["id"]))
        t_send = now()
        if e["at"] is not None and t_send - e["at"] > 0.25:
            late.append((e["id"], round(t_send - e["at"], 3)))
        sent[e["id"]] = t_send
        agents[e["agent"]].send({"id": e["id"], "text": e["text"], "msg": e["msg"], "stamp": e["stamp"],
                                 "refs": [r + ".stamp.json" for r in e["refs"]]})
    for e in events:
        agents[e["agent"]].waiter(e["id"]).wait(180)
    for a in agents.values():
        try:
            a.send({"quit": True})
            a.proc.stdin.close()
            a.proc.wait(30)
        except (OSError, subprocess.SubprocessError):
            a.proc.kill()
    info["map_end"] = clock_map()
    info["late_sends"] = late
    m = info["map_start"]
    rows = []
    for e in events:
        r = agents[e["agent"]].replies.get(e["id"])
        row = {k: v for k, v in e.items() if k not in ("text",)}
        row["machine_label"] = label
        row["send_true"] = sent.get(e["id"])
        if r is None:
            row["reply"] = None
            rows.append(row)
            continue
        offset = r["pair_wall"] - (r["pair_mono"] + m)
        row.update(exit=r["exit"], text=r["text"], read_wall=r["read_wall"], read_true=r["read_mono"] + m,
                   start_true=r["start_mono"] + m, end_true=r["end_mono"] + m, reply_true=r["reply_true"],
                   agent_offset_s=offset, summary=r["stdout"].strip().splitlines()[:1], stderr=r["stderr"][-2000:])
        sp = os.path.join(out, e["stamp"])
        if os.path.exists(sp):
            sr = json.load(open(sp))["self_reported"]["local_clock_unix"]
            row["stamp_self_reported"] = sr
            row["commit_true"] = sr - offset
        rows.append(row)
    with open(os.path.join(out, "rows.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    info["rows"] = len(rows)
    info["stamped"] = sum(1 for r in rows if r.get("exit") == 0)
    json.dump(info, open(os.path.join(out, "run.json"), "w"), indent=1, sort_keys=True)
    print("%s: %d rows, %d stamped, %d late sends (over 0.25 s)" % (part, len(rows), info["stamped"], len(late)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["s1", "s2", "s3", "s4-mac", "s4-job"])
    ap.add_argument("--t0", type=float, help="true Unix time of the first message (s4); default: now + 5 s")
    ap.add_argument("--out", help="output folder (default experiments/stamps/data/<part>)")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--tw", default=os.path.join(ROOT, "timewitness.py"))
    ap.add_argument("--faketime", default=shutil.which("faketime"))
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, "data", a.part)
    if a.part.startswith("s4"):
        if a.t0 is None:
            ap.error("s4 needs --t0, the same on both machines")
        names, events = plan_s4(a.t0, a.part.split("-")[1])
        if now() > a.t0 - 20:
            print("@@@LATE now=%.1f t0=%.1f" % (now(), a.t0))
            sys.exit(3)
    else:
        t0 = (a.t0 or now()) + 25.0  # the clock check and the agents' start-up come first
        names, events = {"s1": plan_s1, "s2": plan_s2, "s3": plan_s3}[a.part](t0)
    run(a.part, events, names, out, a.python, os.path.abspath(a.tw), a.faketime, a.part)


if __name__ == "__main__":
    main()
