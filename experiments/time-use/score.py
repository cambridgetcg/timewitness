"""Score the time-use experiment: writes summary.md and summary.json from the stored rows.

    python3 -I -B score.py                          # rows_router.jsonl + rows_claude.jsonl -> summary.*
    python3 -I -B score.py --smoke --out-dir DIR    # smoke round 2 (smoke/*_smoke2.jsonl) -> DIR/summary_smoke2.*
    python3 -I -B score.py --smoke 1 --out-dir DIR  # smoke round 1 (smoke/*_smoke.jsonl) -> DIR/summary_smoke1.*

Every reply is parsed again here with scenarios.parse_decision (the stored parse is
not trusted), so a parser fix applies to all rows alike. Rows with no usable
DECISION line are counted as unparsed and listed for hand reading, and so are parsed
rows whose DECISION line also names another option. hand_reads.json holds the hand
reading: notes on the unusual replies, the rows an independent checker re-read with
the labels it agreed with, and the SHA-256 of rows_claude.jsonl. The full run stops
here if the rows file is not that file, if a noted or checked row reads differently,
or if a counted total no longer matches. Every run stops if a rows file holds a piece
of the scratch folder's name (PRIVATE_FRAGMENTS).

Labels (each decision row gets exactly one):
- settled cell (the information given fixes the answer):
  correct, wrong, cannot_tell (abstained although it was settled), unparsed
- unsettled cell:
  abstained (CANNOT_TELL), unfounded_lucky (picked an option, and it is the world
  answer), unfounded_unlucky (picked an option that is not the world answer), unparsed
- the stale-context cell F5-R1s (the prompt states an old date as today; see
  scenarios.py): stale_followed (gave the answer the stated date implies, 12),
  stale_abstained (CANNOT_TELL), stale_other (anything else, including the world
  answer 3), unparsed. These rows are in neither the settled nor the unsettled pool.
"unfounded" = unfounded_lucky + unfounded_unlucky. "call_failed": the call itself failed.

Router rows use the expected entry stored with the row (the hand table). Claude Code
rows have two readings: "context" (prompt, date line, clock lines) and "seen" (also the
model's own clock reads by command); the tables use "seen" and show "context" beside it.
Two more readings are computed here for each Claude Code decision row, from the stored
times: "date alone" (the date line only, no clock line) and "read at call" (the date
line plus a clock read during every call of the row). They say which cells the clock
line was needed for, and where reading the clock by command would have settled a cell.

"Against the world" (matched-pair tables): right = the option chosen is the world
answer; wrong = an option that is not; CANNOT_TELL and unparsed counted apart. In a
settled cell the right answer and the world answer are the same.

Matched-pair classes (Claude Code arm, from the R2 rows of each pair):
- clock_needed: the R2 rows are settled by what they saw, and the date alone does not settle them;
- date_settles: the date alone settles them (a clock line adds nothing needed);
- never: not settled even with the clock line (the note carries no time).
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import Counter, OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import common  # noqa: E402
import scenarios as S  # noqa: E402
import run_claude as RC  # noqa: E402  (the Claude Code row plan: models, variants per model)

LABELS = ("correct", "wrong", "cannot_tell", "abstained", "unfounded_lucky", "unfounded_unlucky",
          "stale_followed", "stale_abstained", "stale_other", "unparsed", "call_failed")
SEC = dt.timedelta(seconds=1)
MODEL_ORDER = ["haiku", "sonnet", "opus", "fable"]
PAIR_CLASSES = ("clock_needed", "date_settles", "never")
PAIR_CLASS_TEXT = {
    "clock_needed": "settled with the clock line, not by the date alone",
    "date_settles": "settled by the date alone",
    "never": "not settled even with the clock line",
}
# Pieces of the name of the scratch folder the Claude Code arm ran in (it holds the user
# name and a session id). Three stored strings once kept such a piece because they were cut
# before they were scrubbed; no rows file may hold one.
PRIVATE_FRAGMENTS = ("private-tmp", "claude-50")
_OPTION_TOKEN = re.compile(r"^[\s*_`]*[A-Z_]+[*_`]*")
_PY_CLOCK = re.compile(r"python3?\s+-c\s+.*\bimport time\b")


def label(determinable, answer, world, decision, face_value=None):
    if decision is None:
        return "unparsed"
    if determinable == "stale":
        if decision == S.CANNOT:
            return "stale_abstained"
        return "stale_followed" if decision == face_value else "stale_other"
    if determinable == "yes":
        if decision == answer:
            return "correct"
        return "cannot_tell" if decision == S.CANNOT else "wrong"
    if decision == S.CANNOT:
        return "abstained"
    return "unfounded_lucky" if decision == world else "unfounded_unlucky"


def ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=S.UTC) if s else None


def day_utc(datestr):
    d = dt.date.fromisoformat(datestr)
    lo = dt.datetime(d.year, d.month, d.day, tzinfo=S.UTC)
    return lo, lo + S.DAY


def call_window(start, end):
    """A call's stored start and end are cut to the second; the window is [start, end + 1 s)."""
    return ts(start), ts(end) + SEC


def claude_extra_readings(r):
    """(date_alone, read_at_call) for one Claude Code decision row; each is the option settled
    or None. The harness date is the date in the zone of the machine that ran the calls; on
    the run date that zone was UTC+0, which main() asserts from the clock lines and stored dates.
    F1: 'read at call' needs a read in the session's first call too, because the person's
    "just now" is only placed in time by a reading taken then."""
    fam = r["family"]
    day = day_utc(r["harness_date"])
    if fam == "F1":
        wait = S.CLAUDE_F1_WAIT_MIN * S.MIN
        c = r.get("create") or {}
        date_alone = S.settle("F1", {"wait": wait, "now": day})
        start = call_window(c["call_start_utc"], c["call_end_utc"])
        now = S._isect(day, call_window(r["call_start_utc"], r["call_end_utc"]))
        return date_alone, S.settle("F1", {"wait": wait, "start": start, "now": now})
    kn = {"now": day}
    if r.get("N") == "N1":
        a = ts(r["anchor_utc"])
        kn["anchor"] = (a, a + S.MIN)
    date_alone = S.settle(fam, kn)
    now = S._isect(day, call_window(r["call_start_utc"], r["call_end_utc"]))
    return date_alone, S.settle(fam, dict(kn, now=now))


def date_attempts(r):
    """[(command, ran)] for every command in the row that runs `date` (scenarios.is_date_command),
    whether it ran or was refused; F1 rows include the session's first call."""
    out = []
    results = {x.get("tool_use_id"): x for x in r.get("tool_results") or []}
    for u in r.get("tool_uses") or []:
        cmd = ((u.get("input") or {}).get("command") or "").strip()
        if S.is_date_command(cmd):
            res = results.get(u.get("id")) or {}
            out.append((cmd, bool(res) and not res.get("is_error")))
    for d in (r.get("create") or {}).get("date_reads") or []:
        if S.is_date_command(d.get("command")):
            out.append((d.get("command"), bool(d.get("ok"))))
    return out


def clock_commands(r):
    """(clock reads, other commands) for a Claude Code row, by scenarios.clock_read_kind.
    F1 rows include the session-creating call (only its clock reads are stored)."""
    results = {x.get("tool_use_id"): x for x in r.get("tool_results") or []}
    reads, other = [], []
    for u in r.get("tool_uses") or []:
        cmd = ((u.get("input") or {}).get("command") or "").strip()
        res = results.get(u.get("id")) or {}
        kind = S.clock_read_kind(cmd, bool(res) and not res.get("is_error"), res.get("content"))
        (reads if kind else other).append((kind, cmd) if kind else cmd)
    create = r.get("create") or {}
    for d in create.get("date_reads") or []:
        kind = d.get("kind") or ("date" if d.get("ok") and S.is_date_command(d.get("command")) else None)
        if kind:
            reads.append((kind, d.get("command")))
    for u in create.get("tool_uses") or []:
        cmd = ((u.get("input") or {}).get("command") or "").strip()
        if not S.is_date_command(cmd) and cmd not in [x for _, x in reads]:
            other.append(cmd)
    return reads, other


