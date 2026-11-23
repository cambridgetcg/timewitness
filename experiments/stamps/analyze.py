#!/usr/bin/env python3
"""Check every stored stamp with timewitness, offline, and write one results file per part
(results/s1.json ... results/s5.json). Run from the repo root after the parts have run:

    python3 -I experiments/stamps/analyze.py

Every verdict here comes from the tool's own command line (`--check-stamp --json --payload` for
each stamp, `--order --json` for each group), run with the working directory set to the part's
data folder so that only relative file names appear. Truth comes from the drivers' rows: each
row has the true time at which the agent read its clock (`read_true`) and committed the stamp
(`commit_true`, the stamp's self-reported clock minus the agent's measured clock offset).
A decision from self-reported times compares clock readings, so it is graded against the true
times of those readings (`read_true`). A decision from stamps is graded against the true commit
times (`commit_true`). Each self-reported decision is also graded from the clock reading as
written in the message file (to the millisecond) and against the commit times, so that a reader
can see where the choice matters (only at S2's +60 s check).

Labels used throughout:
  right      the decision matches the truth
  wrong      the decision is the opposite of the truth
  undecided  the method gives no answer (for stamps: the windows overlap or a bound is too close)
  tie        (S2 self-reported only) the true time between the two clock readings is within TIE_S
             of the lease, so right and wrong are decided by milliseconds
"""
import concurrent.futures
import datetime
import json
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TW = os.path.join(ROOT, "timewitness.py")
DATA = os.environ.get("STAMPS_DATA") or os.path.join(HERE, "data")       # override only for rehearsals
RES = os.environ.get("STAMPS_RESULTS") or os.path.join(HERE, "results")
PY = sys.executable
TOL = 1.0  # the tool's tolerance for whole-second Roughtime times (STAMP_TOLERANCE_S)
LEASE = 60.0
TIE_S = 0.01  # a self-reported lease check this close to the lease is a tie (readings are written to 1 ms)
os.makedirs(RES, exist_ok=True)
CLOCK_RE = re.compile(r"(?:clock reads|clock reading) (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})Z")


def text_clock(folder, r):
    """The clock reading as the agent wrote it into its message file (to the millisecond)."""
    with open(os.path.join(DATA, folder, r["msg"]), encoding="utf-8") as f:
        m = CLOCK_RE.search(f.read())
    return datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%f").replace(
        tzinfo=datetime.timezone.utc).timestamp()


def add_text_clock(folder, rows):
    for r in rows:
        r["read_text"] = text_clock(folder, r)


def offset_spread(rows):
    """Per agent, the spread (max - min) of its measured clock offset over the rows given."""
    out = {}
    for a in sorted({r["agent"] for r in rows if "agent_offset_s" in r}):
        v = [r["agent_offset_s"] for r in rows if r["agent"] == a and "agent_offset_s" in r]
        out[a] = max(v) - min(v)
    return out


def load_rows(folder):
    rows, bad = [], 0
    path = os.path.join(DATA, folder, "rows.jsonl")
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return rows, bad


def tw_json(args, cwd, faketime=None):
    cmd = [PY, "-I", TW] + args + ["--json"]
    if faketime:
        cmd = [faketime[0], "-f", faketime[1]] + cmd
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, {"error": "no JSON", "stderr": p.stderr[-500:]}


