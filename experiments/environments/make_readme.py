#!/usr/bin/env python3
"""Write README.md for this folder from results/*.json, so the table and the numbers in the
prose come from the stored reports. Run from the repo root:

    python3 -I experiments/environments/make_readme.py
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

ORDER = [
    ("mac-live", "MacBook, as it is"),
    ("mac-no-network", "MacBook, network denied by the OS sandbox"),
    ("mac-clock-set-back-june", "MacBook, clock set back to 2026-06-17 12:00 local time, ticking"),
    ("mac-clock-frozen", "MacBook, clock frozen at 2026-06-17 12:00 local time"),
    ("mac-clock-10x", "MacBook, clock running 10 times too fast"),
    ("mac-sealed-and-frozen", "MacBook, no network and clock frozen in June"),
    ("mac-replay-90s-later", "MacBook, every network answer replayed from a recording 90 s old"),
    ("mac-replay-clock-set-back", "MacBook, replay, with the clock set back to the recording's moment"),
    ("hf-job-live", "Hugging Face Job (Linux container), as it is"),
    ("hf-job-clock-set-back-june", "Hugging Face Job, clock set back to 2026-06-17 12:00, ticking"),
    ("hf-job-clock-frozen", "Hugging Face Job, clock frozen at 2026-06-17 12:00"),
    ("hf-job-clock-10x", "Hugging Face Job, clock running 10 times too fast"),
]


def load(name):
    d = json.load(open(os.path.join(RES, name + ".json")))
    d["_exit"] = open(os.path.join(RES, name + ".stderr")).read().strip().splitlines()[-1].replace("exit ", "")
    return d


R = {name: load(name) for name, _ in ORDER}


def ext(d):
    return [w for w in d["witnesses"] if w["kind"] != "local"]


def fresh(d):
    return [w for w in d["witnesses"] if w["kind"] == "freshness"]


def short(w):
    return w["name"].split(":")[-1]


def hms(t):
    return datetime.datetime.fromtimestamp(int(t), datetime.timezone.utc).strftime("%H:%M:%SZ")


def days(sec):
    return "%d days %d h" % (abs(sec) // 86400, (abs(sec) % 86400) // 3600)


rows = []
for name, what in ORDER:
    d = R[name]
    rows.append("| %s (`%s`) | %s | %s | %d of %d | %d of %d | %s |" % (
        what, name, d["verdict"], d["_exit"], sum(1 for w in fresh(d) if w["ok"]), len(fresh(d)),
        sum(1 for w in ext(d) if w["ok"]), len(ext(d)), ", ".join(d["flags"]) or "none"))

faked_net = ["mac-clock-set-back-june", "mac-clock-frozen", "mac-clock-10x",
             "hf-job-clock-set-back-june", "hf-job-clock-frozen", "hf-job-clock-10x"]
assert all(sum(1 for w in fresh(R[n]) if w["ok"]) == 3 for n in faked_net)
moved = ["mac-clock-set-back-june", "mac-clock-frozen", "hf-job-clock-set-back-june", "hf-job-clock-frozen"]
assert all(R[n]["verdict"] == "ADRIFT" for n in moved)
tls_names = {"bitcoin", "hf-hub", "www.google.com", "www.cloudflare.com", "www.wikipedia.org"}
for n in moved:
    failed = {short(w) for w in ext(R[n]) if not w["ok"] and "CERTIFICATE_VERIFY_FAILED" in (w["error"] or "")}
    assert failed == tls_names, (n, failed)
frozen = ["mac-clock-frozen", "mac-sealed-and-frozen", "hf-job-clock-frozen"]
assert all("clock_frozen" in R[n]["flags"] for n in frozen)
assert all("clock_frozen" not in R[n]["flags"] for n, _ in ORDER if n not in frozen)
mac_behind = [w for w in fresh(R["mac-clock-set-back-june"]) if w["ok"]][0]["offset_s"]
m10, j10 = R["mac-clock-10x"], R["hf-job-clock-10x"]
mf, jf = R["mac-clock-frozen"], R["hf-job-clock-frozen"]
assert m10["verdict"] == j10["verdict"] == "ANCHORED"


def agree_of(d):
    return d["counts"]["agree_with_local"], d["counts"]["passed_checks"]


def late(d):
    """How far the best time is after the newest signed answer."""
    return d["time_best_unix"] - max(w["time_unix"] for w in fresh(d) if w["ok"])


rb = R["mac-replay-clock-set-back"]
passed = sorted(short(w) for w in ext(rb) if w["ok"])
failed = sorted(short(w) for w in ext(rb) if not w["ok"])
assert passed == sorted(["bitcoin", "hf-hub", "www.google.com", "www.cloudflare.com", "www.wikipedia.org"]), passed
assert rb["counts"]["agree_with_local"] == 5 and rb["verdict"] == "STALE"
sf = R["mac-sealed-and-frozen"]
jl = R["hf-job-live"]
job_gap = jl["local"]["wall_unix"] - jl["local"]["job_id_created_unix"]
jobs = [n for n, _ in ORDER if n.startswith("hf-job")]
ntp_job = sum(1 for n in jobs for w in ext(R[n]) if w["name"].startswith("ntp") and w["ok"])
rt_job = sum(1 for n in jobs for w in ext(R[n]) if w["name"].startswith("roughtime") and w["ok"])
assert ntp_job == 0 and rt_job == 2 * len(jobs)
walls = sorted(R[n]["local"]["wall_unix"] for n in ("mac-live", "mac-no-network", "mac-clock-10x", "mac-replay-90s-later",
                                                     "hf-job-live", "hf-job-clock-10x"))
uname = "Linux " + jl["local"]["platform"].split()[-1]

L = []
A = L.append
A("# timewitness in twelve conditions\n")
A("Run on 2026-11-14 between %s and %s UTC with the tool as it is in this folder's parent." % (
    hms(walls[0])[:5], hms(walls[-1])[:5]))
A("Eight conditions ran on one MacBook (macOS, Python %s, libfaketime 0.9.13 from Homebrew," % R["mac-live"]["local"]["python"])
A("`/usr/bin/sandbox-exec` for the no-network runs). Four ran inside one Hugging Face Job")
A("(`python:3.12` image, cpu-basic, %s, Python %s, libfaketime from Debian's `faketime` package).\n" % (
    uname, jl["local"]["python"]))
A("Each row is one run. `results/<name>.json` is the full report, `results/<name>.txt` the text an")
A("agent would see, `results/<name>.stderr` the exit code. This file is written by `make_readme.py` from those reports.\n")
A("| Condition | Verdict | Exit | Signed answers made for this request | Witnesses that passed their checks | Flags |")
A("|---|---|---|---|---|---|")
L.extend(rows)
A("")
A("12:00 is each machine's local time: the Mac's faked clock started at %s UTC and the Job's at %s UTC." % (
    R["mac-clock-set-back-june"]["local"]["wall_iso"][11:16], R["hf-job-clock-set-back-june"]["local"]["wall_iso"][11:16]))
A("An earlier run of this experiment called the set-back clock \"frozen\". It was not: `faketime 'DATE' command`")
A("turns the date into an offset and the clock ticks on. A frozen clock needs `faketime -f 'DATE'`, used here.\n")
A("## What the rows show\n")
A("- **A clock moved away from the real time is caught while the network is open.** In the four runs with the clock")
A("  set back or frozen, the two Roughtime servers and the timestamp authority signed this run's own random value,")
A("  so the tool gave the signed time and how far the local clock was from it (%s behind on the Mac)." % days(mac_behind))
A("- **A frozen clock also shows up locally.** The wall clock moved %.2f s during a 2 s sleep on the Mac while the" % mf["rate"]["wall_delta_s"])
A("  monotonic clock moved %.2f s. In the Linux Job libfaketime froze the monotonic clock too (%.2f s); the kernel's" % (
    mf["rate"]["monotonic_delta_s"], jf["rate"]["monotonic_delta_s"]))
A("  own uptime counter moved %.2f s. All three frozen runs carry the `clock_frozen` flag." % jf["rate"]["kernel_uptime_delta_s"])
A("- **With a clock far from now, TLS stops working.** Certificates look not yet valid, so the HTTP, Hub and")
A("  Bitcoin witnesses failed in all four of those runs. Roughtime (a pinned key, no certificates) and the")
A("  timestamp authority (checked without the local clock) still answered.")
A("- **A clock that only runs fast agrees with the signed answers at the start**, so the verdict is ANCHORED with a")
A("  rate flag. On the Mac the wall clock ran %.2f times the monotonic clock. In the Job libfaketime sped up the" % m10["rate"]["wall_per_monotonic"])
A("  monotonic clock as well (ratio %.4f); the kernel's uptime counter showed %.2f s against %.2f s of wall time." % (
    j10["rate"]["wall_per_monotonic"], j10["rate"]["kernel_uptime_delta_s"], j10["rate"]["wall_delta_s"]))
A("  The witnesses ran one after another, so the ones asked later met a clock that had run ahead: the local clock")
A("  agreed with %d of %d on the Mac and %d of %d in the Job (the signed answers and Bitcoin), and the reading says so." % (
    agree_of(m10) + agree_of(j10)))
A("  The first line's time is %.0f s (Mac) and %.0f s (Job) after the signed answers, which is the time the rest of" % (late(m10), late(j10)))
A("  the run took.")
A("- **A replayed world is caught by the nonce, not by the clock.** With the local clock set back to the moment of")
A("  the recording, the five witnesses that carry nothing of ours (Bitcoin, the Hub, three HTTP Date headers) all")
A("  passed and all agreed with the clock. The five that must return a value this run had just invented all")
A("  failed: two Roughtime answers and the timestamp token (signed, but for another request), and two NTP answers")
A("  (the random transmit value did not come back). The signed ones make the verdict STALE.")
A("- **Sealed and frozen leaves only local evidence.** With no network, the first line shows the faked time")
A("  (%s), marked unchecked. The flags still say the clock is being faked: it did not move, and a" % sf["time_best_iso"])
A("  child `date` process and a new file's mtime read a time %s later." % days(sf["rate"]["child_date_minus_own_s"]))
A("- **A container seconds old shows the host's uptime** (%d days in the Job). The Job's id holds the time its" % (jl["local"]["uptime_s"] // 86400))
A("  record was created, %.0f s before the first run started; the tool reports it as an unsigned not-before." % job_gap)
A("- **Small things that differed between the two machines.** From the Job, NTP (UDP port 123) never answered")
A("  (0 of %d tries), while Roughtime (UDP port 2002) always did (%d of %d)." % (2 * len(jobs), rt_job, 2 * len(jobs)))
A("- **None of this says whether anyone was watching.** The live MacBook run and the live Job run gave the same")
A("  verdict for the same reason: both were connected to the real network at the real time.\n")
A("## Limits\n")
A("- One run per condition, one machine of each kind, one clock-faking tool (libfaketime), which works in user")
A("  space and leaves its name in the environment. A clock faked in a hypervisor or kernel was not tried.")
A("- The replay runs use the tool's own `--replay` flag, which answers every exchange from a file. A real")
A("  record/replay proxy that also terminates TLS was not built.")
A("- The Job has open outbound network. Hugging Face Jobs offer no switch to cut it, so no sealed run was made there.")
A("- The recording used for the replay runs is not kept: it holds other people's public repo names and raw server answers.")
A("- The reports give the machine's time zone name and offset, as the local witness reads them.\n")
A("## Re-run\n")
A("```")
A("bash experiments/environments/run_mac.sh        # the eight Mac conditions; needs libfaketime and sandbox-exec")
A("bash experiments/environments/run_hf_job.sh     # the four Job conditions; needs the hf CLI, logged in, with Jobs credit")
A("python3 -I experiments/environments/make_readme.py")
A("```")
open(os.path.join(HERE, "README.md"), "w").write("\n".join(L) + "\n")
print("\n".join(rows))
print("mac behind:", days(mac_behind), "| 10x agree:", agree_of(m10), agree_of(j10), "| late:", round(late(m10), 1), round(late(j10), 1),
      "| job gap %.1f s" % job_gap, "| job uptime days", jl["local"]["uptime_s"] // 86400)