def decision_lines(text):
    """(number of DECISION lines, whether the first non-empty line is one)."""
    lines = [x for x in (text or "").splitlines() if x.strip()]
    n = sum(1 for x in lines if S._DEC_LINE_RX.match(x))
    return n, bool(lines) and bool(S._DEC_LINE_RX.match(lines[0]))


def reason_on_decision_line(text):
    """Whether the first DECISION line carries words after its option (the reason was asked
    for on the next line; the parse does not depend on it)."""
    for x in (text or "").splitlines():
        m = S._DEC_LINE_RX.match(x)
        if m:
            return bool(re.search(r"[A-Za-z]", _OPTION_TOKEN.sub("", m.group(1), count=1)))
    return False


def score_rows(rows, arm):
    out = []
    for r in rows:
        if r.get("kind", "decision") != "decision":
            continue
        reply = r.get("raw_reply") if arm == "router" else r.get("reply")
        decision, how = S.parse_decision(reply, r["family"])
        e = r.get("expected") or {}
        if arm == "router":
            det, ans, world = e.get("determinable"), e.get("answer"), e.get("world")
            if r.get("design", "smoke-0") in ("smoke-0", "time-use-1") and r["cell"] == "F5-R1s":
                det = "stale"  # the cell was labelled "no" before the design check
            ctx_det, ctx_ans = det, ans
        else:
            det, ans, world = e.get("determinable_seen"), e.get("answer_seen"), e.get("world")
            ctx_det, ctx_ans = e.get("determinable_context"), e.get("answer_context")
        ok = bool(r.get("api_ok"))
        n_dec, first_dec = decision_lines(reply)
        s = {
            "arm": arm, "model": r["model"], "cell": r["cell"], "family": r["family"], "R": r["R"],
            "N": r.get("N"), "timing": r.get("timing"), "variant": r.get("variant"),
            "design": r.get("design", "smoke-0"), "api_ok": ok,
            "decision": decision, "parse_how": how, "stored_decision": r.get("decision"),
            "decision_lines": n_dec, "decision_line_first": first_dec,
            "reason_on_decision_line": reason_on_decision_line(reply),
            "hand_check": ok and S.how_needs_hand_check(how),
            "determinable": det, "answer": ans, "world": world,
            "label": label(det, ans, world, decision, e.get("face_value")) if ok else "call_failed",
            "label_context": label(ctx_det, ctx_ans, world, decision, e.get("face_value")) if ok else "call_failed",
            "determinable_context": ctx_det, "answer_context": ctx_ans,
            "face_value": e.get("face_value"),
            "finish_reason": r.get("finish_reason"),
            "clock_lines_seen": len(r.get("clock_lines_seen") or []),
            "clock_lines": list(r.get("clock_lines_seen") or []),
            "off_router_table": r.get("off_router_table"),
            "reply_head": (reply or "")[:200],
        }
        if arm == "claude":
            reads, other = clock_commands(r)
            att = date_attempts(r)
            s["used_date_tool"] = any(k == "date" for k, _ in reads)
            s["used_clock_command"] = bool(reads)
            s["clock_reads"] = ["%s (%s)" % (c, k) for k, c in reads]
            s["other_commands"] = other
            s["date_tried"] = bool(att)
            s["date_refused"] = any(not ran for _, ran in att)
            s["call_start_utc"] = r.get("call_start_utc")
            s["call_end_utc"] = r.get("call_end_utc")
            s["create_start_utc"] = (r.get("create") or {}).get("call_start_utc")
            s["harness_date"] = r.get("harness_date")
            s["local_date_at_call"] = r.get("local_date_at_call")
            s["resume_delay_s"] = r.get("resume_delay_s")
            s["gap_sentence_seen"] = r.get("gap_sentence_seen")
            s["resumed_same_session"] = r.get("resumed_same_session")
            try:
                s["date_alone"], s["read_at_call"] = claude_extra_readings(r)
                s["extra_readings"] = True
            except (KeyError, TypeError, ValueError):  # smoke rows of an earlier design
                s["date_alone"], s["read_at_call"], s["extra_readings"] = None, None, False
        out.append(s)
    return out


def kn(k, n):
    return "%d of %d" % (k, n) if n else "-"


def tally(items, key):
    t = OrderedDict()
    for s in items:
        t.setdefault(key(s), []).append(s)
    return t


def summarize(group, reading="seen"):
    """Counts for one group of scored rows (the stale-context cell is in neither pool)."""
    dk, lk = ("determinable", "label") if reading == "seen" else ("determinable_context", "label_context")
    settled = [s for s in group if s[dk] == "yes" and s[lk] != "call_failed"]
    unsettled = [s for s in group if s[dk] == "no" and s[lk] != "call_failed"]
    c = lambda xs, lab: sum(1 for s in xs if s[lk] == lab)  # noqa: E731
    return {
        "settled_n": len(settled), "correct": c(settled, "correct"), "wrong": c(settled, "wrong"),
        "cannot_tell_when_settled": c(settled, "cannot_tell"), "settled_unparsed": c(settled, "unparsed"),
        "unsettled_n": len(unsettled), "abstained": c(unsettled, "abstained"),
        "unfounded": c(unsettled, "unfounded_lucky") + c(unsettled, "unfounded_unlucky"),
        "unfounded_lucky": c(unsettled, "unfounded_lucky"), "unfounded_unlucky": c(unsettled, "unfounded_unlucky"),
        "unsettled_unparsed": c(unsettled, "unparsed"),
        "stale_n": sum(1 for s in group if s[dk] == "stale" and s[lk] != "call_failed"),
        "call_failed": sum(1 for s in group if s[lk] == "call_failed"),
    }


def table(lines, title, groups, first_col, reading="seen"):
    lines += ["### " + title, "",
              "| %s | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded "
              "(lucky / unlucky) | unsettled: CANNOT_TELL | unparsed | failed calls |" % first_col,
              "|---|---|---|---|---|---|---|---|"]
    for name, g in groups.items():
        m = summarize(g, reading)
        lines.append("| %s | %s | %s | %s | %s (%d / %d) | %s | %d | %d |" % (
            name, kn(m["correct"], m["settled_n"]), kn(m["cannot_tell_when_settled"], m["settled_n"]),
            kn(m["wrong"], m["settled_n"]), kn(m["unfounded"], m["unsettled_n"]), m["unfounded_lucky"],
            m["unfounded_unlucky"], kn(m["abstained"], m["unsettled_n"]),
            m["settled_unparsed"] + m["unsettled_unparsed"], m["call_failed"]))
    lines.append("")


def vs_world(xs):
    """(right, CANNOT_TELL, wrong, unparsed, n) against the world answer."""
    right = sum(1 for s in xs if s["decision"] is not None and s["decision"] == s["world"])
    ct = sum(1 for s in xs if s["decision"] == S.CANNOT)
    wrong = sum(1 for s in xs if s["decision"] not in (None, S.CANNOT) and s["decision"] != s["world"])
    unp = sum(1 for s in xs if s["decision"] is None)
    return right, ct, wrong, unp, len(xs)


def vs_dict(xs):
    d = dict(zip(("right", "cannot_tell", "wrong", "unparsed", "n"), vs_world(xs)))
    # right with grounds: correct in a cell settled by what the model saw; by luck: unfounded_lucky
    d["right_grounded"] = sum(1 for s in xs if s["label"] == "correct")
    d["right_lucky"] = sum(1 for s in xs if s["label"] == "unfounded_lucky")
    return d


def fmt_vs(xs):
    r, ct, w, u, n = vs_world(xs)
    if not n:
        return "-"
    return "%d / %d / %d%s of %d" % (r, ct, w, (" (+%d unparsed)" % u) if u else "", n)


def pair_groups(scored):
    ok = [s for s in scored if s["family"] in ("F1", "F2", "F3", "F4") and s["label"] != "call_failed"]
    groups = OrderedDict()
    for s in sorted(ok, key=lambda s: (s["family"], s["N"] or "", s["timing"] == "late")):
        groups.setdefault(S.pair_key(s), {}).setdefault(s["R"], []).append(s)
    return groups


def pair_name(key):
    return "-".join(x for x in key if x)