def check_all(folder, rows):
    """--check-stamp --payload for every row that has a stamp. Adds row['check']."""
    cwd = os.path.join(DATA, folder)

    def one(r):
        if r.get("exit") != 0 or not os.path.exists(os.path.join(cwd, r["stamp"])):
            return None
        code, d = tw_json(["--check-stamp", r["stamp"], "--payload", r["msg"]], cwd)
        keep = ("valid", "payload_match", "not_before_unix", "existed_by_unix", "width_s", "bounds_cross_s",
                "not_before_from", "existed_by_from", "beacons_counted", "seals_counted", "commitment", "refs",
                "problems")
        out = {k: d.get(k) for k in keep}
        out["exit"] = code
        out["servers"] = [{"name": s.get("name"), "not_before_unix": s.get("not_before_unix"),
                           "existed_by_unix": s.get("existed_by_unix"),
                           "beacon_time_unix": (s.get("beacon") or {}).get("time_unix"),
                           "seal_time_unix": (s.get("seal") or {}).get("time_unix")} for s in d.get("servers") or []]
        return out

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for r, c in zip(rows, ex.map(one, rows)):
            r["check"] = c


def order(folder, stamps):
    """--order --json over the stamp files, in the order given. Returns (exit, {(id_a, id_b): pair})."""
    cwd = os.path.join(DATA, folder)
    code, d = tw_json(["--order"] + stamps, cwd)
    label = {s["label"]: s["file"] for s in d["stamps"]}
    pairs = {}
    for p in d["pairs"]:
        pairs[(label[p["a"]], label[p["b"]])] = p
    return code, d, pairs


def stamp_decision(p, file_a, file_b):
    """From one --order pair: 'a' if a is shown first, 'b' if b, None if undecided, 'x' for a contradiction."""
    if p["result"].startswith("contradiction"):
        return "x"
    if p["earlier"] is None:
        return None
    return "a" if p["earlier"] == p["a"] else "b"


def how(p):
    """How --order decided a pair: by a window, by a reference, or only through other stamps."""
    rs = " | ".join(p.get("reasons") or [])
    if not rs:
        return None
    if "existed by" in rs:
        return "window"
    if "references" in rs:
        return "reference"
    return "through"


def summary(vals):
    vals = sorted(vals)
    if not vals:
        return None
    return {"n": len(vals), "min": vals[0], "median": statistics.median(vals), "max": vals[-1]}


