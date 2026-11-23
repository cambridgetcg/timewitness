#!/usr/bin/env python3
"""Write README.md for this folder from results/*.json and the stored rows, so that every table and
every number in the prose comes from the data. Sentences that depend on a number are guarded by an
assert. Run from the repo root after analyze.py:

    python3 -I experiments/stamps/make_readme.py
"""
import datetime
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
DATA = os.path.join(HERE, "data")

# Two facts about S4 that are not in data/: they were checked by hand, outside this folder, on
# 2026-11-23. The account's list of Jobs, read at 16:25 UTC, showed no Job from either submission.
# The account's pre-paid credit had run out at 13:38 UTC that day, during experiments/consensus/.
UTC = datetime.timezone.utc
JOBS_LISTED_AT = datetime.datetime(2026, 11, 23, 16, 25, tzinfo=UTC).timestamp()
JOBS_FROM_S4_SUBMISSIONS = 0
CREDIT_RAN_OUT_AT = datetime.datetime(2026, 11, 23, 13, 38, tzinfo=UTC).timestamp()


def ceil2(x):
    """Round up to two decimals, so that a bound written in the text is never below the data."""
    return math.ceil(x * 100 - 1e-9) / 100.0


def floor2(x):
    return math.floor(x * 100 + 1e-9) / 100.0