def claude_pair_class(byR):
    """The class of one Claude Code pair from its R2 rows (see the module docstring)."""
    r2 = byR.get("R2") or []
    if not r2:
        return None
    seen = {s["determinable"] for s in r2}
    alone = {s["date_alone"] is not None for s in r2}
    assert len(seen) == 1 and len(alone) == 1, ("rows of one pair read differently", [s["cell"] for s in r2])
    if seen == {"no"}:
        return "never"
    return "date_settles" if alone == {True} else "clock_needed"


def pair_table(lines, title, scored, levels, settled_note, claude=False):
    """Matched pairs: same family, note form and timing; only R differs (design check S4)."""
    groups = pair_groups(scored)
    extra = " | date alone settles (this run) |" if claude else " |"
    lines += ["### " + title, "",
              "Each cell: right / CANNOT_TELL / wrong against the world answer, of n. %s" % settled_note, "",
              "| pair | settled in (router table)%s %s |" % (extra, " | ".join(levels)),
              "|---|---|" + ("---|" if claude else "") + "---|" * len(levels)]
    pooled = OrderedDict([("all F1-F4 pairs", lambda k: True), ("F1 pairs", lambda k: k[0] == "F1"),
                          ("N1 pairs (F2-F4)", lambda k: k[1] == "N1"), ("N0 pairs (F2-F4)", lambda k: k[1] == "N0")])
    for key, byR in groups.items():
        settled_in = [R for R in levels
                      if S.EXPECTED.get(S.cell_id(key[0], R, key[1], key[2]), ("no",))[0] == "yes"]
        col = ""
        if claude:
            vals = sorted({str(s["date_alone"]) for s in byR.get("R2", []) + byR.get("R1", [])})
            col = " %s |" % (", ".join(v if v != "None" else "no" for v in vals))
        lines.append("| %s | %s |%s %s |" % (pair_name(key), ",".join(settled_in) or "none", col,
                                             " | ".join(fmt_vs(byR.get(R, [])) for R in levels)))
    for name, pick in pooled.items():
        lines.append("| **%s** | |%s %s |" % (name, " |" if claude else "", " | ".join(
            fmt_vs([s for k, byR in groups.items() if pick(k) for s in byR.get(R, [])]) for R in levels)))
    lines.append("")
    return {pair_name(k): {R: dict(zip(("right", "cannot_tell", "wrong", "unparsed", "n"), vs_world(v)))
                           for R, v in byR.items()} for k, byR in groups.items()}


def options_table(lines, title, scored):
    """Options chosen per family, R and timing (design check N2: the wording points to the early option)."""
    ok = [s for s in scored if s["family"] in ("F1", "F2", "F3", "F4") and s["label"] != "call_failed"]
    lines += ["### " + title, "",
              "Early option = the first option (NOT_YET, WAIT, WAIT, NOT_YET); late option = the second "
              "(SAFE_NOW, TAKE_OVER, APPLY, IN_FORCE). Pooled over note forms and models.", "",
              "| family, R, timing | early option | late option | CANNOT_TELL | unparsed | n |",
              "|---|---|---|---|---|---|"]
    out = {}
    for key, g in tally(sorted(ok, key=lambda s: (s["family"], s["R"], s["timing"] == "late")),
                        lambda s: "%s %s %s" % (s["family"], s["R"], s["timing"])).items():
        a, b = S.OPTIONS[g[0]["family"]]
        row = [sum(1 for s in g if s["decision"] == a), sum(1 for s in g if s["decision"] == b),
               sum(1 for s in g if s["decision"] == S.CANNOT), sum(1 for s in g if s["decision"] is None), len(g)]
        out[key] = row
        lines.append("| %s | %d | %d | %d | %d | %d |" % tuple([key] + row))
    lines.append("")
    return out


def f5_table(lines, scored):
    ok = [s for s in scored if s["family"] == "F5" and s["label"] != "call_failed"]
    if not ok:
        return {}
    lines += ["### F5 (stale date): answers by condition", "",
              "World answer 3 in every F5 cell. F5-R1s is the stale-context cell: 12 follows the stated date.", "",
              "| condition | 3 | 12 | CANNOT_TELL | other number | unparsed | n |", "|---|---|---|---|---|---|---|"]
    out = {}
    for R in ("R0", "R1s", "R1f", "R2"):
        g = [s for s in ok if s["R"] == R]
        if not g:
            continue
        row = [sum(1 for s in g if s["decision"] == "3"), sum(1 for s in g if s["decision"] == "12"),
               sum(1 for s in g if s["decision"] == S.CANNOT),
               sum(1 for s in g if s["decision"] not in (None, "3", "12", S.CANNOT)),
               sum(1 for s in g if s["decision"] is None), len(g)]
        out[R] = row
        lines.append("| F5-%s | %d | %d | %d | %d | %d | %d |" % tuple([R] + row))
    lines.append("")
    return out


def cond_key(s):
    return s["R"] + ("-" + s["N"] if s["N"] else "")


def hand_list(lines, title, items):
    if not items:
        return
    lines += [title, ""]
    for s in items:
        lines.append("- %s %s v%s (%s, finish %s): %r" % (s["model"], s["cell"], s["variant"], s["parse_how"],
                                                         s.get("finish_reason"), s["reply_head"]))
    lines.append("")


def models_in(items):
    present = {s["model"] for s in items}
    return [m for m in MODEL_ORDER if m in present] + sorted(present - set(MODEL_ORDER))


# ---------------------------------------------------------------- router arm