def window_stats(rows):
    ok = [r for r in rows if r.get("check") and r["check"]["valid"]]
    widths = [r["check"]["width_s"] for r in ok]
    inside = [r for r in ok if "commit_true" in r]
    strict = sum(1 for r in inside if r["check"]["not_before_unix"] <= r["commit_true"] <= r["check"]["existed_by_unix"])
    loose = sum(1 for r in inside if r["check"]["not_before_unix"] - TOL <= r["commit_true"]
                <= r["check"]["existed_by_unix"] + TOL)
    from_ = {}
    for r in ok:
        k = "%s / %s" % (r["check"]["not_before_from"], r["check"]["existed_by_from"])
        from_[k] = from_.get(k, 0) + 1
    return {"stamps": len(rows), "made": sum(1 for r in rows if r.get("exit") == 0), "valid": len(ok),
            "payload_match": sum(1 for r in ok if r["check"]["payload_match"]),
            "two_servers": sum(1 for r in ok if r["check"]["beacons_counted"] == 2 and r["check"]["seals_counted"] == 2),
            "width_s": summary(widths), "width_counts": {str(w): widths.count(w) for w in sorted(set(widths))},
            "bounds_cross": sum(1 for w in widths if w < 0), "true_commit_inside_window": strict,
            "true_commit_inside_window_with_1s": loose, "with_true_commit": len(inside), "bounds_from": from_,
            "one_server_only": sum(1 for r in ok if r["check"]["beacons_counted"] < 2),
            "seal_over_2s_after_beacon": sum(1 for r in ok for s in r["check"]["servers"]
                                             if s["seal_time_unix"] is not None and s["beacon_time_unix"] is not None
                                             and s["seal_time_unix"] - s["beacon_time_unix"] > 2),
            "slow_over_2s": sum(1 for r in rows if "end_true" in r and r["end_true"] - r["start_true"] > 2),
            "slow_details": [{"id": r["id"], "seconds": round(r["end_true"] - r["start_true"], 3),
                              "width_s": r["check"]["width_s"],
                              "servers": [s["name"] for s in r["check"]["servers"]],
                              "seal_minus_beacon_s": {s["name"]: (None if s["seal_time_unix"] is None else
                                                                  s["seal_time_unix"] - s["beacon_time_unix"])
                                                      for s in r["check"]["servers"]}}
                             for r in ok if "end_true" in r and r["end_true"] - r["start_true"] > 2],
            "roughtime_se_beacon_and_seal_in_different_seconds": sum(
                1 for r in ok for s in r["check"]["servers"] if s["name"] == "roughtime.se"
                and s["seal_time_unix"] is not None and s["seal_time_unix"] != s["beacon_time_unix"]),
            # A reader who holds the message and its stamp can compare the author's stated clock reading
            # with the middle of the window. How far is that from the author's real clock error?
            "reader_estimate_of_author_clock_error_minus_true_error_s": summary(
                [r["read_wall"] - (r["check"]["not_before_unix"] + r["check"]["existed_by_unix"]) / 2
                 - r["agent_offset_s"] for r in ok if "agent_offset_s" in r]),
            "reader_estimate_abs_error_s_stamps_under_2s": summary(
                [abs(r["read_wall"] - (r["check"]["not_before_unix"] + r["check"]["existed_by_unix"]) / 2
                     - r["agent_offset_s"]) for r in ok if "agent_offset_s" in r
                 and r["end_true"] - r["start_true"] <= 2]),
            "stamp_seconds": summary([r["end_true"] - r["start_true"] for r in rows if "end_true" in r]),
            # How far inside its window each true commit time lay, on each side (seconds).
            "commit_margins": [{"id": r["id"],
                                "after_not_before_s": round(r["commit_true"] - r["check"]["not_before_unix"], 4),
                                "before_existed_by_s": round(r["check"]["existed_by_unix"] - r["commit_true"], 4)}
                               for r in inside],
            "agent_offset_spread_s": offset_spread(rows),
            "read_text_minus_read_wall_abs_max_s": max([abs(r["read_text"] - r["read_wall"]) for r in rows
                                                        if "read_text" in r] or [0.0])}


def order_series(folder, rows, series_name):
    """S1/S4 for one series: (a) self-reported clock readings, (b) --order. Truth: true commit times."""
    rs = sorted(rows, key=lambda r: r["index"])
    files = [r["stamp"] for r in rs]
    code, d, pairs = order(folder, files)
    by_file = {r["stamp"]: r for r in rs}
    schedule_vs_commit = sum(1 for i in range(len(rs)) for j in range(i + 1, len(rs))
                             if rs[i]["commit_true"] > rs[j]["commit_true"])
    out = {"series": series_name, "messages": len(rs), "pairs": 0, "order_exit": code,
           "order_all_valid": d.get("all_valid"), "order_contradiction": d.get("contradiction"),
           "schedule_pairs_committed_in_other_order": schedule_vs_commit,
           "a": {"right": 0, "wrong": 0, "undecided": 0}, "b": {"right": 0, "wrong": 0, "undecided": 0,
                                                                 "contradiction": 0, "not_compared": 0},
           "a_text": {"right": 0, "wrong": 0, "undecided": 0},
           "pairs_read_order_differs_from_commit_order": 0,
           "b_how": {}, "pair_rows": []}
    for (fa, fb), p in pairs.items():
        ra, rb = by_file[fa], by_file[fb]
        sep = rb["commit_true"] - ra["commit_true"]  # > 0: a was committed first
        truth = "a" if sep > 0 else "b"
        sra, srb = ra["read_wall"], rb["read_wall"]
        ta = "a" if sra < srb else ("b" if srb < sra else None)
        # The self-reported order is judged against the true order of the clock readings it compares.
        truth_read = "a" if rb["read_true"] > ra["read_true"] else "b"
        out["a"]["right" if ta == truth_read else ("undecided" if ta is None else "wrong")] += 1
        if "read_text" in ra and "read_text" in rb:
            tt = "a" if ra["read_text"] < rb["read_text"] else ("b" if rb["read_text"] < ra["read_text"] else None)
            out["a_text"]["right" if tt == truth_read else ("undecided" if tt is None else "wrong")] += 1
        out["pairs_read_order_differs_from_commit_order"] += truth_read != truth
        if p["result"].startswith("not compared"):
            sb = "not_compared"
        else:
            dec = stamp_decision(p, fa, fb)
            sb = "contradiction" if dec == "x" else ("undecided" if dec is None else
                                                     ("right" if dec == truth else "wrong"))
        out["b"][sb] += 1
        h = how(p)
        if h:
            out["b_how"][h] = out["b_how"].get(h, 0) + 1
        out["pairs"] += 1
        out["pair_rows"].append({"a": ra["id"], "b": rb["id"], "agent_a": ra["agent"], "agent_b": rb["agent"],
                                 "widest_window_s": max(ra["check"]["width_s"], rb["check"]["width_s"])
                                 if ra.get("check") and rb.get("check") and ra["check"]["valid"]
                                 and rb["check"]["valid"] else None,
                                 "machine_a": ra.get("machine"), "machine_b": rb.get("machine"),
                                 "true_separation_s": round(abs(sep), 3),
                                 "true_separation_read_s": round(abs(rb["read_true"] - ra["read_true"]), 3),
                                 "self_reported": ta and (
                                     "right" if ta == truth_read else "wrong"), "stamps": sb, "how": h,
                                 "order_result": p["result"]})
    return out