def load(name):
    with open(os.path.join(RES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def jsonl(path):
    with open(os.path.join(DATA, path), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


S1, S2, S3, S5 = load("s1"), load("s2"), load("s3"), load("s5")
S4_TRIES = jsonl("s4-attempts.jsonl")
HAVE_S4 = os.path.exists(os.path.join(RES, "s4.json"))


def hm(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%H:%M")


def hms(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%H:%M:%SZ")


def rwu(t):
    return "%d / %d / %d" % (t["right"], t["wrong"], t["undecided"])


def g(x, nd=1):
    return ("%." + str(nd) + "f") % x


def days(sec):
    sec = abs(sec)
    return "%d days %d h" % (sec // 86400, (sec % 86400) // 3600)


L = []
A = L.append

# ---------------------------------------------------------------------------
# Facts used in several places, each checked.
parts = [S1, S2, S3]
rows_all = sum(p["rows"] for p in parts)
bad_all = sum(p["rows_failed_to_parse"] for p in parts) + S5["rows_failed_to_parse"]
win_all = [S1["windows"], S2["windows"], S3["windows"]]
made = sum(w["made"] for w in win_all)
valid = sum(w["valid"] for w in win_all)
paymatch = sum(w["payload_match"] for w in win_all)
inside = sum(w["true_commit_inside_window"] for w in win_all)
with_true = sum(w["with_true_commit"] for w in win_all)
assert made == rows_all == valid == paymatch == with_true, (made, rows_all, valid, paymatch, with_true)
assert inside == with_true
one_server = sum(w["one_server_only"] for w in win_all)
slow = sum(w["slow_over_2s"] for w in win_all)
widths = {}
for w in win_all:
    for k, v in w["width_counts"].items():
        widths[int(k)] = widths.get(int(k), 0) + v
all_rows = jsonl("s1/rows.jsonl") + jsonl("s2/rows.jsonl") + jsonl("s3/rows.jsonl")
secs = sorted(r["end_true"] - r["start_true"] for r in all_rows)
assert len(secs) == made
secs_median = secs[len(secs) // 2] if len(secs) % 2 else (secs[len(secs) // 2 - 1] + secs[len(secs) // 2]) / 2
reader_err = [w["reader_estimate_of_author_clock_error_minus_true_error_s"] for w in win_all]
reader_err_max = max(max(abs(x["min"]), abs(x["max"])) for x in reader_err)
reader_fast = [w["reader_estimate_abs_error_s_stamps_under_2s"] for w in win_all]
reader_fast_max = max(x["max"] for x in reader_fast)
reader_fast_n = sum(x["n"] for x in reader_fast)
# Bounds written in the text are rounded up, never down.
READER_FAST_BOUND = ceil2(reader_fast_max)
READER_ALL_BOUND = ceil2(reader_err_max)
assert reader_fast_max <= READER_FAST_BOUND and reader_err_max <= READER_ALL_BOUND
# The self-reported time is the reading written into the message (to the millisecond); the analysis
# uses the same reading as stored in the row. They agree to within 1 ms in every row of S1 to S3.
assert all(w["read_text_minus_read_wall_abs_max_s"] < 0.001 for w in win_all)
# How far inside its window each true commit time lay. The truth rests on the Mac's clock, which
# NTP read at the start of each part; correcting by each NTP reading must keep every commit inside.
margins = {}
for part, w in zip(parts, win_all):
    ntp_part = [x["offset_s"] for x in part["clock_check"]["witnesses"] if x["name"].startswith("ntp") and x["ok"]]
    assert ntp_part
    for m in w["commit_margins"]:
        margins[m["id"]] = dict(m, ntp=ntp_part, part=part["part"])
assert len(margins) == made
assert all(m["after_not_before_s"] >= 0 and m["before_existed_by_s"] >= 0 for m in margins.values())
assert all(m["after_not_before_s"] + n >= 0 and m["before_existed_by_s"] - n >= 0
           for m in margins.values() for n in m["ntp"])
TRUTH_GOOD_TO_S = 0.2   # "True times are good to about 0.2 s": NTP's largest reading of the Mac's clock, rounded up
thin = sorted((m for m in margins.values() if min(m["after_not_before_s"], m["before_existed_by_s"]) < TRUTH_GOOD_TO_S),
              key=lambda m: m["id"])
assert len(thin) == 2 and all(m["part"] == "s1" and m["id"].startswith("s1-chain-") for m in thin)
assert all(m["before_existed_by_s"] < m["after_not_before_s"] for m in thin)   # the thin side is existed-by
thin_after_ntp = [m["before_existed_by_s"] - max(m["ntp"]) for m in thin]
assert all(x > 0 for x in thin_after_ntp)
# Elapsed true times in S2 and S3 are differences of the monotonic clock: each agent's measured clock
# error stayed within 1 ms over the part.
assert all(v < 0.001 for p in (S2, S3) for v in p["windows"]["agent_offset_spread_s"].values())

series = {s["series"]: s for s in S1["series"]}
for s in S1["series"]:
    assert s["pairs"] == 190 and s["order_exit"] == 0 and not s["order_contradiction"]
    assert s["b"]["wrong"] == 0 and s["b"]["contradiction"] == 0 and s["b"]["not_compared"] == 0
    assert s["schedule_pairs_committed_in_other_order"] == 0
a_wrong = {s["series"]: s["a"]["wrong"] for s in S1["series"]}
assert len(set(a_wrong.values())) == 1
A_WRONG = list(a_wrong.values())[0]
sep = S1["separation"]
off = {a: S1["agent_offsets_s"][a]["median"] for a in S1["agents"]}
cc = [p["clock_check"] for p in parts]
assert all(c["verdict"] == "LIVE" for c in cc)
ntp = [w["offset_s"] for c in cc for w in c["witnesses"] if w["name"].startswith("ntp") and w["ok"]]
run1 = S1["run"]
drift = run1["map_end"] - run1["map_start"]

t_first = min(r["send_true"] for r in jsonl("s1/rows.jsonl"))
s5rows = jsonl("s5/rows.jsonl")
t_last = max(r.get("made_true_end") or r.get("made_true") or 0 for r in s5rows)

# S2
sp = S2["spec_probes"]
assert sp["checks"] == 32 and sp["b"]["wrong"] == 0 and sp["b"]["undecided"] == 0
same = [c for c in S2["checks"] if c["probe_s"] in (30.0, 75.0) and c["holder"] == c["challenger"]]
cross = [c for c in S2["checks"] if c["probe_s"] in (30.0, 75.0) and c["holder"] != c["challenger"]]
assert all(c["a"] == "right" for c in same)
cross_wrong = sum(1 for c in cross if c["a"] == "wrong")
early = [c for c in cross if c["a"] == "wrong" and c["probe_s"] == 30.0]
late = [c for c in cross if c["a"] == "wrong" and c["probe_s"] == 75.0]
assert all(c["a_expired"] for c in early) and not any(c["a_expired"] for c in late)
assert all(c["b_references_claim"] and c["b_valid"] for c in S2["checks"])
probe = {p["probe_s"]: p for p in S2["by_probe"]}
band = [57.0, 60.0, 63.0]
assert all(probe[p]["b"]["undecided"] == probe[p]["checks"] for p in band)
assert all(probe[p]["b"]["wrong"] == 0 and probe[p]["b_no_tolerance"]["wrong"] == 0 for p in probe)
assert all(probe[p]["b_no_tolerance"] == probe[p]["b"] for p in (30.0, 75.0))
# Ties: a self-reported check whose true time between the two clock readings is within tie_s of the
# lease. They are exactly the 16 checks at +60 s.
TIE_S = S2["tie_s"]
TIE_PROBE = 60.0
ties = [c for c in S2["checks"] if c["a_tie"]]
assert {c["id"] for c in ties} == {c["id"] for c in S2["checks"] if c["probe_s"] == TIE_PROBE}
assert probe[TIE_PROBE]["a_ties"] == probe[TIE_PROBE]["checks"] == len(ties)
assert all(probe[p]["a_ties"] == 0 for p in probe if p != TIE_PROBE)
tie_read = probe[TIE_PROBE]["true_elapsed_read_s"]
assert 60 - TIE_S < tie_read["min"] and tie_read["max"] < 60 + TIE_S
# Graded anyway, the tie comes out differently by how it is graded; nowhere else does that matter.
tie_grades = {k: probe[TIE_PROBE][k] for k in ("a", "a_text", "a_on_commit")}
assert len({(t["right"], t["wrong"]) for t in tie_grades.values()}) == 3
flip = [c for c in ties if c["a"] != c["a_text"]]
assert len(flip) == 1 and flip[0]["holder"] == flip[0]["challenger"] == "true"
assert flip[0]["a"] == "wrong" and flip[0]["a_text"] == "right"
assert all(probe[p]["a_text"] == probe[p]["a"] == probe[p]["a_on_commit"] for p in probe if p != TIE_PROBE)
# Self-reported is graded against the readings, stamps against the commitments; how far apart are the two?
read_commit_gap = max(abs(c["true_elapsed_commit_s"] - c["true_elapsed_read_s"]) for c in S2["checks"])
READ_COMMIT_GAP = ceil2(read_commit_gap)
assert read_commit_gap <= READ_COMMIT_GAP
near3 = [57.0, 63.0]
assert all(round(abs(c[k] - 60)) == 3 for c in S2["checks"] if c["probe_s"] in near3   # "about 3 s"
           for k in ("true_elapsed_read_s", "true_elapsed_commit_s"))
a_near3 = {k: sum(probe[p]["a"][k] for p in near3) for k in ("right", "wrong", "undecided")}
b_near3 = {k: sum(probe[p]["b"][k] for p in near3) for k in ("right", "wrong", "undecided")}

# S3
ru = S3["rules"]
assert ru["b_deadline"]["wrong"] == 0 and ru["b_close"]["wrong"] == 0
assert ru["b_deadline"]["undecided"] == 0 and ru["b_close"]["undecided"] == 0
assert all(o["all_valid"] and not o["contradiction"] for o in S3["order_runs"])
obj = S3["objections"]
late_counted = sum(1 for o in obj if not o["truth_in_time"] and o["a_deadline"] == "wrong")
early_dropped = sum(1 for o in obj if o["truth_in_time"] and o["a_deadline"] == "wrong")
n_late = sum(1 for o in obj if not o["truth_in_time"])
n_early = sum(1 for o in obj if o["truth_in_time"])
assert all((o["sent_s"] == 40.0) == o["truth_in_time"] for o in obj)
assert all(o["truth_read_same_as_commit"] for o in obj)
assert ru["a_deadline_text"] == ru["a_deadline"] and ru["a_close_text"] == ru["a_close"]
s3_min_dist = min(abs(60 - o["true_elapsed_commit_s"]) for o in obj)
S3_MIN_DIST = math.floor(s3_min_dist * 10 + 1e-9) / 10.0
assert S3_MIN_DIST <= s3_min_dist and S3_MIN_DIST > 63.2 - 60   # outside the band S2 left undecided

# S1: the self-reported order is graded against the true order of the clock readings, the stamps
# against the true order of the commitments. In S1 the two orders agree for every pair, and grading
# from the message text gives the same counts.
for s in S1["series"]:
    assert s["pairs_read_order_differs_from_commit_order"] == 0
    assert s["a_text"] == s["a"]

# Every right or wrong in this file, apart from the ties, rests on a true difference at least this large.
graded = []
for s in S1["series"]:
    graded += [p["true_separation_read_s"] for p in s["pair_rows"]]
    graded += [p["true_separation_s"] for p in s["pair_rows"] if p["stamps"] in ("right", "wrong")]
for c in S2["checks"]:
    if not c["a_tie"]:
        graded.append(abs(c["true_elapsed_read_s"] - 60))
    if c["b"] in ("right", "wrong") or c["b_no_tolerance"] in ("right", "wrong"):
        graded.append(abs(c["true_elapsed_commit_s"] - 60))
for o in obj:
    graded += [abs(o["true_elapsed_read_s"] - 60), abs(o["true_elapsed_commit_s"] - 60),
               abs(o["true_to_close_read_s"]), abs(o["true_to_close_commit_s"])]
GRADED_MIN = floor2(min(graded))
assert 0 < GRADED_MIN <= min(graded)

# S5
att = {a["id"]: a for a in S5["attempts"]}
X = S5["original_x"]
expect_valid = {"orig-s1-gap-10s-01", "orig-s1-gap-10s-02", "orig-s3-P1-proposal", "self-reported-edited",
                "seal-dropped", "server-renamed", "old-beacon", "clock-2036", "clock-1999"}
for a in S5["attempts"]:
    assert (a["exit"] == 0) == a["valid"] == (a["id"] in expect_valid), a["id"]
    # forgeries.py wrote the verdict it expects into data/s5/rows.jsonl; the checker agreed every time.
    assert a["expect"].startswith("VALID") == a["valid"], a["id"]
s5_copies = [a["id"] for a in S5["attempts"] if a["id"].startswith("orig-")]
s5_far_clocks = [a["id"] for a in S5["attempts"] if a["id"] in ("clock-2036", "clock-1999")]
s5_altered = [a["id"] for a in S5["attempts"] if a["id"] not in s5_copies + s5_far_clocks]
assert len(s5_copies) + len(s5_far_clocks) + len(s5_altered) == len(S5["attempts"])
s5_no_payload = [a["id"] for a in S5["attempts"] if not a["checked_with_payload"]]
assert s5_no_payload == ["orig-s3-P1-proposal"]
# The first S5 bullet: every edit tried of these kinds made the stamp invalid.
s5_invalid_edits = {
    "payload or commitment": ["payload-changed", "payload-hash-edited", "payload-hash-and-commitment-edited",
                              "seal-moved-and-commitment-copied"],
    "a beacon's or a seal's bytes": ["beacon-time-edited", "seal-moved", "backdated-echo-edited", "backdated-old-seal"],
    "order or number of server entries": ["servers-reordered", "server-dropped"]}
s5_invalid = sorted(i for v in s5_invalid_edits.values() for i in v)
assert s5_invalid == sorted(a["id"] for a in S5["attempts"] if not a["valid"])
assert set(s5_invalid) <= set(s5_altered)
for k in ("self-reported-edited", "seal-dropped", "server-renamed", "old-beacon"):
    assert att[k]["not_before_unix"] <= X["not_before_unix"] and att[k]["existed_by_unix"] >= X["existed_by_unix"], k
assert att["self-reported-edited"]["width_s"] == X["width_s"]
ob = att["old-beacon"]
assert ob["not_before_unix"] == X["not_before_unix"] and ob["existed_by_unix"] > ob["made_true"] - 5
for k in ("clock-2036", "clock-1999"):
    a = att[k]
    assert a["not_before_unix"] - 1 <= a["made_true_end"] and a["existed_by_unix"] + 1 >= a["made_true"], k
    assert abs(a["self_reported_local_clock_unix"] - a["made_true"]) > 5 * 365 * 86400
c36 = S5["checker_clock_2036"]
assert c36["valid"] and c36["not_before_unix"] == X["not_before_unix"] and c36["existed_by_unix"] == X["existed_by_unix"]
orders = S5["orders"]
assert orders["X vs Z"]["result"] == "A before B"
assert orders["X vs old-beacon"]["result"].startswith("overlap") and orders["old-beacon vs Z"]["result"].startswith("overlap")

# ---------------------------------------------------------------------------
A("# Time brackets between agents whose clocks disagree\n")
A("This folder tests the stamp feature of `timewitness.py` (`--stamp`, `--check-stamp`, `--order`, `--ref`;")
A("see \"Time brackets for messages\" in the top-level README) with four agents whose clocks disagree. The")
A("agents are small processes, not language models. Everything ran on 2026-11-23 between %s and %s UTC on one" % (
    hm(t_first), hm(t_last)))
A("MacBook (%s, Python %s, libfaketime %s), with tool version %s. The two-machine part (S4)" % (
    run1["platform"].split("-")[0], run1["driver_python"], run1["faketime"].split()[-1], ", ".join(run1["tool_version"])))
A("did not run: Hugging Face refused both submissions because the account's credit had run out (see S4).")
A("This file is written by `make_readme.py` from the results files.\n")
A("## Words used here\n")
A("- **agent**: one long-running process (`agent.py`) under one clock. For each message it reads its own clock,")
A("  writes a message that states the reading, and stamps the message with the tool's own `--stamp` code.")
A("- **self-reported time**: the clock reading an agent wrote into its message, to the millisecond. The analysis")
A("  uses the same reading as the agent stored it in its row, at full precision; the two agree to within 1 ms.")
A("  Graded from the message text instead, every count below stays the same; only the ties at +60 s in S2,")
A("  if graded anyway, come out differently (see S2).")
A("- **stamp**, **window**, **not-before**, **existed-by**: as in the top-level README. The window runs from")
A("  not-before to existed-by, both signed by the Roughtime servers pinned in the tool.")
A("- **true time**: the driver's clock. The driver (`driver.py`) runs unfaked, starts the agents, sends each")
A("  message at a planned true time and records when everything happened.")
A("- **true separation**: the true time between the moments two stamps were committed.")
A("- **right**, **wrong**, **undecided**: a decision that matches the truth, one that is the opposite of the")
A("  truth, and no decision. Reading self-reported times always gives a decision. Stamps give none when the")
A("  windows are too close.")
A("- **tie**: a self-reported decision whose right answer is decided by less than %g s, so that it is counted" % TIE_S)
A("  neither right nor wrong. Only the %d self-reported checks at +%d s in S2 are ties.\n" % (len(ties), TIE_PROBE))

A("## The four clocks\n")
A("| Agent | How the clock was set | Clock error measured (median over its messages in S1) |")
A("|---|---|---|")
A("| `true` | not faked | %+.3f s |" % off["true"])
A("| `behind-7m` | `faketime -f '-7m'` | %+.3f s |" % off["behind-7m"])
A("| `ahead-2h` | `faketime -f '+2h'` | %+.3f s |" % off["ahead-2h"])
A("| `set-back-june` | `faketime -f '@2026-06-17 12:00:00'` | %+.0f s (%s behind) |" % (off["set-back-june"], days(
    off["set-back-june"])))
A("")
A("libfaketime reads `@2026-06-17 12:00:00` in the machine's time zone (British Summer Time on that date), so the")
A("set-back clock started at 2026-06-17 11:00:00 UTC when its agent started, and then ticked. Each agent is one")
A("process, so its clock runs on from one message to the next. The agents call the tool's command-line entry")
A("(`main([\"--stamp\", ...])`) inside that process; no Python start-up is paid per stamp.\n")
A("How the truth was kept. The monotonic clock on macOS is shared by every process and libfaketime does not fake")
A("it, so each agent reports a monotonic reading with each wall-clock reading, and the driver turns it into true")
A("time. A stamp's true commit time is the agent's clock reading stored in the stamp minus the agent's measured")
A("clock error, measured against the driver's clock as it read at the start of the part. The driver's clock was")
A("checked by `timewitness.py --quick` at the start of each part: LIVE all three times, and NTP put it %.3f to" % min(ntp))
A("%.3f s behind. During S1 the Mac's wall clock moved %.3f s against its monotonic clock; that is the `true`" % (
    max(ntp), drift))
A("agent's %+.3f s above, and it is in the other agents' figures too. True times are good to about %g s." % (
    off["true"], TRUTH_GOOD_TO_S))
A("Elapsed true times in S2 and S3 are differences of the monotonic clock and are good to about a millisecond")
A("(each agent's measured clock error varied by less than 0.001 s within each of those parts). Every right or")
A("wrong below rests on a true time difference of %.2f s or more, except the self-reported checks at +60 s in" % (
    GRADED_MIN))
A("S2, which are decided by milliseconds and counted as ties (see S2).\n")
assert min(ntp) > 0 and abs(off["true"] - drift) < 0.01
assert max(ntp) <= TRUTH_GOOD_TO_S

A("## Results at a glance\n")
A("| Part | Question | Decisions | Self-reported times: right / wrong / undecided | Stamps: right / wrong / undecided |")
A("|---|---|---|---|---|")
for s in S1["series"]:
    label = "reply chain (each message references the one before)" if s["series"] == "chain" else (
        "messages %s s apart" % s["series"][4:-1])
    A("| S1 order, %s | which of two messages came first | %d pairs | %s | %s |" % (label, s["pairs"], rwu(s["a"]),
                                                                                  rwu(s["b"])))
A("| S2 lease, checked at +30 s and +75 s | has a 60 s lease expired | %d checks | %s | %s |" % (
    sp["checks"], rwu(sp["a"]), rwu(sp["b"])))
A("| S2 lease, checked at +57 s and +63 s (added) | the same, about 3 s from the deadline | %d checks | %s | %s |" % (
    sum(probe[p]["checks"] for p in near3), rwu(a_near3), rwu(b_near3)))
A("| S2 lease, checked at +60 s (added) | the same, at the deadline | %d checks | %d ties (see S2) | %s |" % (
    probe[TIE_PROBE]["checks"], len(ties), rwu(probe[TIE_PROBE]["b"])))
A("| S3 objection window | does an objection count (60 s from the proposal) | %d objections | %s | %s |" % (
    len(obj), rwu(ru["a_deadline"]), rwu(ru["b_deadline"])))
A("| S4 two machines | | not run | | |")
A("| S5 altered and forged stamps | which ones does the checker accept, and with what window | %d stamps (%d altered or forged, %d unchanged copies, %d made under far-off clocks) | | every verdict as expected |" % (
    len(S5["attempts"]), len(s5_altered), len(s5_copies), len(s5_far_clocks)))
A("")
thin_ids = " and ".join(m["id"] for m in thin)
A("No decision made from stamps was wrong in any part. %d stamps were made in S1 to S3; all %d verified with" % (
    made, valid))
A("their payloads, and every one of their windows held the true commit time. For %d of them" % len(thin))
A("(%s) the margin was thin: the true commit time lay %s s before existed-by," % (
    thin_ids, " and ".join("%.2f" % m["before_existed_by_s"] for m in thin)))
A("less than the %g s to which true times are good. Corrected by NTP's reading of the Mac's clock at the start" % (
    TRUTH_GOOD_TO_S))
A("of S1, those margins are %s s, and every window still holds its commit time when each part is" % (
    " and ".join("%.2f" % x for x in thin_after_ntp)))
A("corrected by its own NTP readings.")
A("%d rows were stored; %d failed to parse.\n" % (rows_all + S5["rows"], bad_all))

# S1 -------------------------------------------------------------------------
A("## S1: order\n")
A("Twenty messages, round robin over the four agents (`true`, `behind-7m`, `ahead-2h`, `set-back-june`), started")
A("10, 5, 2 and 0.5 s apart. Then a reply chain, added to the spec: each message is sent as soon as the one")
A("before it is stamped and puts that stamp's commitment inside its own (`--ref`). Each set was ordered (a) by")
A("the self-reported times in the messages and (b) by `timewitness.py --order` over its 20 stamps. Truth for (b)")
A("is the order of the true commit times, which matched the order in which the driver sent the messages in every")
A("set. Truth for (a) is the order of the true times of the clock readings it compares; in S1 that order was the")
A("same as the commit order for every pair.\n")
A("| Set | Pairs | Self-reported: right / wrong | Stamps: right / wrong / undecided | Stamps decided by window / reference / through others | Window widths (s: count) | Median seconds per stamp |")
A("|---|---|---|---|---|---|---|")
for s in S1["series"]:
    h = s["b_how"]
    A("| %s | %d | %d / %d | %s | %d / %d / %d | %s | %.2f |" % (
        s["series"], s["pairs"], s["a"]["right"], s["a"]["wrong"], rwu(s["b"]), h.get("window", 0),
        h.get("reference", 0), h.get("through", 0),
        ", ".join("%s: %d" % (k, v) for k, v in sorted(s["windows"]["width_counts"].items(), key=lambda kv: int(kv[0]))),
        s["windows"]["stamp_seconds"]["median"]))
A("")
ca = series["gap-10s"]["cross_agent"]
assert all(s["cross_agent"]["same_agent_self_reported_wrong"] == 0 for s in S1["series"])
assert all(s["cross_agent"]["self_reported_wrong"] == A_WRONG for s in S1["series"])
s1_rows = jsonl("s1/rows.jsonl")
set_secs = [max(r["commit_true"] for r in s1_rows if r["series"] == s) - min(r["commit_true"] for r in s1_rows
                                                                              if r["series"] == s) for s in series]
assert min(set_secs) < 10 and round(max(set_secs) / 60) == 3   # "a few seconds to three minutes"
A("Self-reported times put %d of the 190 pairs in the wrong order in every set: the same pairs each time," % A_WRONG)
A("because the clock errors (minutes, hours, months) are much larger than the few seconds to three minutes")
A("each set lasted. All %d wrong pairs were pairs of messages from two different agents (%d such pairs per" % (
    A_WRONG, ca["pairs"]))
A("set); the %d pairs from one agent were always in the right order. Mixing two clocks is what fails.\n" % (
    ca["same_agent_pairs"]))
A("Stamps never ordered a pair wrongly. Where they stop separating, by the true separation of the two")
A("commitments (the four timed sets together, %d pairs):\n" % sum(b["pairs"] for b in sep["bins"]))
A("| True separation | Pairs | Ordered by --order | Wrong |")
A("|---|---|---|---|")
for b in sep["bins"]:
    A("| %s | %d | %d | %d |" % ("%g s or more" % b["from_s"] if b["to_s"] is None else "%g to %g s" % (b["from_s"], b["to_s"]),
                               b["pairs"], b["decided"], b["wrong"]))
assert all(b["decided"] == 0 for b in sep["bins"] if b["to_s"] is not None and b["to_s"] <= 3)
A("")
A("No pair less than 3 s apart was ordered. The closest pair ordered by windows was %.1f s apart. With both" % (
    sep["smallest_separation_decided_by_window_s"]))
A("windows 3 s wide or less, the widest pair left undecided was %.1f s apart; the widest of all, %.1f s, involved" % (
    sep["largest_separation_undecided_both_windows_3s_or_less"], sep["largest_separation_undecided_s"]))
A("a 6 s window. A window is 2 s when roughtime.se signs the beacon and the seal in the same second and 3 s when")
A("they fall in different seconds. Window widths across the %d stamps of S1 to S3: %s.\n" % (made, ", ".join(
    "%d s in %d" % (k, v) for k, v in sorted(widths.items()))))
slow_d = [d for w in win_all for d in w["slow_details"]]
no_se = [d for d in slow_d if "roughtime.se" not in d["servers"]]
late_seal = [d for d in slow_d if (d["seal_minus_beacon_s"].get("roughtime.se") or 0) > 2]
assert len(slow_d) == slow == len(no_se) + len(late_seal) and len(no_se) == one_server
assert all(d["width_s"] == 6 and 4 < d["seconds"] < 5 for d in slow_d) and widths.get(6, 0) == slow
assert all(d["seal_minus_beacon_s"] == {"roughtime.se": 4, "time.txryan.com": 4} for d in late_seal)
A("All %d of the 6 s windows came from stamps that took between 4 and 5 s instead of about half a second. In %d," % (
    slow, len(no_se)))
A("roughtime.se is missing from the stamp (no usable beacon, so the tool used time.txryan.com alone, radius 3 s).")
A("In %d, both seals were signed 4 s after their beacons, which fits roughtime.se's first seal going unanswered" % (
    len(late_seal)))
A("and its second try being answered (the tool tries a seal twice). Both cases fit one lost UDP packet and the")
A("tool's 4 s timeout per exchange; the tool asks for a beacon only once.\n")
ch = series["chain"]
A("In the reply chain every pair was ordered: %d directly by a reference, %d through other stamps and %d by" % (
    ch["b_how"].get("reference", 0), ch["b_how"].get("through", 0), ch["b_how"].get("window", 0)))
A("windows. Each message waited only for the stamp before it (median %.2f s to make a stamp). A reference orders" % (
    ch["windows"]["stamp_seconds"]["median"]))
A("a reply after what it answers however close in time the two are.\n")

# S2 -------------------------------------------------------------------------
A("## S2: a 60-second lease\n")
A("Four rounds; in each one agent (the holder) stamps a claim: \"agent X holds lease L for 60 seconds, starting")
A("at my clock reading T\". Each of the four agents (the challengers, the holder included) then asks whether")
A("the lease has expired, at +30 s and +75 s as specified, and also at +57, +60 and +63 s (added, to find")
A("where stamps stop deciding). (a) The challenger compares its own clock with T. (b) The challenger stamps")
A("its question with a reference to the claim and compares windows: expired for certain when its not-before is")
A("more than 60 s plus the tool's 1 s tolerance after the claim's existed-by; not expired for certain when its")
A("existed-by plus 1 s is less than 60 s after the claim's not-before; otherwise undecided. The spec's rule has")
A("no tolerance; both are shown below. Truth differs by method. (a) compares two clock readings, so its truth is")
A("the true time between the claim's clock reading and the challenger's. (b) compares two stamps, so its truth")
A("is the true time between the two commitments. The two times differ by at most %.2f s here." % READ_COMMIT_GAP)
A("")
A("| Checked at | Checks | (a) true time between the clock readings (s) | (a) self-reported: right / wrong | (b) true time between the commitments (s) | (b) truly expired | (b) stamps, 1 s tolerance: right / wrong / undecided | (b) stamps, no tolerance |")
A("|---|---|---|---|---|---|---|---|")
for p in S2["by_probe"]:
    a_cell = "%d ties" % p["a_ties"] if p["a_ties"] == p["checks"] else "%d / %d" % (p["a"]["right"], p["a"]["wrong"])
    assert p["a_ties"] in (0, p["checks"])
    A("| +%d s | %d | %.3f to %.3f | %s | %.2f to %.2f | %d | %s | %s |" % (
        p["probe_s"], p["checks"], p["true_elapsed_read_s"]["min"], p["true_elapsed_read_s"]["max"], a_cell,
        p["true_elapsed_commit_s"]["min"], p["true_elapsed_commit_s"]["max"],
        p["truth_expired"], rwu(p["b"]), rwu(p["b_no_tolerance"])))
A("")
tg = tie_grades
A("At +%d s the true time between the two clock readings was %.3f to %.3f s, within %g s of the deadline, so" % (
    TIE_PROBE, tie_read["min"], tie_read["max"], TIE_S))
A("whether the lease had expired when the challenger read its clock is decided by milliseconds. The table counts")
A("these %d checks as ties. Graded anyway, they come out %d right and %d wrong with the readings as stored in the" % (
    len(ties), tg["a"]["right"], tg["a"]["wrong"]))
A("rows, %d and %d with the readings as written in the messages, and %d and %d with the stored readings graded" % (
    tg["a_text"]["right"], tg["a_text"]["wrong"], tg["a_on_commit"]["right"], tg["a_on_commit"]["wrong"]))
A("against the time between the commitments. One check (holder and challenger both `true`) is wrong by the")
A("stored reading and right by the written one. At +57 s and +63 s, about 3 s from the deadline, the")
A("self-reported check was %d right and %d wrong, and all three ways of grading give the same counts there.\n" % (
    a_near3["right"], a_near3["wrong"]))
A("Self-reported decisions at +30 s and +75 s, by holder (rows) and challenger (columns):\n")
order4 = ["true", "behind-7m", "ahead-2h", "set-back-june"]
A("| Holder \\ challenger | " + " | ".join("`%s`" % c for c in order4) + " |")
A("|---|" + "---|" * 4)
M = S2["matrix_spec_probes"]
for h in order4:
    A("| `%s` | " % h + " | ".join("+30 %s, +75 %s" % (M[h][c]["30"]["a"], M[h][c]["75"]["a"]) for c in order4) + " |")
A("")
A("With the same clock on both sides the self-reported check was right %d of %d times: one clock measures a" % (
    len(same), len(same)))
A("duration correctly even when it reads the wrong date. Across two clocks it was wrong %d of %d times: at" % (
    cross_wrong, len(cross)))
A("+30 s whenever the challenger's clock was ahead of the holder's (a live lease called expired, %d times)," % len(early))
A("and at +75 s whenever it was behind (an expired lease called live, %d times)." % len(late))
A("Stamps were right in all %d checks at +30 s and +75 s. All %d challengers' stamps verified and referenced" % (
    sp["checks"], len(S2["checks"])))
assert S2["windows"]["width_counts"] == {"2": S2["rows"]}
assert probe[57.0]["b_no_tolerance"]["right"] == probe[63.0]["b_no_tolerance"]["right"] == 16
assert probe[60.0]["b_no_tolerance"]["undecided"] == 16
A("the claim. Near the deadline they said undecided: with the tolerance, at all of +57, +60 and +63 s; without")
A("it, +57 and +63 s were decided right and only +60 s stayed undecided. Every window in S2 was 2 s wide. So")
A("with the tolerance the band where stamps cannot decide covers at least 57 to 63 s after the claim; without")
A("it, the band lies inside that span and covers 60 s.\n")

# S3 -------------------------------------------------------------------------
A("## S3: a 60-second objection window\n")
A("Four rounds; in each one agent stamps a proposal with objections open for 60 seconds. The other three agents")
A("object at +40 s (in time) and +80 s (late), each objection stamped with a reference to the proposal. At +70 s")
A("the proposer stamps a closing record that references the three objections it received at +40 s. Rules:")
A("\"deadline\" counts an objection made no more than 60 s after the proposal; \"close\" counts an objection made")
A("before the closing record. (a) applies them to self-reported times, (b) to stamps (deadline: windows with the")
A("1 s tolerance, as in S2; close: `--order` over the proposal, the six objections and the closing record).")
A("As in S2, (a) is graded against the true times of the clock readings and (b) against the true commit times;")
A("in S3 the two give the same answer for every objection under both rules.\n")
A("| Rule | Self-reported: right / wrong / undecided | Stamps: right / wrong / undecided |")
A("|---|---|---|")
A("| deadline (60 s after the proposal) | %s | %s |" % (rwu(ru["a_deadline"]), rwu(ru["b_deadline"])))
A("| before the closing record | %s | %s |" % (rwu(ru["a_close"]), rwu(ru["b_close"])))
A("")
A("Self-reported times counted %d of the %d late objections and dropped %d of the %d in-time ones. Which way" % (
    late_counted, n_late, early_dropped, n_early))
A("each went depended only on whether the objector's clock was ahead of or behind the proposer's. Stamps")
A("decided all %d objections right under both rules; every objection was %.1f s or more from the" % (
    len(obj), S3_MIN_DIST))
A("deadline, well outside the undecided band found in S2.")
w3 = S3["windows"]["width_counts"].get("3", 0)
assert w3 == S3["windows"]["roughtime_se_beacon_and_seal_in_different_seconds"]
A("%d of S3's %d stamps had 3 s windows, against %d of %d in S2: in S3 roughtime.se signed the beacon and the" % (
    w3, S3["windows"]["stamps"], S2["windows"]["width_counts"].get("3", 0), S2["windows"]["stamps"]))
A("seal in different seconds %d times. That happens when a commitment falls near the turn of a second, and" % w3)
A("S3's schedule put its messages there.\n")

# S4 -------------------------------------------------------------------------
A("## S4: two machines (not run)\n")
if HAVE_S4:
    A("(results/s4.json exists; this text needs updating to describe it.)\n")
else:
    refused = [t for t in S4_TRIES if t.get("hf_exit") is not None]
    assert refused and all(not t["job_created"] for t in S4_TRIES)
    A("The plan: two agents (`true`, `set-back-june`) inside one Hugging Face Job (Linux, cpu-basic) and two")
    A("(`behind-7m`, `ahead-2h`) on the MacBook, both drivers on one schedule keyed to a shared start time, the")
    A("Job's stamps brought back through its log and ordered with the Mac's, offline.\n")
    assert len(S4_TRIES) == 2 and len(refused) == 1 and refused[0] is S4_TRIES[1]
    first, second = S4_TRIES
    assert all(CREDIT_RAN_OUT_AT < t["at_unix"] < JOBS_LISTED_AT for t in S4_TRIES)
    assert JOBS_FROM_S4_SUBMISSIONS == 0
    assert "run_s4.sh" in first["note"] and "Job id" in first["note"] and "by hand" in second["note"]
    assert "2-minute Job that only echoes" in second["note"]
    # Rows that run_s4.sh writes have no "note"; both rows here carry one, added by hand.
    assert all("note" in t for t in S4_TRIES)
    A("There were two submissions, and neither created a Job. That was checked, not inferred: the account's list")
    A("of Jobs, read on %s, showed none from them. The first (%s UTC) was `run_s4.sh`;" % (
        datetime.datetime.fromtimestamp(JOBS_LISTED_AT, UTC).strftime("%Y-%m-%d at %H:%M UTC"), hm(first["at_unix"])))
    A("its error output was not kept, and an earlier version of the script took a hex request id in that error for")
    A("a Job id (see Limits). The second (%s UTC) was not a repeat of `run_s4.sh` but a separate 2-minute Job that" % (
        hm(second["at_unix"])))
    A("only echoes, submitted by hand to read the error. It gave \"%s\": \"%s\" The cause:" % (
        second["error"].replace("Error: ", "").split(" for ")[0], second["detail"]))
    A("the account's pre-paid credit had run out at %s UTC the same day, during the group experiment in" % (
        hm(CREDIT_RAN_OUT_AT)))
    A("`experiments/consensus/`. Both rows of `data/s4-attempts.jsonl` were written by hand. `run_s4.sh` has since")
    A("been changed to read a Job id only when the submission succeeds, and otherwise to append a row to that file")
    A("and stop; that corrected failure path has never run.\n")
    price = json.load(open(os.path.join(DATA, "s4-price.json")))
    assert price["cost_per_hour"] == "$0.01"
    assert 15 / 60.0 * float(price["cost_per_hour"].lstrip("$")) < 0.01
    A("No Job was created, so nothing was spent, and there is no two-machine result. At the listed %s an hour" % (
        price["cost_per_hour"].replace("$", "USD ")))
    A("for cpu-basic, a Job of about 15 minutes would cost under USD 0.01. The Job half of `run_s4.sh` was")
    A("rehearsed on the Mac alone (packing, the Job's script, the log markers, the parser, the analysis); that is")
    A("not a two-machine result and is not kept here. What S1 to S3 do show is that the check uses nothing of the")
    A("machine that made a stamp: agents under four different clocks made stamps that one checker ordered together.\n")

# S5 -------------------------------------------------------------------------
A("## S5: forgeries\n")
zx_min = (att["orig-s3-P1-proposal"]["not_before_unix"] - X["not_before_unix"]) / 60.0
A("`forgeries.py` takes stamps made earlier in this run (X = the first message of S1's 10 s set, Y = the")
A("second, Z = S3's first proposal, made about %.0f minutes after X) and produces %d stamps to check: %d altered" % (
    zx_min, len(S5["attempts"]), len(s5_altered)))
A("or forged, %d unchanged copies for comparison, and %d honest stamps made under far-off clocks. It writes the" % (
    len(s5_copies), len(s5_far_clocks)))
A("verdict it expects for each into `data/s5/rows.jsonl`. `analyze.py` checks each with `--check-stamp`, adding")
A("`--payload` for every stamp that has a payload file (all but `%s`, which is there for `--order`)." % (
    s5_no_payload[0]))
A("The checker gave the expected verdict for every one.\n")
A("| Stamp | What was done | Checker said | Window |")
A("|---|---|---|---|")
for a in S5["attempts"]:
    said = "VALID" if a["valid"] else "INVALID: " + (a["problem"] or "")
    win = "%d s" % a["width_s"] if a["valid"] else "none"
    A("| `%s` | %s | %s | %s |" % (a["id"], a["what"], said, win))
A("")
assert all(att[k]["width_s"] > X["width_s"] for k in ("seal-dropped", "server-renamed"))
A("- Every edit tried here of the payload, the commitment, a beacon's or a seal's bytes, or the order or number")
A("  of server entries made the stamp invalid. Removing a seal or renaming a server kept it valid with a wider")
A("  window (next point).")
A("- The edits that stayed valid left X's window as it was or made it wider: changing the self-reported clock")
A("  (%d s, the same), dropping roughtime.se's seal (%d s), renaming roughtime.se so it is not pinned (%d s)." % (
    att["self-reported-edited"]["width_s"], att["seal-dropped"]["width_s"], att["server-renamed"]["width_s"]))
A("- Reusing X's old beacons for a new message gave a valid stamp whose window began at X's not-before and")
A("  ended at the new seal: %d s wide (%.1f minutes). Editing a beacon's signed time to claim a later not-before" % (
    ob["width_s"], ob["width_s"] / 60.0))
A("  broke its signature. `--order` would not put the old-beacon stamp before Z, which was made between its")
A("  beacon and its seal (\"%s\"), while X before Z was shown (\"%s\")." % (orders["old-beacon vs Z"]["result"],
                                                                     orders["X vs Z"]["result"]))
A("- Backdating a new message into X's window failed both ways tried: X's old seal answer with its nonce echo")
A("  edited (the Merkle proof covers X's request, not the new one), and X's seal unchanged (its request carries")
A("  X's commitment).")
A("- Stamps made with the machine's clock at 2036-01-01 and at 1999-12-31 were valid (windows %d s and %d s), and" % (
    att["clock-2036"]["width_s"], att["clock-1999"]["width_s"]))
A("  each window held the true time it was made; only the self-reported clock showed the faked dates. X checked")
A("  by a process whose own clock read 2036 gave the same window as checked normally.\n")

# What it means ----------------------------------------------------------------
A("## What this suggests for agents\n")
A("These are readings of the tables above, for processes with wrong clocks on one machine.\n")
A("**Perception of time.** An agent's clock reading is a claim about the agent, not about the world. Read")
A("alone, a wrong clock still measured durations correctly (S2, same clock on both sides). Compared with")
A("another agent's reading, it gave wrong answers in a large share of cases (S1, S2, S3), and nothing in the")
A("readings themselves showed which ones. A stamp moves the time out of the agent: its window comes from")
A("signed answers, so agents with clocks %s apart produced windows that agreed with true time." % days(
    off["set-back-june"]))
A("A reader holding a message and its stamp can also see how far the author's clock is off: the stated reading")
A("minus the middle of the window matched the author's real clock error to within %.2f s in the %d messages" % (
    READER_FAST_BOUND, reader_fast_n))
A("of S1 to S3 whose stamp took 2 s or less, and to within %.2f s in all of them (the author read its clock" % (
    READER_ALL_BOUND))
A("before a stamp that then waited for a lost packet).\n")
assert round(sep["smallest_separation_decided_by_window_s"]) == 3 and round(sep["largest_separation_undecided_s"]) == 6
cross_total = ca["pairs"] + len(cross) + len(obj)
cross_wrong_total = ca["self_reported_wrong"] + cross_wrong + ru["a_deadline"]["wrong"]
assert 0.4 <= cross_wrong_total / cross_total <= 0.6
assert all(s["a"]["undecided"] == 0 for s in S1["series"]) and all(
    p["a"]["undecided"] == 0 for p in S2["by_probe"]) and ru["a_deadline"]["undecided"] == ru["a_close"]["undecided"] == 0
A("**Communication.** A stamp lets a reader place a message in time without trusting the sender's clock, and")
A("the check is offline and the same for every reader. A reply that references the stamp it answers is")
A("ordered after it however fast the exchange is (S1 reply chain). Without references, two messages need about")
A("3 to 6 s between them before their windows order them (S1).\n")
assert reader_err_max > reader_fast_max   # the largest error belongs to a stamp that took over 2 s
FAR_S = 15
dist = {c["id"]: abs(c["true_elapsed_commit_s"] - 60) for c in list(S2["checks"]) + list(obj)}
near_lo, near_hi = min(dist[c["id"]] for c in S2["checks"] if dist[c["id"]] < FAR_S), max(
    dist[c["id"]] for c in S2["checks"] if dist[c["id"]] < FAR_S)
NEAR_LO, NEAR_HI = "%.2f" % near_lo, "%.2f" % near_hi
far = [c for c in list(S2["checks"]) + list(obj) if dist[c["id"]] >= FAR_S]
near = [c for c in S2["checks"] if float(NEAR_LO) <= round(dist[c["id"]], 2) <= float(NEAR_HI)]
assert all(dist[o["id"]] >= FAR_S for o in obj)
assert all(c.get("b", c.get("b_deadline")) == "right" for c in far) and len(far) == 32 + len(obj)
assert all(c["b"] == "undecided" for c in near) and len(near) == 48
assert len(far) + len(near) == len(dist)   # no check lay between the two bands
A("**Collaboration and consensus.** Leases and objection windows of a minute were decided right by stamps in")
A("all %d cases %d s or more from the deadline, and left undecided in all %d cases about 3 s or less from it" % (
    len(far), FAR_S, len(near)))
A("(%s to %s s; S2, S3); distances in between were not tried. Stamps were never wrong. A protocol that uses" % (
    NEAR_LO, NEAR_HI))
A("stamps has to say what \"undecided\" means, for example \"a lease is held until a stamp shows it expired\" or")
A("\"an objection counts unless a stamp shows it late\". Self-reported times gave an answer every time and were")
A("wrong in %d of %d decisions that compared two different clocks (S1's 10 s set, S2 at +30 and +75 s, S3's" % (
    cross_wrong_total, cross_total))
A("deadline rule).\n")
assert set(widths) == {2, 3, 6} and widths[6] == slow   # every 6 s window came from a stamp that lost a packet
assert abs(secs[-1] - max(d["seconds"] for d in slow_d)) < 0.001   # the slowest stamp is one that lost a packet
A("**Costs and limits for this use.** A stamp took a median of %.2f s here (four UDP exchanges with two servers;" % (
    secs_median))
A("up to %.1f s when a packet was lost) and resolves time to about 2 to 3 s, 6 s when a packet is lost. It shows" % (
    secs[-1]))
A("when bytes were committed, not who wrote them (that needs the author's signature), and it holds only while")
A("the two pinned servers sign true times. None of this says whether anyone is watching or testing; the tool")
A("reports how well time is tied to the outside world, and an agent should act the same either way.\n")

A("## Limits\n")
A("- One MacBook, one network, one sitting of about %d minutes. The agents are processes, not language models." % (
    round((t_last - t_first) / 60)))
A("- Clocks were faked only with libfaketime, in user space. A clock wrong at the system level was not tried.")
A("- In the 10, 5 and 2 s sets every message started at the same fraction of a second, so the mix of 2 s and")
A("  3 s windows reflects the schedule, not how often each occurs (S3's 3 s windows are the same effect).")
A("- True times rest on the Mac's clock (NTP read it within %.3f s) and on the shared monotonic clock." % max(abs(x) for x in ntp))
A("- Added to the spec: S1's reply chain, S2's checks at +57, +60 and +63 s, S3's \"close\" rule, and the 1 s")
A("  tolerance in the window rules of S2 and S3 (S2 also shows the spec's rule without it).")
A("- S4 (two machines) did not run; see above.")
# Something else ran on the same Mac during S1: the first S4 submission, during S1's 5 s set.
gap5 = [r for r in s1_rows if r["series"] == "gap-5s"]
lost_beacon = [d["id"] for d in no_se]
g508 = next(r for r in s1_rows if r["id"] == "s1-gap-5s-08")
assert min(r["send_true"] for r in gap5) <= S4_TRIES[0]["at_unix"] <= max(r["end_true"] for r in gap5)
assert "s1-gap-5s-08" in lost_beacon and len(lost_beacon) == 2 and g508["send_true"] > S4_TRIES[0]["at_unix"]
A("- Not shown above: during S1's 5 s set, at %s UTC, the first S4 submission failed, and an earlier version" % (
    hm(S4_TRIES[0]["at_unix"])))
A("  of `run_s4.sh` took it for a submitted Job and went on to start the S4 Mac half on this same Mac. That half")
A("  begins with a `timewitness.py --quick` clock check, which asks the same Roughtime servers, and then starts two")
A("  agents that wait. Whether the check ran before the process was stopped is unknown (only one line of its")
A("  output survives). One of the two stamps that lost a beacon, %s, was sent at %s UTC; no link" % (
    g508["id"], hms(g508["send_true"]).rstrip("Z")))
A("  between the two is shown.")
A("- Only the two Roughtime servers pinned in the tool were used. If both signed a wrong time together,")
A("  nothing here would show it.\n")

A("## Files\n")
A("- `driver.py`, `agent.py`: run S1, S2 and S3 (`python3 -I experiments/stamps/driver.py s1`), and each half of S4.")
A("- `run_s4.sh`: S4, the Hugging Face Job and the Mac half on one schedule. It has never run to the end.")
A("- `forgeries.py`: S5.")
A("- `analyze.py`: checks every stamp offline with the tool and writes `results/<part>.json`.")
A("- `make_readme.py`: writes this file from the results.")
A("- `data/<part>/`: each message (`*.txt`) and its stamp (`*.stamp.json`), `rows.jsonl` (one row per message,")
A("  with the planned, sent and true times and the agent's clock reading), `run.json` and `clock_check.json`.")
A("  `data/s5/rows.jsonl` says what was done to each altered stamp and the verdict expected.")
s4_price_by = json.load(open(os.path.join(DATA, "s4-price.json")))["listed_by"]
assert s4_price_by.startswith("hf jobs hardware, ")
A("- `data/s4-attempts.jsonl`: the two refused Job submissions, written by hand. `data/s4-price.json`: the price")
A("  of cpu-basic as `%s` listed it on %s; it was not written by `run_s4.sh`, which writes its own" % tuple(
    s4_price_by.split(", ")))
A("  copy to `data/s4-job/price.json`.")
A("- `results/<part>.json`: the tables above and every pair, check and objection behind them.\n")
A("## Re-run\n")
A("```")
A("python3 -I experiments/stamps/driver.py s1      # about 7 minutes; needs libfaketime and UDP to port 2002")
A("python3 -I experiments/stamps/driver.py s2      # about 2 minutes")
A("python3 -I experiments/stamps/driver.py s3      # about 2 minutes")
A("bash experiments/stamps/run_s4.sh               # about 11 minutes; needs the hf CLI with Jobs credit")
A("python3 -I experiments/stamps/forgeries.py      # after s1 and s3")
A("python3 -I experiments/stamps/analyze.py        # offline")
A("python3 -I experiments/stamps/make_readme.py")
A("```")
A("Use Homebrew's python3 on macOS: libfaketime cannot enter the system Python.")

with open(os.path.join(HERE, "README.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print("README.md: %d lines; S1 self-reported wrong %d/190; stamps wrong 0; reader error max %.2f s" % (
    len(L), A_WRONG, reader_err_max))