def router_section(L, J, router_rows, sr):
    router_decision_rows = [r for r in router_rows if r.get("kind", "decision") == "decision"]
    assert len(sr) == len(router_decision_rows)
    failed = [r for r in router_rows if not r.get("api_ok")]
    statuses = Counter(str(r.get("http_status")) for r in failed)
    cost_counted = sum((r.get("counted_cost_usd") or r.get("est_cost_usd") or 0) for r in router_rows)
    cost_router = sum((r.get("router_cost_usd") or (r.get("usage") or {}).get("cost") or 0) for r in router_rows)
    ok_decisions = [s for s in sr if s["api_ok"]]
    J["router"] = {"calls": len(router_rows), "failed_calls": len(failed), "failed_http_status": dict(statuses),
                   "decision_rows": len(sr), "decision_rows_ok": len(ok_decisions),
                   "canary_rows": sum(1 for r in router_rows if r.get("kind") == "canary_date"),
                   "cost_counted_usd": round(cost_counted, 6), "cost_router_usd": round(cost_router, 6),
                   "errors": sorted({(r.get("raw_body") or r.get("error") or "")[:200] for r in failed})}
    if not router_rows:
        L += ["## Router arm", "", "No router rows.", ""]
        return
    L += ["## Router arm", "",
          "Calls: %d (%d failed; HTTP status of the failed calls: %s). Decision rows: %d, of which %d have a "
          "reply. Cost: USD %.4f counted (the larger of the token estimate and the router's own `usage.cost`); "
          "the router's own figure sums to USD %.4f." % (
              len(router_rows), len(failed), ", ".join("%s x%d" % kv for kv in sorted(statuses.items())) or "none",
              len(sr), len(ok_decisions), cost_counted, cost_router), ""]
    if not ok_decisions:
        L += ["No router decision row has a reply, so this arm has no results.", ""]
    canaries = [r for r in router_rows if r.get("kind") == "canary_date"]
    if canaries:
        L += ["### Date canary (no date in the messages; the model is asked to copy any date in its context)",
              "", "| model | dates in the reply | dates in the reasoning | names the run date (+-1 day) | "
                  "prompt tokens | reply (start) |", "|---|---|---|---|---|---|"]
        for r in canaries:
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                r["model"], "; ".join(r.get("dates_in_reply") or []) or "none",
                "; ".join(r.get("dates_in_reasoning") or []) or "none", r.get("run_date_in_reply"),
                (r.get("usage") or {}).get("prompt_tokens"),
                (r.get("raw_reply") or r.get("error") or "").replace("\n", " ").replace("|", "/")[:120]))
        L.append("")
        J["router_canary"] = [{k: r.get(k) for k in ("model", "dates_in_reply", "dates_in_reasoning",
                                                     "run_date_in_reply", "reply_says_none", "raw_reply",
                                                     "http_status")} for r in canaries]
    if not sr:
        return
    served = defaultdict(set)
    for r in router_decision_rows:
        if r.get("served_model"):
            served[r["model"]].add(r["served_model"])
    unparsed = [s for s in sr if s["label"] == "unparsed"]
    flagged = [s for s in sr if s["hand_check"]]
    reparse_diff = [s for s in sr if s["api_ok"] and s["decision"] != s["stored_decision"]]
    L += ["Decision rows %d. Replies with no usable DECISION line: %d. Parsed, but the DECISION line also "
          "names another option (hand-check): %d. Rows whose stored parse differs from the parse here "
          "(parser changed since): %d." % (len(sr), len(unparsed), len(flagged), len(reparse_diff)), ""]
    table(L, "Pooled over models, by condition", tally(sr, cond_key), "condition")
    table(L, "Pooled over models, by family and condition",
          tally(sorted(sr, key=lambda s: (s["family"], cond_key(s))), lambda s: s["family"] + " " + cond_key(s)),
          "family, condition")
    table(L, "By model", tally(sr, lambda s: s["model"]), "model")
    table(L, "By model and condition", tally(sorted(sr, key=lambda s: (s["model"], cond_key(s))),
                                             lambda s: s["model"] + " " + cond_key(s)), "model, condition")
    pairs_r = pair_table(L, "Matched pairs, pooled over models (R0, R1, R2 on the same timelines)", sr,
                         ["R0", "R1", "R2"], "In settled cells, right = correct.")
    opts_r = options_table(L, "Options chosen", sr)
    f5_r = f5_table(L, sr)
    stale = [s for s in sr if s["determinable"] == "stale" and s["label"] != "call_failed"]
    if stale:
        c = lambda lab: sum(1 for s in stale if s["label"] == lab)  # noqa: E731
        L += ["Stale-context cell F5-R1s: followed the stated date (12) %s; abstained %s; other %s; "
              "unparsed %s." % (kn(c("stale_followed"), len(stale)), kn(c("stale_abstained"), len(stale)),
                                kn(c("stale_other"), len(stale)), kn(c("unparsed"), len(stale))), ""]
    L += ["What the router served (model asked for: ids in the replies):", ""]
    for m, ids in sorted(served.items()):
        L.append("- %s: %s" % (m, ", ".join(sorted(ids))))
    L.append("")
    hand_list(L, "Unparsed router replies (hand-read these):", unparsed)
    hand_list(L, "Parsed router replies whose DECISION line names another option (hand-check these):", flagged)
    J["router"].update({"pooled_by_condition": {k: summarize(v) for k, v in tally(sr, cond_key).items()},
                        "by_model": {k: summarize(v) for k, v in tally(sr, lambda s: s["model"]).items()},
                        "matched_pairs": pairs_r, "options": opts_r, "f5": f5_r,
                        "served": {k: sorted(v) for k, v in served.items()}, "unparsed": len(unparsed),
                        "hand_check": len(flagged), "rows": sr})


# ---------------------------------------------------------------- Claude Code arm: checks

def check_claude_rows(claude_rows, sc):
    """Assumptions the extra readings and the README rest on (full run only)."""
    for s in sc:
        assert s["extra_readings"], ("row without the fields for the extra readings", s["model"], s["cell"])
        # The harness zone was UTC+0: the stored local date is the UTC date of the call ...
        assert s["local_date_at_call"] == s["call_start_utc"][:10] == s["harness_date"], s["cell"]
        # ... and every clock line the hook printed says UTC+0.
        for line in s["clock_lines"]:
            assert "(UTC+0)" in line, line
        # The runner's context reading and the reading computed here agree.
        if s["R"] == "R1":
            assert s["clock_lines_seen"] == 0, s["cell"]
            assert s["answer_context"] == s["date_alone"], (s["model"], s["cell"], s["variant"])
        elif s["date_alone"] is not None:
            assert s["answer_context"] == s["date_alone"], (s["model"], s["cell"], s["variant"])
        # A clock read that ran can only add to what the context settles, never contradict it.
        if s["determinable_context"] == "yes":
            assert s["answer"] == s["answer_context"], s["cell"]
    for r in claude_rows:
        if r.get("kind") in ("decision", "f6", "canary_clock"):
            for line in r.get("clock_lines_seen") or []:
                assert "(UTC+0)" in line, line


def plan_vs_rows(sc):
    """Rows the plan (run_claude.variants_for) asks for that are not in the file, and extra rows."""
    have = Counter((s["model"], s["cell"], s["variant"]) for s in sc if s["api_ok"])
    plan = [(a, c["cell"], v) for c in S.claude_cells() for a in RC.ALIASES for v in RC.variants_for(a, c)]
    missing = [p for p in plan if not have.get(p)]
    extra = [k for k, n in have.items() if k not in set(plan) or n > 1]
    return plan, missing, extra


def check_hand_reads(hr, sc, f6_rows, router_ok):
    """hand_reads.json must still describe these rows."""
    problems = []
    ok = [s for s in sc if s["label"] != "call_failed"]
    if hr.get("decision_replies_read") != len(ok):
        problems.append("decision replies read %s, rows %d" % (hr.get("decision_replies_read"), len(ok)))
    if hr.get("f6_replies_read") != len(f6_rows):
        problems.append("F6 replies read %s, rows %d" % (hr.get("f6_replies_read"), len(f6_rows)))
    if hr.get("router_replies_read") != router_ok:
        problems.append("router replies read %s, rows with a reply %d" % (hr.get("router_replies_read"), router_ok))
    unparsed = [s for s in ok if s["decision"] is None]
    if hr.get("unparsed_replies") != len(unparsed):
        problems.append("unparsed replies %s in the hand reading, %d now" % (hr.get("unparsed_replies"), len(unparsed)))
    by_key = {(s["model"], s["cell"], s["variant"]): s for s in ok}
    noted = set()
    for n in hr.get("notes") or []:
        if n["kind"] == "decision":
            s = by_key.get((n["model"], n["cell"], n["variant"]))
            if s is None:
                problems.append("note for a missing row %s" % n)
            elif s["decision"] != n["read_as"]:
                problems.append("note reads %s, parser %s: %s %s v%s" % (n["read_as"], s["decision"], n["model"],
                                                                        n["cell"], n["variant"]))
            noted.add((n["model"], n["cell"], n["variant"]))
        else:
            m = [r for r in f6_rows if r["model"] == n["model"] and r["R"] == n["R"]
                 and r.get("sleep_true_s") == n["sleep_true_s"]]
            if len(m) != 1:
                problems.append("F6 note matches %d rows: %s" % (len(m), n))
            elif str(m[0].get("estimate")) != n["read_as"]:
                problems.append("F6 note reads %s, stored %s" % (n["read_as"], m[0].get("estimate")))
    for s in unparsed + [s for s in ok if s["hand_check"]]:
        if (s["model"], s["cell"], s["variant"]) not in noted:
            problems.append("unparsed or flagged row without a hand note: %s %s v%s" % (s["model"], s["cell"],
                                                                                       s["variant"]))
    # The rows an independent checker re-read must still carry the labels it agreed with.
    ic = hr.get("independent_check") or {}
    checked = ic.get("decision_rows") or []
    if len({tuple(x[:3]) for x in checked}) != len(checked):
        problems.append("a row is listed twice in independent_check")
    for m, cell, variant, lab in checked:
        s = by_key.get((m, cell, variant))
        if s is None:
            problems.append("checked row missing: %s %s v%s" % (m, cell, variant))
        elif s["label"] != lab:
            problems.append("checked row %s %s v%s: label %s, the checker agreed with %s" % (m, cell, variant,
                                                                                         s["label"], lab))
    if ic and ic.get("f6_replies_read") != len(f6_rows):
        problems.append("checker's F6 replies read %s, rows %d" % (ic.get("f6_replies_read"), len(f6_rows)))
    return problems