def separation_table(pair_rows, edges=(0, 1, 2, 3, 4, 5, 6, 8, 10, 1e9)):
    """How often --order decided a pair, by the true time between the two commitments."""
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [p for p in pair_rows if lo <= p["true_separation_s"] < hi]
        if not sel:
            continue
        out.append({"from_s": lo, "to_s": hi if hi < 1e9 else None, "pairs": len(sel),
                    "decided": sum(1 for p in sel if p["stamps"] in ("right", "wrong")),
                    "wrong": sum(1 for p in sel if p["stamps"] == "wrong")})
    dec = [p["true_separation_s"] for p in pair_rows if p["stamps"] in ("right", "wrong") and p["how"] == "window"]
    und = [p["true_separation_s"] for p in pair_rows if p["stamps"] == "undecided"]
    und2 = [p["true_separation_s"] for p in pair_rows if p["stamps"] == "undecided"
            and p["widest_window_s"] is not None and p["widest_window_s"] <= 3]
    return {"bins": out, "smallest_separation_decided_by_window_s": min(dec) if dec else None,
            "largest_separation_undecided_s": max(und) if und else None,
            "largest_separation_undecided_both_windows_3s_or_less": max(und2) if und2 else None,
            "pairs_with_a_window_over_3s": sum(1 for p in pair_rows if (p["widest_window_s"] or 0) > 3)}


# ---------------------------------------------------------------------------

def part_s1():
    rows, bad = load_rows("s1")
    check_all("s1", rows)
    add_text_clock("s1", rows)
    res = {"part": "s1", "rows": len(rows), "rows_failed_to_parse": bad, "series": [],
           "run": json.load(open(os.path.join(DATA, "s1", "run.json"))),
           "clock_check": json.load(open(os.path.join(DATA, "s1", "clock_check.json")))}
    window_pairs = []
    for s in ("gap-10s", "gap-5s", "gap-2s", "gap-0.5s", "chain"):
        sel = [r for r in rows if r["series"] == s]
        o = order_series("s1", sel, s)
        o["windows"] = window_stats(sel)
        if s != "chain":
            window_pairs += o["pair_rows"]
        res["series"].append(o)
    res["windows"] = window_stats(rows)
    res["separation"] = separation_table(window_pairs)
    for o in res["series"]:
        cross = [p for p in o["pair_rows"] if p["agent_a"] != p["agent_b"]]
        o["cross_agent"] = {"pairs": len(cross), "self_reported_wrong": sum(1 for p in cross if p["self_reported"] == "wrong"),
                            "same_agent_pairs": o["pairs"] - len(cross),
                            "same_agent_self_reported_wrong": sum(1 for p in o["pair_rows"] if p["agent_a"] == p["agent_b"]
                                                                  and p["self_reported"] != "right")}
    res["agents"] = sorted({r["agent"] for r in rows})
    res["agent_offsets_s"] = {a: summary([r["agent_offset_s"] for r in rows if r["agent"] == a and
                                          "agent_offset_s" in r]) for a in res["agents"]}
    return res