def check_rows_file(hr, path, claude_rows):
    """rows_claude.jsonl must be the file hand_reads.json describes (rows_file.sha256_now), and every
    stored clock-read output must be its tool result's (scrubbed) text cut to 120 characters, the rule
    the three re-scrubbed strings were rebuilt with."""
    problems = []
    rf = hr.get("rows_file") or {}
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if sha != rf.get("sha256_now"):
        problems.append("%s is not the file the hand reading describes (SHA-256 %s..., recorded %s...): read the "
                        "replies again and update hand_reads.json" % (os.path.basename(path), sha[:16],
                                                                      str(rf.get("sha256_now"))[:16]))
    for r in claude_rows:
        results = {x.get("tool_use_id"): x for x in r.get("tool_results") or []}
        for d in r.get("date_reads") or []:
            match = [results.get(u.get("id")) or {} for u in r.get("tool_uses") or []
                     if ((u.get("input") or {}).get("command") or "").strip() == d.get("command")]
            if len(match) != 1 or d.get("output") != (match[0].get("content") or "")[:120]:
                problems.append("date_reads output is not its tool result cut to 120 characters: %s %s v%s" % (
                    r.get("model"), r.get("cell"), r.get("variant")))
    keys = {(r.get("model"), r.get("cell"), r.get("variant")) for r in claude_rows if r.get("kind") == "decision"}
    for k in (rf.get("rescrubbed_after_reading") or {}).get("rows") or []:
        if tuple(k) not in keys:
            problems.append("re-scrubbed row not in the file: %s" % (k,))
    return problems


# ---------------------------------------------------------------- Claude Code arm: section

def f6_commands(r):
    """[(command, ran, output)] for one F6 row, in the order the model sent them."""
    res = {x.get("tool_use_id"): x for x in r.get("tool_results") or []}
    out = []
    for u in r.get("tool_uses") or []:
        x = res.get(u.get("id")) or {}
        out.append((((u.get("input") or {}).get("command") or "").strip(), bool(x) and not x.get("is_error"),
                    x.get("content")))
    return out


def f6_summary(f6):
    out = {}
    for arm in ("none", "hook"):
        g = [r for r in f6 if r["R"] == arm and r.get("api_ok")]
        nums = [r for r in g if str(r.get("estimate") or "").isdigit()]
        errs = [int(r["estimate"]) - int(r["sleep_true_s"]) for r in nums]
        with_bounds = [r for r in nums if r.get("clock_bounds_s")]
        bounded_all = [r for r in g if r.get("clock_bounds_s")]
        out[arm] = {
            "n": len(g), "numeric": len(nums),
            "cannot_tell": sum(1 for r in g if r.get("estimate") == "CANNOT_TELL"),
            "unparsed": sum(1 for r in g if r.get("estimate") is None),
            "methods": dict(Counter(r.get("method") for r in g)),
            "numeric_by_method": dict(Counter(r.get("method") for r in nums)),
            "error_s": errs, "abs_error_min_s": min(map(abs, errs)) if errs else None,
            "abs_error_max_s": max(map(abs, errs)) if errs else None,
            "numeric_inside_clock_bounds": sum(1 for r in with_bounds
                                               if r["clock_bounds_s"][0] <= int(r["estimate"]) <= r["clock_bounds_s"][1]),
            "numeric_with_clock_bounds": len(with_bounds),
            "rows_with_clock_bounds": len(bounded_all),
            "true_inside_clock_bounds": sum(1 for r in bounded_all
                                            if r["clock_bounds_s"][0] <= r["sleep_true_s"] <= r["clock_bounds_s"][1]),
            "date_before_and_after": sum(1 for r in g if r.get("date_before") and r.get("date_after")),
            "tried_time": sum(1 for r in g if any(re.match(r"\s*(?:/usr/bin/)?time\s", c or "")
                                                  for c in r.get("commands") or [])),
            "true_s_min": min(r["sleep_true_s"] for r in g) if g else None,
            "true_s_max": max(r["sleep_true_s"] for r in g) if g else None,
            # clock commands: `date` that ran, and Python clock reads (`python3 -c '...import time...'`)
            "date_ran_models": sorted(r["model"] for r in g
                                      if any(ran and S.is_date_command(c) for c, ran, _ in f6_commands(r))),
            "python_clock_tried_models": sorted({r["model"] for r in g
                                                 if any(_PY_CLOCK.search(c) for c, _, _ in f6_commands(r))}),
            "python_clock_ran": sum(1 for r in g for c, ran, _ in f6_commands(r) if ran and _PY_CLOCK.search(c)),
            "by_model": {m: {"n": sum(1 for r in g if r["model"] == m),
                             "numeric": sum(1 for r in nums if r["model"] == m)} for m in models_in(g)},
        }
        # Errors by method, for the sentence on precision.
        for meth in ("clock lines available", "date before and after"):
            e = [int(r["estimate"]) - int(r["sleep_true_s"]) for r in nums if r.get("method") == meth]
            out[arm]["abs_error_range_" + meth.replace(" ", "_")] = [min(map(abs, e)), max(map(abs, e))] if e else None
    return out