def lease_decide_stamps(claim, check, tol):
    nb_c, eb_c = claim["not_before_unix"], claim["existed_by_unix"]
    nb_q, eb_q = check["not_before_unix"], check["existed_by_unix"]
    if nb_q > eb_c + tol + LEASE:
        return True
    if eb_q + tol < nb_c + LEASE:
        return False
    return None


def grade(decision, truth):
    if decision is None:
        return "undecided"
    return "right" if decision == truth else "wrong"


def part_s2():
    rows, bad = load_rows("s2")
    check_all("s2", rows)
    add_text_clock("s2", rows)
    claims = {r["lease"]: r for r in rows if r["role"] == "claim"}
    checks = [r for r in rows if r["role"] == "check"]
    out = []
    for q in checks:
        c = claims[q["lease"]]
        e_read = q["read_true"] - c["read_true"]
        e_commit = q["commit_true"] - c["commit_true"]
        a_dec = (q["read_wall"] - c["read_wall"]) > LEASE
        a_dec_text = (q["read_text"] - c["read_text"]) > LEASE
        cc, qc = c["check"], q["check"]
        b_ok = bool(cc and qc and cc["valid"] and qc["valid"])
        b_dec = lease_decide_stamps(cc, qc, TOL) if b_ok else None
        b_dec0 = lease_decide_stamps(cc, qc, 0.0) if b_ok else None
        out.append({"id": q["id"], "lease": q["lease"], "holder": q["holder"], "challenger": q["challenger"],
                    "probe_s": q["probe_s"], "true_elapsed_read_s": round(e_read, 3),
                    "true_elapsed_commit_s": round(e_commit, 3),
                    "self_reported_elapsed_s": round(q["read_wall"] - c["read_wall"], 3),
                    "self_reported_elapsed_text_s": round(q["read_text"] - c["read_text"], 3),
                    "a_expired": a_dec, "a": grade(a_dec, e_read > LEASE),
                    "a_text": grade(a_dec_text, e_read > LEASE), "a_on_commit": grade(a_dec, e_commit > LEASE),
                    "a_tie": abs(e_read - LEASE) < TIE_S,
                    "b_valid": b_ok, "b_references_claim": bool(qc and cc and cc["commitment"] in (qc["refs"] or [])),
                    "b_expired": b_dec, "b": grade(b_dec, e_commit > LEASE),
                    "b_no_tolerance": grade(b_dec0, e_commit > LEASE),
                    "b_gap_s": None if not b_ok else qc["not_before_unix"] - cc["existed_by_unix"],
                    "b_span_s": None if not b_ok else qc["existed_by_unix"] - cc["not_before_unix"]})

    def tally(sel, key):
        t = {"right": 0, "wrong": 0, "undecided": 0}
        for x in sel:
            t[x[key]] += 1
        return t

    by_probe = []
    for p in sorted({x["probe_s"] for x in out}):
        sel = [x for x in out if x["probe_s"] == p]
        by_probe.append({"probe_s": p, "checks": len(sel), "truth_expired": sum(
            1 for x in sel if x["true_elapsed_commit_s"] > LEASE),
            "true_elapsed_commit_s": summary([x["true_elapsed_commit_s"] for x in sel]),
            "true_elapsed_read_s": summary([x["true_elapsed_read_s"] for x in sel]),
            "a_ties": sum(1 for x in sel if x["a_tie"]),
            "a": tally(sel, "a"), "a_text": tally(sel, "a_text"), "a_on_commit": tally(sel, "a_on_commit"),
            "b": tally(sel, "b"), "b_no_tolerance": tally(sel, "b_no_tolerance")})
    spec = [x for x in out if x["probe_s"] in (30.0, 75.0)]
    matrix = {}
    for x in spec:
        matrix.setdefault(x["holder"], {}).setdefault(x["challenger"], {})[str(int(x["probe_s"]))] = {
            "a": x["a"], "b": x["b"], "self_reported_elapsed_s": x["self_reported_elapsed_s"]}
    return {"part": "s2", "rows": len(rows), "rows_failed_to_parse": bad, "checks": out, "by_probe": by_probe,
            "tie_s": TIE_S,
            "spec_probes": {"checks": len(spec), "a": tally(spec, "a"), "b": tally(spec, "b")},
            "matrix_spec_probes": matrix, "windows": window_stats(rows),
            "run": json.load(open(os.path.join(DATA, "s2", "run.json"))),
            "clock_check": json.load(open(os.path.join(DATA, "s2", "clock_check.json")))}


def part_s3():
    rows, bad = load_rows("s3")
    check_all("s3", rows)
    add_text_clock("s3", rows)
    out = []
    order_runs = []
    for prop in sorted({r["proposal"] for r in rows}):
        sel = [r for r in rows if r["proposal"] == prop]
        P = next(r for r in sel if r["role"] == "proposal")
        C = next(r for r in sel if r["role"] == "close")
        objs = sorted([r for r in sel if r["role"] == "objection"], key=lambda r: (r["sent_s"], r["objector"]))
        code, d, pairs = order("s3", [P["stamp"]] + [o["stamp"] for o in objs] + [C["stamp"]])
        order_runs.append({"proposal": prop, "exit": code, "all_valid": d.get("all_valid"),
                           "contradiction": d.get("contradiction")})
        for o in objs:
            e_read = o["read_true"] - P["read_true"]
            e_commit = o["commit_true"] - P["commit_true"]
            truth_read = e_read <= LEASE
            truth_commit = e_commit <= LEASE
            truth_close = o["commit_true"] < C["commit_true"]
            a1 = (o["read_wall"] - P["read_wall"]) <= LEASE
            a2 = o["read_wall"] < C["read_wall"]
            a1_text = (o["read_text"] - P["read_text"]) <= LEASE
            a2_text = o["read_text"] < C["read_text"]
            truth_close_read = o["read_true"] < C["read_true"]
            pc, oc = P["check"], o["check"]
            ok = bool(pc and oc and pc["valid"] and oc["valid"])
            if not ok:
                b1 = None
            elif oc["existed_by_unix"] + TOL < pc["not_before_unix"] + LEASE:
                b1 = True
            elif oc["not_before_unix"] > pc["existed_by_unix"] + TOL + LEASE:
                b1 = False
            else:
                b1 = None
            p = pairs.get((o["stamp"], C["stamp"]))
            dec = stamp_decision(p, o["stamp"], C["stamp"]) if p else None
            b2 = None if dec in (None, "x") else (dec == "a")
            out.append({"id": o["id"], "proposal": prop, "proposer": P["agent"], "objector": o["objector"],
                        "sent_s": o["sent_s"], "true_elapsed_commit_s": round(e_commit, 3),
                        "true_elapsed_read_s": round(e_read, 3),
                        "self_reported_elapsed_s": round(o["read_wall"] - P["read_wall"], 3),
                        "truth_in_time": truth_commit,
                        "a_deadline": grade(a1, truth_read), "a_close": grade(a2, truth_close_read),
                        "a_deadline_text": grade(a1_text, truth_read), "a_close_text": grade(a2_text, truth_close_read),
                        "truth_read_same_as_commit": truth_read == truth_commit and truth_close_read == truth_close,
                        "true_to_close_read_s": round(C["read_true"] - o["read_true"], 3),
                        "true_to_close_commit_s": round(C["commit_true"] - o["commit_true"], 3),
                        "b_deadline": grade(b1, truth_commit), "b_close": grade(b2, truth_close),
                        "b_close_how": how(p) if p else None, "close_order_result": p["result"] if p else None})

    def tally(key, sel=None):
        t = {"right": 0, "wrong": 0, "undecided": 0}
        for x in (sel if sel is not None else out):
            t[x[key]] += 1
        return t

    rules = {k: tally(k) for k in ("a_deadline", "a_close", "a_deadline_text", "a_close_text", "b_deadline", "b_close")}
    by_sent = {str(int(s)): {k: tally(k, [x for x in out if x["sent_s"] == s]) for k in
                             ("a_deadline", "a_close", "b_deadline", "b_close")}
               for s in sorted({x["sent_s"] for x in out})}
    return {"part": "s3", "rows": len(rows), "rows_failed_to_parse": bad, "objections": out, "rules": rules,
            "by_sent": by_sent, "order_runs": order_runs, "windows": window_stats(rows),
            "run": json.load(open(os.path.join(DATA, "s3", "run.json"))),
            "clock_check": json.load(open(os.path.join(DATA, "s3", "clock_check.json")))}