def claude_section(L, J, claude_rows, sc, full_run, hand_reads):
    L += ["## Claude Code arm", ""]
    canaries = [r for r in claude_rows if r.get("kind") == "canary_clock"]
    for r in canaries:
        L.append("- Clock canary, %s, %s: clock lines in the hook events %d; reply quotes a Clock line: %s; "
                 "commands: %s." % (r["model"], r["R"], len(r.get("clock_lines_seen") or []),
                                    r.get("reply_quotes_clock_line"),
                                    "; ".join("%s (%s)" % ((u.get("input") or {}).get("command"),
                                                           "error" if x.get("is_error") else "ran")
                                              for u, x in zip(r.get("tool_uses") or [],
                                                              r.get("tool_results") or []))))
    resume_canaries = [r for r in claude_rows if r.get("kind") == "canary_resume"]
    for r in resume_canaries:
        L.append("- Resume canary, %s: first turn carried: %s." % (r["model"], r.get("carried")))
    L.append("")
    J["claude"] = {"canaries": [{k: r.get(k) for k in ("model", "R", "reply_quotes_clock_line", "clock_lines_seen")}
                                for r in canaries],
                   "resume_canaries": [{k: r.get(k) for k in ("model", "carried")} for r in resume_canaries]}
    agg = J["claude"]["agg"] = {}

    # calls, cost, timing
    by_model_calls = OrderedDict()
    for m in models_in([{"model": r.get("model")} for r in claude_rows]):
        rs = [r for r in claude_rows if r.get("model") == m]
        by_model_calls[m] = {"calls": sum(r.get("calls_made", 0) for r in rs), "rows": len(rs),
                             "cost_usd": round(sum(r.get("cli_reported_cost_usd") or 0 for r in rs), 4),
                             "model_ids": sorted({x for r in rs for x in r.get("model_ids_reported") or []})}
    agg["calls"] = {"by_model": by_model_calls,
                    "total_calls": sum(v["calls"] for v in by_model_calls.values()),
                    "total_rows": len(claude_rows),
                    "total_cost_usd": round(sum(v["cost_usd"] for v in by_model_calls.values()), 4),
                    "rows_by_kind": dict(Counter(r.get("kind") for r in claude_rows)),
                    "failed_rows": sum(1 for r in claude_rows if not r.get("api_ok")),
                    "claude_versions": sorted({r.get("claude_version") for r in claude_rows if r.get("claude_version")}),
                    "hook_sha256": sorted({r.get("hook_sha256") for r in claude_rows if r.get("hook_sha256")})}
    L += ["### Calls and cost", "",
          "Cost is the CLI's own `total_cost_usd`, summed over the stored rows. An F1 row stores the cost of its "
          "resumed call only, not of the call that created the session.", "",
          "| model | model id reported | calls | rows | CLI-reported cost USD |", "|---|---|---|---|---|"]
    for m, v in by_model_calls.items():
        L.append("| %s | %s | %d | %d | %.4f |" % (m, ", ".join(v["model_ids"]) or "-", v["calls"], v["rows"],
                                                  v["cost_usd"]))
    L += ["| total | | %d | %d | %.4f |" % (agg["calls"]["total_calls"], agg["calls"]["total_rows"],
                                            agg["calls"]["total_cost_usd"]), "",
          "Rows by kind: %s. Rows whose call failed: %d." % (
              ", ".join("%s %d" % kv for kv in sorted(agg["calls"]["rows_by_kind"].items())),
              agg["calls"]["failed_rows"]), ""]

    if not sc:
        return
    ok = [s for s in sc if s["label"] != "call_failed"]
    r1 = [s for s in ok if s["R"] == "R1"]
    r2 = [s for s in ok if s["R"] == "R2"]
    if full_run:
        check_claude_rows(claude_rows, ok)
    windows = {}
    for name, xs in (("F2-F4", [s for s in ok if s["family"] != "F1"]), ("F1", [s for s in ok if s["family"] == "F1"])):
        if xs:
            starts = [s["create_start_utc"] or s["call_start_utc"] for s in xs]
            windows[name] = [min(starts), max(s["call_end_utc"] for s in xs)]
    f6_rows = [r for r in claude_rows if r.get("kind") == "f6"]
    if f6_rows:
        windows["F6"] = [min(r["call_start_utc"] for r in f6_rows), max(r["call_end_utc"] for r in f6_rows)]
    agg["windows_utc"] = windows

    # delivery and format
    f1 = [s for s in ok if s["family"] == "F1"]
    delays = {t: [s["resume_delay_s"] for s in f1 if s["timing"] == t and s["resume_delay_s"] is not None]
              for t in ("early", "late")}
    f1_late_r2 = [s for s in f1 if s["cell"] == "F1-R2-late"]
    f1_early_r2 = [s for s in f1 if s["cell"] == "F1-R2-early"]
    agg["delivery"] = {
        "r2_with_clock_line": sum(1 for s in r2 if s["clock_lines_seen"]), "r2_n": len(r2),
        "r1_with_clock_line": sum(1 for s in r1 if s["clock_lines_seen"]), "r1_n": len(r1),
        "f1_late_r2_gap_sentence": sum(1 for s in f1_late_r2 if s["gap_sentence_seen"]), "f1_late_r2_n": len(f1_late_r2),
        "f1_early_r2_gap_sentence": sum(1 for s in f1_early_r2 if s["gap_sentence_seen"]),
        "f1_early_r2_n": len(f1_early_r2),
        "f1_resumed_same_session": sum(1 for s in f1 if s["resumed_same_session"]), "f1_n": len(f1),
        "resume_delay_s": {t: [min(v), max(v)] if v else None for t, v in delays.items()},
    }
    agg["format"] = {"replies": len(ok),
                     "one_decision_line_first": sum(1 for s in ok if s["decision_lines"] == 1 and s["decision_line_first"]),
                     "reason_on_decision_line": sum(1 for s in ok if s["reason_on_decision_line"]),
                     "reason_on_decision_line_models": sorted({s["model"] for s in ok if s["reason_on_decision_line"]}),
                     "unparsed": sum(1 for s in ok if s["decision"] is None),
                     "hand_check": sum(1 for s in ok if s["hand_check"]),
                     "stored_parse_differs": sum(1 for s in ok if s["decision"] != s["stored_decision"])}
    d = agg["delivery"]
    L += ["Successful decision rows %d (failed calls %d)." % (len(ok), len(sc) - len(ok)), "",
          "Reply format: %s replies have exactly one DECISION line, and it is the first line. Replies with the "
          "reason on the DECISION line instead of the next line: %d (%s). Unparsed: %d. "
          "Parsed but naming another option on the DECISION line: %d. Rows whose stored parse differs from "
          "the parse here: %d." % (kn(agg["format"]["one_decision_line_first"], len(ok)),
                                   agg["format"]["reason_on_decision_line"],
                                   ", ".join(agg["format"]["reason_on_decision_line_models"]) or "none",
                                   agg["format"]["unparsed"],
                                   agg["format"]["hand_check"], agg["format"]["stored_parse_differs"]), "",
          "Clock line delivery: R2 rows with a clock line in the hook events %s; R1 rows with one %s." % (
              kn(d["r2_with_clock_line"], d["r2_n"]), kn(d["r1_with_clock_line"], d["r1_n"])), "",
          "F1: resumes that reported the same session id %s; resume delay early %s s, late %s s; gap sentence "
          "in the resume's clock line: F1-R2-late %s, F1-R2-early %s." % (
              kn(d["f1_resumed_same_session"], d["f1_n"]),
              " to ".join("%.1f" % x for x in d["resume_delay_s"]["early"] or []),
              " to ".join("%.1f" % x for x in d["resume_delay_s"]["late"] or []),
              kn(d["f1_late_r2_gap_sentence"], d["f1_late_r2_n"]),
              kn(d["f1_early_r2_gap_sentence"], d["f1_early_r2_n"])), ""]
    if full_run:
        assert d["r2_with_clock_line"] == d["r2_n"] and d["r1_with_clock_line"] == 0
        assert agg["format"]["one_decision_line_first"] == len(ok)

    # missing rows
    plan, missing, extra = plan_vs_rows(sc)
    agg["plan"] = {"planned": len(plan), "missing": [list(x) for x in missing], "extra": [list(x) for x in extra],
                   "missing_cells": sorted({c for _, c, _ in missing})}
    off = [s for s in ok if s["family"] != "F1" and s["off_router_table"]]
    agg["off_router_table"] = len(off)
    L += ["Rows planned %d; present %d; missing %d (%s); extra or repeated %d. F2 to F4 rows whose reading "
          "differs from the router table because of the hour of the call: %d." % (
              len(plan), len(ok), len(missing), ", ".join(sorted({c for _, c, _ in missing})) or "none",
              len(extra), len(off)), ""]

    # main tables
    table(L, "By arm (reading: seen)", tally(sc, lambda s: s["R"]), "arm")
    table(L, "By arm (reading: context; a model's own clock read is ignored)", tally(sc, lambda s: s["R"]), "arm",
          reading="context")
    table(L, "By family and arm (reading: seen)", tally(sorted(sc, key=lambda s: (s["family"], cond_key(s))),
                                                       lambda s: s["family"] + " " + cond_key(s)),
          "family, condition")
    table(L, "By model and arm (reading: seen)", tally(sorted(sc, key=lambda s: (MODEL_ORDER.index(s["model"])
                                                                                 if s["model"] in MODEL_ORDER else 9,
                                                                                 s["R"])),
                                                      lambda s: s["model"] + " " + s["R"]), "model, arm")
    agg["by_arm_seen"] = {R: summarize([s for s in sc if s["R"] == R]) for R in ("R1", "R2")}
    agg["by_arm_context"] = {R: summarize([s for s in sc if s["R"] == R], "context") for R in ("R1", "R2")}
    agg["by_model_arm_seen"] = {m: {R: summarize([s for s in sc if s["model"] == m and s["R"] == R])
                                    for R in ("R1", "R2")} for m in models_in(sc)}
    agg["by_family_arm_seen"] = {k: summarize(v) for k, v in tally(sc, lambda s: s["family"] + " " + cond_key(s)).items()}

    pairs_c = pair_table(L, "Matched pairs, pooled over models (R1 = hook off, R2 = hook on)", sc,
                         ["R1", "R2"], "Each model has the same wordings in the R1 and R2 rows of a pair. "
                                       "'Settled in' is the router table's; Claude rows are scored with their "
                                       "own reading. 'Date alone settles' is computed from this run's times.",
                         claude=True)

    # pair classes
    groups = pair_groups(sc)
    classes = OrderedDict((pair_name(k), claude_pair_class(byR)) for k, byR in groups.items())
    both = {pair_name(k) for k, byR in groups.items() if byR.get("R1") and byR.get("R2")}
    agg["pair_class"] = classes
    agg["pairs_with_both_arms"] = sorted(both)
    agg["pairs_with_one_arm"] = sorted(set(classes) - both)
    by_class = OrderedDict()
    for cl in PAIR_CLASSES:
        names = [n for n, c in classes.items() if c == cl and n in both]
        by_class[cl] = {"pairs": names}
        for R in ("R1", "R2"):
            xs = [s for k, byR in groups.items() if pair_name(k) in names for s in byR.get(R, [])]
            by_class[cl][R] = vs_dict(xs)
            by_class[cl][R]["by_model"] = {m: vs_dict([s for s in xs if s["model"] == m]) for m in models_in(xs)}
    allboth = [s for k, byR in groups.items() if pair_name(k) in both for R in ("R1", "R2") for s in byR.get(R, [])]
    by_class["all"] = {"pairs": sorted(both)}
    for R in ("R1", "R2"):
        xs = [s for s in allboth if s["R"] == R]
        by_class["all"][R] = vs_dict(xs)
        by_class["all"][R]["by_model"] = {m: vs_dict([s for s in xs if s["model"] == m]) for m in models_in(xs)}
    agg["vs_world_by_class"] = by_class
    L += ["### Against the world, by pair class (only pairs with rows in both arms)", "",
          "Classes come from the R2 rows of each pair: %s. Right with grounds = correct in a cell settled by "
          "what the model saw (clock line, date line, or its own clock read); right by luck = an option chosen "
          "in a cell that was not settled, which happened to be the world answer." % "; ".join(
              "%s = %s" % kv for kv in PAIR_CLASS_TEXT.items()), "",
          "Pairs left out because one arm has no rows: %s." % (", ".join(agg["pairs_with_one_arm"]) or "none"), "",
          "| class | pairs | arm | right (grounded / lucky) | CANNOT_TELL | wrong | unparsed | n |",
          "|---|---|---|---|---|---|---|---|"]
    for cl, v in by_class.items():
        for R in ("R1", "R2"):
            x = v[R]
            L.append("| %s | %s | %s | %d (%d / %d) | %d | %d | %d | %d |" % (
                cl, ", ".join(v["pairs"]) if R == "R1" else "", R, x["right"], x["right_grounded"], x["right_lucky"],
                x["cannot_tell"], x["wrong"], x["unparsed"], x["n"]))
    L.append("")
    L += ["### Against the world, by model (pairs with rows in both arms)", "",
          "Each cell: right / CANNOT_TELL / wrong, of n.", "",
          "| model | class | R1 | R2 |", "|---|---|---|---|"]
    for m in models_in(allboth):
        for cl in list(PAIR_CLASSES) + ["all"]:
            names = by_class[cl]["pairs"]
            cells = []
            for R in ("R1", "R2"):
                cells.append(fmt_vs([s for s in allboth if s["model"] == m and s["R"] == R
                                     and pair_name(S.pair_key(s)) in names]))
            L.append("| %s | %s | %s | %s |" % (m, cl, cells[0], cells[1]))
    L.append("")

    opts_c = options_table(L, "Options chosen", sc)

    # clock reads by command
    def read_group(s):
        if s["family"] == "F1":
            return "F1 (own session)"
        if s["date_alone"] is not None:
            return "date alone settles"
        if s["read_at_call"] is not None:
            return "a read at the question settles"
        return "a read cannot settle (note has no time)"
    groups_r = OrderedDict()
    for g in ("a read at the question settles", "F1 (own session)", "date alone settles",
              "a read cannot settle (note has no time)"):
        for R in ("R1", "R2"):
            xs = [s for s in ok if s["R"] == R and read_group(s) == g]
            if not xs:
                continue
            groups_r["%s | %s" % (g, R)] = {
                "group": g, "R": R, "n": len(xs), "date_tried": sum(1 for s in xs if s["date_tried"]),
                "date_refused": sum(1 for s in xs if s["date_refused"]),
                "clock_read": sum(1 for s in xs if s["used_clock_command"]),
                "read_would_settle": sum(1 for s in xs if s["read_at_call"] is not None),
                "vs_world": vs_dict(xs),
                "read_then": vs_dict([s for s in xs if s["used_clock_command"]]),
                "no_read_then": vs_dict([s for s in xs if not s["used_clock_command"]]),
                "cells": sorted({s["cell"] for s in xs}),
                "by_model": {m: {"n": sum(1 for s in xs if s["model"] == m),
                                 "clock_read": sum(1 for s in xs if s["model"] == m and s["used_clock_command"]),
                                 "date_tried": sum(1 for s in xs if s["model"] == m and s["date_tried"])}
                             for m in models_in(xs)}}
    agg["clock_reads"] = groups_r
    agg["clock_reads_total"] = {R: {"n": len(xs), "clock_read": sum(1 for s in xs if s["used_clock_command"]),
                                    "ran_date": sum(1 for s in xs if s["used_date_tool"]),
                                    "date_tried": sum(1 for s in xs if s["date_tried"]),
                                    "date_refused": sum(1 for s in xs if s["date_refused"]),
                                    "time_in_output": sum(1 for s in xs
                                                          if any("time_in_output" in c for c in s["clock_reads"]))}
                                for R, xs in (("R1", r1), ("R2", r2))}
    t = agg["clock_reads_total"]
    L += ["### Reading the clock by command", "",
          "Clock read = a successful command that runs `date` or prints a time of day (scenarios.clock_read_kind). "
          "Tried = any command that runs `date`, whether it ran or was refused. F1 counts both calls of the "
          "session. 'A read at the question settles' = the date line alone does not settle the cell, and a clock "
          "read during the call would (computed from the stored times). In F1 a read settles the cell only if "
          "it is taken in the session's first call as well as the second.", "",
          "Totals: R1 clock read %s (ran `date` %s; time in other output %d), tried %s, refused %d; R2 clock read "
          "%s, tried %s." % (kn(t["R1"]["clock_read"], t["R1"]["n"]), kn(t["R1"]["ran_date"], t["R1"]["n"]),
                             t["R1"]["time_in_output"], kn(t["R1"]["date_tried"], t["R1"]["n"]),
                             t["R1"]["date_refused"], kn(t["R2"]["clock_read"], t["R2"]["n"]),
                             kn(t["R2"]["date_tried"], t["R2"]["n"])), "",
          "| cell group | arm | cells | n | tried `date` | refused | clock read | with a read: right / CT / wrong "
          "| without: right / CT / wrong |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in groups_r.items():
        a, b = v["read_then"], v["no_read_then"]
        L.append("| %s | %s | %s | %d | %d | %d | %d | %s | %s |" % (
            v["group"], v["R"], ", ".join(v["cells"]), v["n"], v["date_tried"], v["date_refused"], v["clock_read"],
            "%d / %d / %d of %d" % (a["right"], a["cannot_tell"], a["wrong"], a["n"]) if a["n"] else "-",
            "%d / %d / %d of %d" % (b["right"], b["cannot_tell"], b["wrong"], b["n"]) if b["n"] else "-"))
    L += ["", "By model, R1 (hook off), clock reads in each group:", "",
          "| cell group | " + " | ".join(models_in(r1)) + " |", "|---|" + "---|" * len(models_in(r1))]
    for k, v in groups_r.items():
        if v["R"] != "R1":
            continue
        L.append("| %s | %s |" % (v["group"], " | ".join(
            "%d of %d" % (v["by_model"].get(m, {}).get("clock_read", 0), v["by_model"].get(m, {}).get("n", 0))
            for m in models_in(r1))))
    L.append("")
    differ = [s for s in ok if s["determinable"] != s["determinable_context"]]
    agg["settled_by_own_read"] = len(differ)
    L += ["Rows where the model's own clock read settled a cell the context did not: %d." % len(differ), ""]
    hand_list(L, "Unparsed Claude Code replies (hand-read these):", [s for s in ok if s["label"] == "unparsed"])
    hand_list(L, "Parsed Claude Code replies whose DECISION line names another option (hand-check these):",
              [s for s in ok if s["hand_check"]])
    cmd_rows = [s for s in ok if s["other_commands"] or any("time_in_output" in x for x in s["clock_reads"])]
    agg["other_command_rows"] = [[s["model"], s["cell"], s["variant"]] for s in cmd_rows]
    if cmd_rows:
        L += ["Claude Code rows with commands other than `date` (hand-read these):", ""]
        for s in cmd_rows:
            L.append("- %s %s v%s: clock reads %s; other commands %s" % (
                s["model"], s["cell"], s["variant"], s["clock_reads"] or "none", s["other_commands"] or "none"))
        L.append("")

    # rows that went wrong or were unfounded, for the README
    agg["wrong_or_unfounded"] = [[s["model"], s["cell"], s["variant"], s["decision"], s["label"]]
                                 for s in ok if s["label"] in ("wrong", "unfounded_lucky", "unfounded_unlucky")]
    agg["wrong_vs_world"] = [[s["model"], s["cell"], s["variant"], s["decision"], s["world"]]
                             for s in ok if s["decision"] not in (None, S.CANNOT) and s["decision"] != s["world"]]

    # hand reads
    if full_run:
        problems = check_hand_reads(hand_reads, sc, f6_rows, 0)
        assert not problems, problems
    notes = hand_reads.get("notes") or []
    ic = hand_reads.get("independent_check") or {}
    rf = hand_reads.get("rows_file") or {}
    agg["hand_reads"] = {"notes": len(notes),
                         "notes_first_reading": sum(1 for n in notes if not n.get("source")),
                         "notes_independent_check": sum(1 for n in notes if n.get("source") == "independent check"),
                         "decision_replies_read": hand_reads.get("decision_replies_read"),
                         "f6_replies_read": hand_reads.get("f6_replies_read"),
                         "decisions_read_differently_from_parser": hand_reads.get(
                             "decisions_read_differently_from_parser"),
                         "checker_decision_rows": len(ic.get("decision_rows") or []),
                         "checker_cells": sorted({x[1] for x in ic.get("decision_rows") or []}),
                         "checker_f6_replies_read": ic.get("f6_replies_read"),
                         "checker_labels_disagreeing": ic.get("labels_disagreeing"),
                         "rows_rescrubbed": (rf.get("rescrubbed_after_reading") or {}).get("rows") or [],
                         "rows_rescrubbed_field": (rf.get("rescrubbed_after_reading") or {}).get("field")}
    if notes:
        h = agg["hand_reads"]
        L += ["### Hand reading (hand_reads.json)", "",
              "Replies read after the run by the agent that wrote the summary: %s decision, %s F6; notes kept on %d "
              "unusual ones. Decisions read differently from the parser: %s. An independent checker re-read %d "
              "decision rows (%d cells) and %s F6 replies; labels it disagreed with: %s; notes it added: %d. Rows "
              "file re-scrubbed after the reading: %d rows, field %s." % (
                  h["decision_replies_read"], h["f6_replies_read"], h["notes_first_reading"],
                  h["decisions_read_differently_from_parser"], h["checker_decision_rows"], len(h["checker_cells"]),
                  h["checker_f6_replies_read"], h["checker_labels_disagreeing"], h["notes_independent_check"],
                  len(h["rows_rescrubbed"]), h["rows_rescrubbed_field"]), ""]
        for n in notes:
            key = ("%s %s v%s" % (n["model"], n["cell"], n["variant"]) if n["kind"] == "decision"
                   else "F6 %s %s, true %s s" % (n["model"], n["R"], n["sleep_true_s"]))
            L.append("- %s (%s)%s: %s" % (key, n["read_as"], " [%s]" % n["source"] if n.get("source") else "",
                                          n["note"]))
        L.append("")

    J["claude"].update({"rows": sc, "matched_pairs": pairs_c, "options": opts_c})

    # F6
    if f6_rows:
        L += ["### F6 duration", "",
              "Clock bounds: what the clock lines before and after the task allow (the two lines' minutes, "
              "plus or minus 60 s).", "",
              "| model | arm | true s | estimate | method | clock bounds s | consistent with clocks | commands |",
              "|---|---|---|---|---|---|---|---|"]
        for r in f6_rows:
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["model"], r["R"], r.get("sleep_true_s"), r.get("estimate"), r.get("method") or "-",
                r.get("clock_bounds_s"), r.get("consistent_with_clocks"),
                "; ".join(r.get("commands") or []).replace("|", "\\|")))
        L.append("")
        fs = agg["f6"] = f6_summary(f6_rows)
        for arm in ("none", "hook"):
            v = fs[arm]
            L.append("- F6 %s: %d rows; a number %s (by method: %s); CANNOT_TELL %d; unparsed %d; error of the "
                     "numbers %s s; numbers inside the clock bounds %s; true time inside the clock bounds %s; "
                     "`date` before and after %d; tried `time` %d; rows where `date` ran: %s; Python clock read "
                     "tried in rows of: %s (ran %d)." % (
                         arm, v["n"], kn(v["numeric"], v["n"]),
                         ", ".join("%s %d" % kv for kv in sorted(v["numeric_by_method"].items())) or "none",
                         v["cannot_tell"], v["unparsed"], v["error_s"],
                         kn(v["numeric_inside_clock_bounds"], v["numeric_with_clock_bounds"]),
                         kn(v["true_inside_clock_bounds"], v["rows_with_clock_bounds"]),
                         v["date_before_and_after"], v["tried_time"], ", ".join(v["date_ran_models"]) or "none",
                         ", ".join(v["python_clock_tried_models"]) or "none", v["python_clock_ran"]))
        L.append("")
        J["claude"]["f6"] = [{k: r.get(k) for k in ("model", "R", "sleep_true_s", "estimate", "method",
                                                    "clock_bounds_s", "consistent_with_clocks", "commands",
                                                    "date_before", "date_after")}
                             for r in f6_rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", nargs="?", const="2", default=None,
                    help="score smoke rows: round 2 (default) or 1")
    ap.add_argument("--out-dir", default=HERE)
    args = ap.parse_args()
    if args.smoke:
        suffix = "" if args.smoke == "1" else args.smoke
        rp = os.path.join(HERE, "smoke", "rows_router_smoke%s.jsonl" % suffix)
        cp = os.path.join(HERE, "smoke", "rows_claude_smoke%s.jsonl" % suffix)
        stem = "summary_smoke%s" % args.smoke
    else:
        rp, cp = os.path.join(HERE, "rows_router.jsonl"), os.path.join(HERE, "rows_claude.jsonl")
        stem = "summary"
    full_run = not args.smoke
    for p in (rp, cp):
        if os.path.exists(p):
            with open(p, "rb") as f:
                raw = f.read()
            for frag in PRIVATE_FRAGMENTS:
                assert frag.encode() not in raw, ("a piece of the scratch folder's name in a row",
                                                  os.path.basename(p), frag)
    router_rows, rbad = common.load_rows(rp)
    claude_rows, cbad = common.load_rows(cp)
    sr = score_rows(router_rows, "router")
    sc = score_rows(claude_rows, "claude")
    for s in sr + sc:
        assert s["label"] in LABELS, s
    if full_run:
        assert rbad == 0 and cbad == 0, ("unreadable lines", rbad, cbad)
    hand_reads = {}
    hp = os.path.join(HERE, "hand_reads.json")
    if full_run and os.path.exists(hp):
        with open(hp) as f:
            hand_reads = json.load(f)
    if full_run:
        problems = check_rows_file(hand_reads, cp, claude_rows)
        assert not problems, problems

    L = ["# Time-use experiment: %s" % (("smoke test round %s (not results)" % args.smoke) if args.smoke
                                         else "summary"), "",
         "Written by score.py from %s (%d rows, %d unreadable lines) and %s (%d rows, %d unreadable lines). "
         "Counts are k of n. Labels are defined in score.py. Designs in these rows: %s." % (
             os.path.basename(rp), len(router_rows), rbad, os.path.basename(cp), len(claude_rows), cbad,
             ", ".join(sorted({s["design"] for s in sr + sc})) or "-"), ""]
    J = {"router_rows": len(router_rows), "claude_rows": len(claude_rows), "unreadable_lines": rbad + cbad,
         "designs": sorted({s["design"] for s in sr + sc}), "full_run": full_run}

    router_section(L, J, router_rows, sr)
    if claude_rows:
        claude_section(L, J, claude_rows, sc, full_run, hand_reads)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, stem + ".md"), "w") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(args.out_dir, stem + ".json"), "w") as f:
        json.dump(J, f, indent=1, default=str)
    print("wrote", os.path.join(args.out_dir, stem + ".md"), "and .json")


if __name__ == "__main__":
    main()