def part_s4():
    """Both halves in one folder view: the Job's files come back into data/s4-job, the Mac's are in data/s4-mac.
    --order needs the files side by side, so the stamps are compared from a merged folder."""
    mac, bad_m = load_rows("s4-mac")
    job, bad_j = load_rows("s4-job")
    merged = os.path.join(DATA, "s4")
    os.makedirs(merged, exist_ok=True)
    for f in os.listdir(merged):
        os.remove(os.path.join(merged, f))
    for folder, rows in (("s4-mac", mac), ("s4-job", job)):
        for r in rows:
            for k in ("msg", "stamp"):
                src = os.path.join(DATA, folder, r[k])
                if os.path.exists(src):
                    with open(src, "rb") as f, open(os.path.join(merged, r[k]), "wb") as g:
                        g.write(f.read())
    rows = mac + job
    with open(os.path.join(merged, "rows.jsonl"), "w", encoding="utf-8") as f:
        for r in sorted(rows, key=lambda r: r["id"]):
            f.write(json.dumps(r, sort_keys=True) + "\n")
    check_all("s4", rows)
    add_text_clock("s4", rows)
    res = {"part": "s4", "rows": len(rows), "rows_mac": len(mac), "rows_job": len(job),
           "rows_failed_to_parse": bad_m + bad_j, "series": [], "windows": window_stats(rows),
           "windows_job": window_stats(job), "windows_mac": window_stats(mac),
           "run_mac": json.load(open(os.path.join(DATA, "s4-mac", "run.json"))),
           "run_job": json.load(open(os.path.join(DATA, "s4-job", "run.json"))),
           "clock_check_mac": json.load(open(os.path.join(DATA, "s4-mac", "clock_check.json"))),
           "clock_check_job": json.load(open(os.path.join(DATA, "s4-job", "clock_check.json"))),
           "job_log": json.load(open(os.path.join(DATA, "s4-job", "job_log_summary.json"))),
           "price": json.load(open(os.path.join(DATA, "s4-job", "price.json")))}
    for s in ("gap-10s", "gap-2s"):
        sel = [r for r in rows if r["series"] == s and r.get("exit") == 0]
        o = order_series("s4", sel, s)
        cross = [p for p in o["pair_rows"] if p["machine_a"] != p["machine_b"]]
        o["cross_machine"] = {"pairs": len(cross),
                              "a": {k: sum(1 for p in cross if p["self_reported"] == k) for k in ("right", "wrong")},
                              "b": {k: sum(1 for p in cross if p["stamps"] == k) for k in
                                    ("right", "wrong", "undecided", "contradiction")}}
        o["separation"] = separation_table(o["pair_rows"])
        res["series"].append(o)
    res["agent_offsets_s"] = {a: summary([r["agent_offset_s"] for r in rows if r["agent"] == a and
                                          "agent_offset_s" in r]) for a in sorted({r["agent"] for r in rows})}
    return res


def part_s5():
    rows, bad = load_rows("s5")
    cwd = os.path.join(DATA, "s5")
    out = []
    for r in rows:
        args = ["--check-stamp", r["id"] + ".stamp.json"]
        if r.get("payload_file"):
            args += ["--payload", r["payload_file"]]
        code, d = tw_json(args, cwd)
        out.append({"id": r["id"], "what": r["what"], "expect": r["expect"], "exit": code, "valid": d.get("valid"),
                    "checked_with_payload": bool(r.get("payload_file")),
                    "problem": (d.get("problems") or [None])[0], "not_before_unix": d.get("not_before_unix"),
                    "existed_by_unix": d.get("existed_by_unix"), "width_s": d.get("width_s"),
                    "made_true": r.get("made_true"), "made_true_end": r.get("made_true_end"),
                    "stamp_exit": r.get("stamp_exit"), "self_reported_local_clock_unix":
                        d.get("self_reported_local_clock_unix"), "shift_s": r.get("shift_s")})
    by = {x["id"]: x for x in out}
    # The checker's own clock does not matter: check X again with the checking process's clock in 2036.
    ft = os.environ.get("FAKETIME_BIN", "/opt/homebrew/bin/faketime")
    code, d = tw_json(["--check-stamp", "orig-s1-gap-10s-01.stamp.json", "--payload", "orig-s1-gap-10s-01.txt"], cwd,
                      faketime=(ft, "@2036-01-01 00:00:00"))
    checker_2036 = {"exit": code, "valid": d.get("valid"), "not_before_unix": d.get("not_before_unix"),
                    "existed_by_unix": d.get("existed_by_unix")}
    # Order: can the old-beacon stamp be put before a stamp made between its beacon and its seal?
    orders = {}
    for name, files in (("old-beacon vs Z", ["old-beacon.stamp.json", "orig-s3-P1-proposal.stamp.json"]),
                        ("X vs old-beacon", ["orig-s1-gap-10s-01.stamp.json", "old-beacon.stamp.json"]),
                        ("X vs Z", ["orig-s1-gap-10s-01.stamp.json", "orig-s3-P1-proposal.stamp.json"])):
        code, d, pairs = order("s5", files)
        p = list(pairs.values())[0]
        orders[name] = {"exit": code, "result": p["result"], "reasons": p.get("reasons")}
    return {"part": "s5", "rows": len(rows), "rows_failed_to_parse": bad, "attempts": out,
            "checker_clock_2036": checker_2036, "orders": orders,
            "original_x": {k: by["orig-s1-gap-10s-01"][k] for k in ("not_before_unix", "existed_by_unix", "width_s")}}


PARTS = {"s1": part_s1, "s2": part_s2, "s3": part_s3, "s4": part_s4, "s5": part_s5}

if __name__ == "__main__":
    for name in sys.argv[1:] or list(PARTS):
        if name == "s4" and not os.path.exists(os.path.join(DATA, "s4-job", "rows.jsonl")):
            print("s4: no Job rows yet, skipped")
            continue
        if not os.path.exists(os.path.join(DATA, "s4-mac" if name == "s4" else name)):
            print("%s: no data, skipped" % name)
            continue
        res = PARTS[name]()
        with open(os.path.join(RES, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, sort_keys=True)
        print("%s: written results/%s.json" % (name, name))
