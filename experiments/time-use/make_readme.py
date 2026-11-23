"""Write README.md for the time-use experiment from summary.json, scenarios.py and the rows.

    python3 -I -B make_readme.py                      # reads summary.json here, writes README.md here
    python3 -I -B make_readme.py SUMMARY.json OUT.md  # other paths (for a check before the real write)

Run score.py first. Every number in README.md comes from summary.json (written by
score.py from the rows), from the stored rows themselves (the example prompts), from
scenarios.py (the cell table and the timelines), from run_context_router.json (the
router models) or from hand_reads.json (the hand reading and the independent check).
The time the account's credit ran out is a constant here, checked (read only) against
the first HTTP 402 answer in ../consensus/groups.jsonl when that file exists.
A sentence that states a direction (more, fewer, none, all, only) has
an assert on the numbers it rests on, so a rerun with other data stops here instead
of printing a false sentence.
"""

import datetime as dt
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import common  # noqa: E402
import run_claude as RC  # noqa: E402
import run_router as RR  # noqa: E402
import scenarios as S  # noqa: E402

SUMMARY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "summary.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "README.md")
with open(SUMMARY) as f:
    J = json.load(f)
with open(os.path.join(HERE, "hand_reads.json")) as f:
    HR = json.load(f)
with open(os.path.join(HERE, "run_context_router.json")) as f:
    RCTX = json.load(f)
CROWS, _bad = common.load_rows(os.path.join(HERE, "rows_claude.jsonl"))
RROWS, _rbad = common.load_rows(os.path.join(HERE, "rows_router.jsonl"))
assert J["full_run"] and _bad == 0 and _rbad == 0

A = J["claude"]["agg"]
ROWS = J["claude"]["rows"]
PAIRS = J["claude"]["matched_pairs"]
OPTS = J["claude"]["options"]
VC = A["vs_world_by_class"]
CR = A["clock_reads"]
CRT = A["clock_reads_total"]
F6 = A["f6"]
MODELS = list(A["by_model_arm_seen"].keys())
RT = J["router"]


def kofn(k, n):
    return "%d of %d" % (k, n)


def rcw(d):
    """right / CANNOT_TELL / wrong of n, in words."""
    return "%d right, %d CANNOT_TELL, %d wrong (of %d)" % (d["right"], d["cannot_tell"], d["wrong"], d["n"])


def rcw_short(d):
    return "%d / %d / %d of %d" % (d["right"], d["cannot_tell"], d["wrong"], d["n"]) if d["n"] else "-"


def pair_sum(names, R):
    out = {"right": 0, "cannot_tell": 0, "wrong": 0, "unparsed": 0, "n": 0}
    for p in names:
        for k in out:
            out[k] += PAIRS[p].get(R, {}).get(k, 0)
    return out


def hm(iso):
    return iso[11:16]


def words(n):
    return {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, str(n))


# ---------------------------------------------------------------- numbers the prose rests on

CN1, CN2 = VC["clock_needed"]["R1"], VC["clock_needed"]["R2"]
NV1, NV2 = VC["never"]["R1"], VC["never"]["R2"]
DS1, DS2 = VC["date_settles"]["R1"], VC["date_settles"]["R2"]
AL1, AL2 = VC["all"]["R1"], VC["all"]["R2"]
GA1 = CR["a read at the question settles | R1"]
GA2 = CR["a read at the question settles | R2"]
GF1 = CR["F1 (own session) | R1"]
GF2 = CR["F1 (own session) | R2"]
GD1 = CR["date alone settles | R1"]
GN1 = CR["a read cannot settle (note has no time) | R1"]
SEEN1, SEEN2 = A["by_arm_seen"]["R1"], A["by_arm_seen"]["R2"]
CTX1 = A["by_arm_context"]["R1"]
D = A["delivery"]
CALLS = A["calls"]

assert sorted(VC["clock_needed"]["pairs"]) == sorted(["F1-early", "F1-late", "F2-N1-early", "F2-N1-late",
                                                      "F3-N1-early", "F3-N1-late"]), VC["clock_needed"]["pairs"]
assert VC["date_settles"]["pairs"] == ["F4-N1-late"] and A["pairs_with_one_arm"] == ["F4-N1-early"]
assert CN1["n"] == CN2["n"] and NV1["n"] == NV2["n"] and AL1["n"] == AL2["n"]
# "With the hook more right, no CANNOT_TELL"
assert CN2["right"] > CN1["right"] and CN2["cannot_tell"] == 0 < CN1["cannot_tell"]
# "18 of the 20 right came from the model's own `date`; the other 2 were lucky"
assert CN1["right"] == CN1["right_grounded"] + CN1["right_lucky"]
assert CN1["right_grounded"] == GA1["clock_read"] == GA1["read_then"]["right"] == GA1["read_then"]["n"]
assert CN2["right_lucky"] == 0 and CN2["right"] == CN2["right_grounded"]
# "notes with no time: nothing changed; 0 right in either arm"
assert NV1["right"] == NV2["right"] == 0 and NV1["wrong"] <= 1 and NV2["wrong"] <= 1
# "the hook arm had more wrong answers"
assert AL2["wrong"] > AL1["wrong"]
WRONG = A["wrong_vs_world"]
WRONG_MODELS = sorted({w[0] for w in WRONG})
assert WRONG_MODELS == ["haiku"], WRONG_MODELS
assert len(WRONG) == AL1["wrong"] + AL2["wrong"]  # F4-N1-early (R2 only) has no wrong answer
CLEAN = [m for m in MODELS if m not in WRONG_MODELS]
# unfounded decisions, by model
UNF = [w for w in A["wrong_or_unfounded"] if w[4].startswith("unfounded")]
assert sorted({w[0] for w in UNF}) == ["haiku"]
assert len(UNF) == SEEN1["unfounded"] + SEEN2["unfounded"]
# every option chosen without grounds, and every wrong answer, was the family's first ("early") option
EARLY = {fam: opts[0] for fam, opts in S.OPTIONS.items() if opts}
for w in A["wrong_or_unfounded"] + [[x[0], x[1], x[2], x[3], "wrong"] for x in WRONG]:
    assert w[3] == EARLY[w[1][:2]], w
# reading the clock by command
assert CRT["R2"]["clock_read"] == 0 and CRT["R2"]["date_tried"] == 0
assert GD1["clock_read"] == 0 and GN1["clock_read"] == 0 and GD1["date_tried"] == 0 and GN1["date_tried"] == 0
NOHELP_N = GD1["n"] + GN1["n"]
assert GA1["no_read_then"]["right"] == 0 and GA1["no_read_then"]["wrong"] == 0  # no read -> all abstained
assert GF1["clock_read"] == 0 and GF1["date_tried"] == GF1["date_refused"] == len(A["other_command_rows"])
assert CRT["R1"]["clock_read"] == GA1["clock_read"] == A["settled_by_own_read"]
CREATE_READS = sum(1 for r in CROWS if r.get("kind") == "decision" and r["family"] == "F1" and r["R"] == "R1"
                   and ((r.get("create") or {}).get("date_reads") or (r.get("create") or {}).get("tool_uses")))
assert CREATE_READS == 0  # no command at all in the first call of a hook-off F1 session
GA_BY_MODEL = GA1["by_model"]
# F1
F1R1 = pair_sum(["F1-early", "F1-late"], "R1")
F1R2 = pair_sum(["F1-early", "F1-late"], "R2")
F1R1_OPTS = [OPTS["F1 R1 early"], OPTS["F1 R1 late"]]
assert F1R1_OPTS[0][1] == F1R1_OPTS[1][1] == 0  # no SAFE_NOW without the hook
F1R1_EARLYOPT = F1R1_OPTS[0][0] + F1R1_OPTS[1][0]
F1R1_CT = F1R1_OPTS[0][2] + F1R1_OPTS[1][2]
F1_WRONG_R2 = [w for w in WRONG if w[1] == "F1-R2-late"]
assert len(F1_WRONG_R2) == F1R2["wrong"] and F1R2["cannot_tell"] == 0
assert OPTS["F1 R2 early"][0] == OPTS["F1 R2 early"][4]  # all NOT_YET early with the hook
# settled and unsettled
assert SEEN1["correct"] == SEEN1["settled_n"] and SEEN1["wrong"] == 0
assert SEEN2["wrong"] == len(F1_WRONG_R2)
assert SEEN1["cannot_tell_when_settled"] == SEEN2["cannot_tell_when_settled"] == 0
# N1 and N0 hand-over pairs
N1_NAMES = ["F2-N1-early", "F2-N1-late", "F3-N1-early", "F3-N1-late", "F4-N1-early", "F4-N1-late"]
N0_NAMES = ["F2-N0-early", "F2-N0-late", "F3-N0-early", "F3-N0-late", "F4-N0-early", "F4-N0-late"]
N1R1, N1R2 = pair_sum(N1_NAMES, "R1"), pair_sum(N1_NAMES, "R2")
N0R1, N0R2 = pair_sum(N0_NAMES, "R1"), pair_sum(N0_NAMES, "R2")
assert N1R2["right"] == N1R2["n"] and N1R1["wrong"] == 0
assert N0R1["right"] == N0R2["right"] == 0
N1R1_RUN = pair_sum([p for p in N1_NAMES if "R1" in PAIRS[p]], "R1")
assert N1R1_RUN["right"] == GA1["read_then"]["right"] + DS1["right"]
F3N1R1 = pair_sum(["F3-N1-early", "F3-N1-late"], "R1")
F3N1R2 = pair_sum(["F3-N1-early", "F3-N1-late"], "R2")
F2N1R1 = pair_sum(["F2-N1-early", "F2-N1-late"], "R1")
F2N1R2 = pair_sum(["F2-N1-early", "F2-N1-late"], "R2")
assert F3N1R2["right"] == F3N1R2["n"] and F3N1R1["wrong"] == 0 and F3N1R1["right"] < F3N1R2["right"]
# delivery
assert D["r2_with_clock_line"] == D["r2_n"] and D["r1_with_clock_line"] == 0
assert D["f1_late_r2_gap_sentence"] == D["f1_late_r2_n"] and D["f1_early_r2_gap_sentence"] == 0
assert D["f1_resumed_same_session"] == D["f1_n"]
assert CALLS["failed_rows"] == 0 and A["format"]["one_decision_line_first"] == A["format"]["replies"]
assert A["format"]["unparsed"] == 0 and A["format"]["hand_check"] == 0
assert HR["decisions_read_differently_from_parser"] == 0
# F6
F6N, F6H = F6["none"], F6["hook"]
assert F6H["numeric"] > F6N["numeric"]
assert F6N["numeric"] == F6N["numeric_by_method"].get("date before and after", 0)
F6H_CLOCK = F6H["numeric_by_method"].get("clock lines available", 0)
F6H_DATE = F6H["numeric_by_method"].get("date before and after", 0)
assert F6H_CLOCK + F6H_DATE == F6H["numeric"]
assert F6H["numeric_inside_clock_bounds"] == F6H["numeric_with_clock_bounds"] == F6H["numeric"]
assert F6N["date_before_and_after"] == F6N["numeric"]
F6N_MODELS = [m for m, v in F6N["by_model"].items() if v["numeric"]]
assert F6N_MODELS == ["fable"]
F6H_CT_MODELS = [r["model"] for r in J["claude"]["f6"] if r["R"] == "hook" and r["estimate"] == "CANNOT_TELL"]
assert F6H["abs_error_range_date_before_and_after"] == [0, 0]
assert F6N["abs_error_range_date_before_and_after"] == [F6N["abs_error_min_s"], F6N["abs_error_max_s"]]
assert "Bash(time:*)" in RC.F6_DENIED
F6_DATE_USERS = Counter((r["model"], r["R"]) for r in J["claude"]["f6"] if r["method"] == "date before and after")
F6_DATE_TEXT = ", ".join("%s %s with the hook %s" % (m, {1: "once", 2: "twice"}.get(k, "%d times" % k),
                                                    "on" if R == "hook" else "off")
                         for (m, R), k in F6_DATE_USERS.items())
F6_DATE_N = sum(F6_DATE_USERS.values())
assert F6_DATE_N == F6N["date_before_and_after"] + F6H["date_before_and_after"]
F6_TRUE_MIN = min(F6N["true_s_min"], F6H["true_s_min"])
F6_TRUE_MAX = max(F6N["true_s_max"], F6H["true_s_max"])
assert RC.F6_RANGE_S_SPEC[1] < RC.F6_RANGE_S[0]  # the range was moved up, not widened
assert RC.F6_RANGE_S[0] <= F6_TRUE_MIN and F6_TRUE_MAX <= RC.F6_RANGE_S[1]
F6_PER_MODEL = {v["n"] for arm in (F6N, F6H) for v in arm["by_model"].values()}
assert len(F6_PER_MODEL) == 1 and F6N["n"] == F6H["n"]  # the same number of rows per model and arm
# router
assert RT["decision_rows_ok"] == 0 and RT["failed_calls"] == RT["calls"] and list(RT["failed_http_status"]) == ["402"]
assert RT["cost_counted_usd"] == 0
ROUTER_MODELS = list(RCTX["models"])
ROUTER_PLANNED = len(S.router_cells()) * 3 * len(ROUTER_MODELS) + len(ROUTER_MODELS)
ROUTER_CALLED = sorted({r["model"] for r in J["router_canary"]})
_price = {m: v["pricing"]["input"] + v["pricing"]["output"] for m, v in RCTX["models"].items()}
assert ROUTER_CALLED == [min(_price, key=_price.get)]  # "the cheapest model"
_rtimes = sorted(r["call_time_utc"] for r in RROWS)
ROUTER_GAP_MIN = round((dt.datetime.strptime(_rtimes[-1], "%Y-%m-%dT%H:%M:%SZ")
                        - dt.datetime.strptime(_rtimes[0], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 60)
ROUTER_FIRST = _rtimes[0]
# Why the router arm did not run: the account's pre-paid credit ran out during the group experiment in
# experiments/consensus/ (the first HTTP 402 answer in its groups.jsonl), before this arm's first call.
CREDIT_OUT_UTC = "2026-11-23T13:38:21Z"


def first_402_utc(path):
    """Earliest call_time_utc of a call answered with HTTP 402, anywhere in a JSON-lines file."""
    times = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("http_status") == 402 and o.get("call_time_utc"):
                times.append(o["call_time_utc"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for r in common.load_rows(path)[0]:
        walk(r)
    return min(times) if times else None


_cons = os.path.join(HERE, "..", "consensus", "groups.jsonl")
if os.path.exists(_cons):  # read only: that folder belongs to another experiment
    assert first_402_utc(_cons) == CREDIT_OUT_UTC, first_402_utc(_cons)
assert CREDIT_OUT_UTC[:10] == ROUTER_FIRST[:10] and CREDIT_OUT_UTC < ROUTER_FIRST  # same day, before
assert RT["calls"] == 2 and all(r.get("http_status") == 402 for r in RROWS)  # "both calls got HTTP 402"
assert RT["cost_counted_usd"] == 0 and RT["cost_router_usd"] == 0  # "and cost nothing"
# One entry of the price table names another model than the one it prices.
PRICED_AS_OTHER = [(m, v["priced_as"]) for m, v in RCTX["models"].items() if v.get("priced_as", m) != m]
assert len(PRICED_AS_OTHER) == 1 and PRICED_AS_OTHER[0][0] not in ROUTER_CALLED
# canaries
_can = {c["R"]: c for c in J["claude"]["canaries"]}
assert _can["R2"]["reply_quotes_clock_line"] and not _can["R1"]["reply_quotes_clock_line"]
assert J["claude"]["resume_canaries"] and all(c["carried"] for c in J["claude"]["resume_canaries"])
_echo = [(u, x) for r in CROWS if r.get("kind") == "canary_clock" for u, x in zip(r["tool_uses"], r["tool_results"])
         if (u.get("input") or {}).get("command", "").startswith("echo")]
assert _echo and all(not x.get("is_error") for _, x in _echo)  # "`echo` ran in the canary"
# hand-read groups the prose relies on
_groups = [n.get("group") for n in HR["notes"] if n["kind"] == "decision"]
assert _groups.count("read_would_not_help") >= 1
NO_READ_NOTES = [n for n in HR["notes"] if n.get("group") == "no_read_when_it_would_settle"]
# the wrong answers with the hook on: two F1 late rows and one F4 row without a Written line
assert sorted(w[1] for w in WRONG if "-R2-" in w[1]) == ["F1-R2-late", "F1-R2-late", "F4-R2-N0-late"]
# replies in never-settled hook-on cells that quote the clock line's time
_never_r2 = [r for r in CROWS if r.get("kind") == "decision" and r["R"] == "R2" and r.get("N") == "N0"]
NEVER_R2_QUOTE = sum(1 for r in _never_r2 if r["clock_lines_seen"]
                     and re.search(r"Clock: .*?, (\d{2}:\d{2}) ", r["clock_lines_seen"][-1]).group(1) in (r["reply"] or ""))
assert len(_never_r2) == NV2["n"]
# ... of those, all but one answered CANNOT_TELL; the other is haiku's F4 row that placed "tomorrow"
# from the clock line's date and answered wrong (hand note, group "unfounded")
assert A["format"]["stored_parse_differs"] == 0  # the stored decisions are the parser's
_quote_rows = [r for r in _never_r2 if r["clock_lines_seen"]
               and re.search(r"Clock: .*?, (\d{2}:\d{2}) ", r["clock_lines_seen"][-1]).group(1) in (r["reply"] or "")]
NEVER_R2_QUOTE_CT = sum(1 for r in _quote_rows if r["decision"] == S.CANNOT)
_quote_other = [(r["model"], r["cell"], r["variant"]) for r in _quote_rows if r["decision"] != S.CANNOT]
assert len(_quote_rows) == NEVER_R2_QUOTE and _quote_other == [("haiku", "F4-R2-N0-late", 3)], _quote_other
assert [w[:3] for w in WRONG if w[1] == "F4-R2-N0-late"] == [["haiku", "F4-R2-N0-late", 3]]
assert any(n.get("cell") == "F4-R2-N0-late" and n.get("variant") == 3 and "tomorrow" in n["note"]
           for n in HR["notes"])
QUOTE_OTHER_TEXT = "%s, %s, variant %d" % _quote_other[0]
# replies that said a clock read would not help (hand notes)
RWNH = [n for n in HR["notes"] if n.get("group") == "read_would_not_help"]
assert len(RWNH) == 2 and all(n["cell"].startswith("F2-R1-N0") for n in RWNH)
# notes with no time: CANNOT_TELL in both arms together
N0_CT, N0_N = NV1["cannot_tell"] + NV2["cannot_tell"], NV1["n"] + NV2["n"]
assert NV1["right"] + NV2["right"] == 0 and N0_N - N0_CT == NV1["wrong"] + NV2["wrong"] == 1
assert NV2["wrong"] == 1 and NV1["wrong"] == 0
# clock commands with the hook off: tried, ran, refused; the refused ones are the F1 transcript reads
TRANSCRIPT_NOTES = [n for n in HR["notes"] if n.get("group") == "transcript_attempt"]
assert CRT["R1"]["date_refused"] == GF1["date_refused"] == len(TRANSCRIPT_NOTES)
assert CRT["R1"]["date_tried"] == CRT["R1"]["clock_read"] + CRT["R1"]["date_refused"]
assert CRT["R1"]["time_in_output"] == 0  # every clock read was `date`
# F6 with the hook on: one row ran `date`; Python clock reads were tried and refused
assert F6H["date_ran_models"] == ["haiku"] and F6H["python_clock_ran"] == 0
F6H_PY_MODELS = sorted(F6H["python_clock_tried_models"], key=lambda m: MODELS.index(m))
assert F6H_PY_MODELS == ["haiku", "fable"]
# the early and late hook-off prompts of one wording are the same text in N0 and F1 cells, not with a Written line
_texts = {}
for r in CROWS:
    if r.get("kind") == "decision" and r["R"] == "R1":
        _texts.setdefault((r["family"], r.get("N"), r["variant"], r["timing"]), set()).add(
            (r.get("prompt_first") or "") + "\n" + r["prompt"])
for (fam, N, v, t), tx in _texts.items():
    other = _texts.get((fam, N, v, "late" if t == "early" else "early"))
    if other is None:
        continue
    assert (tx == other and len(tx) == 1) == (fam == "F1" or N == "N0"), (fam, N, v)
UNF_R1 = [w for w in UNF if "-R1-" in w[1]]
assert len(UNF_R1) == SEEN1["unfounded"] and all(w[1].startswith("F1-") for w in UNF_R1)
# reasons written on the DECISION line
REASON_ON_LINE = A["format"]["reason_on_decision_line"]
REASON_ON_LINE_MODELS = A["format"]["reason_on_decision_line_models"]
assert REASON_ON_LINE and len(REASON_ON_LINE_MODELS) == 1
# hand reading and the independent check
HRA = A["hand_reads"]
assert HRA["notes_first_reading"] + HRA["notes_independent_check"] == len(HR["notes"])
assert HRA["notes_independent_check"] == 1
IC = HR["independent_check"]
assert IC["labels_disagreeing"] == 0 and IC["f6_estimates_disagreeing"] == 0
CELLS_WITH_ROWS = sorted({s["cell"] for s in ROWS if s["label"] != "call_failed"})
assert HRA["checker_cells"] == CELLS_WITH_ROWS  # one at random from every cell that has rows ...
IC_EXTRA = HRA["checker_decision_rows"] - len(CELLS_WITH_ROWS)  # ... then this many more
assert IC_EXTRA > 0 and HRA["checker_f6_replies_read"] == len(J["claude"]["f6"]) == HR["f6_replies_read"]
RESCRUB = HRA["rows_rescrubbed"]
assert HRA["rows_rescrubbed_field"] == "date_reads[].output"
assert len(RESCRUB) == 3 and all(k[1].startswith("F1-R1-") for k in RESCRUB)
# per-model clock-read rates rest on few rows
GA_N = sorted(v["n"] for v in GA1["by_model"].values())


def table_window():
    """Minutes of a GMT day (24 Nov 2026) at which every F2-F4 cell matches the router table, now and 5 min
    later: run_claude's own rule (Runner.off_table, which does not use its instance)."""
    off = lambda c, t: RC.Runner.off_table(None, c["family"], c, t)  # noqa: E731
    cells = [c for c in S.claude_cells() if c["family"] != "F1"]
    t0 = dt.datetime(2026, 11, 24, tzinfo=S.UTC)
    good = []
    with S._tz(S.ROUTER_TZ):  # the runner reads the date in the zone of the machine that ran the calls
        for i in range(24 * 60):
            t = t0 + i * S.MIN
            if not any(off(c, t) or off(c, t + RC.OFF_TABLE_MARGIN) for c in cells):
                good.append(t)
    runs, start = [], None
    for i, t in enumerate(good):
        if start is None:
            start = t
        if i + 1 == len(good) or good[i + 1] - t != S.MIN:
            runs.append((start, t))
            start = None
    return runs


WINDOWS = table_window()
assert len(WINDOWS) == 1, WINDOWS
WINDOW_TEXT = "%s to %s UTC" % (WINDOWS[0][0].strftime("%H:%M"), WINDOWS[0][1].strftime("%H:%M"))
# hook
HOOK_NOW = S.hook_sha256()
assert len(CALLS["hook_sha256"]) == 1
HOOK_ROWS = CALLS["hook_sha256"][0]
# plan
MISSING_CELLS = A["plan"]["missing_cells"]
assert MISSING_CELLS == ["F4-R1-N1-early"]
# the F4 early note fell on the date of the question in this run
F4E = [r for r in CROWS if r.get("kind") == "decision" and r["cell"].startswith("F4") and r["timing"] == "early"]
assert F4E and all(r["anchor_utc"][:10] == r["call_start_utc"][:10] for r in F4E)
F4E_HOURS = sorted({r["anchor_utc"][11:16] for r in F4E})


def example(model, cell, variant):
    for r in CROWS:
        if r.get("kind") == "decision" and r["model"] == model and r["cell"] == cell and r["variant"] == variant:
            return r
    raise KeyError((model, cell, variant))


EX_F2 = example("sonnet", "F2-R2-N1-late", 1)
EX_F1 = example("sonnet", "F1-R2-late", 1)
assert EX_F2["decision"] == "TAKE_OVER" and EX_F1["decision"] == "SAFE_NOW"
EX_F1_LINES = EX_F1["create"]["clock_lines_seen"] + EX_F1["clock_lines_seen"]
EX_LINE = EX_F1["clock_lines_seen"][0]

W = A["windows_utc"]
DATE = W["F2-F4"][0][:10]
assert all(w[0][:10] == DATE == w[1][:10] for w in W.values())
assert CREDIT_OUT_UTC[:10] == DATE  # "the same day"
FIRST = min(w[0] for w in W.values())
LAST = max(w[1] for w in W.values())
N_DEC = A["format"]["replies"]
N_F6 = len(J["claude"]["f6"])
N_PER_CELL = sum(RC.VARIANTS_PER_MODEL.values())

# ---------------------------------------------------------------- the cell table (from scenarios.py)

FAM_NAME = {"F1": "F1 wait (own session)", "F2": "F2 lease (hand-over)", "F3": "F3 window (agreement by silence)",
            "F4": "F4 relative day (hand-over)", "F5": "F5 stale date (router only)"}


def entry(cell):
    det, ans, world, _ = S.EXPECTED[cell]
    if det == "yes":
        return "**%s**" % ans
    if det == "stale":
        return "stale (12 at its word)"
    return "not settled"


def claude_n(cell):
    return sum(1 for s in ROWS if s["cell"] == cell and s["label"] != "call_failed")


CELLS = S.router_cells()
SETTLED_ROUTER = [c["cell"] for c in CELLS if S.EXPECTED[c["cell"]][0] == "yes"]
cell_rows = []
for fam in ("F1", "F2", "F3", "F4"):
    for N in ((None,) if fam == "F1" else ("N0", "N1")):
        for timing in ("early", "late"):
            ids = {R: S.cell_id(fam, R, N, timing) for R in ("R0", "R1", "R2")}
            world = S.EXPECTED[ids["R0"]][2]
            assert all(S.EXPECTED[i][2] == world for i in ids.values())
            cell_rows.append("| %s | %s | %s | %s | %s | %s | %s | %d / %d |" % (
                FAM_NAME[fam], {"N0": "N0 relative", "N1": "N1 Written line", None: "-"}[N], timing, world,
                entry(ids["R0"]), entry(ids["R1"]), entry(ids["R2"]), claude_n(ids["R1"]), claude_n(ids["R2"])))
F5_ROWS = ["| %s | %s | %s | %s |" % (c["cell"], entry(c["cell"]), S.EXPECTED[c["cell"]][2], S.EXPECTED[c["cell"]][3])
           for c in CELLS if c["family"] == "F5"]
APPENDIX = ["| %s | %s | %s | %s | %s |" % (c["cell"], S.EXPECTED[c["cell"]][0], S.EXPECTED[c["cell"]][1] or "-",
                                            S.EXPECTED[c["cell"]][2], S.EXPECTED[c["cell"]][3].replace("|", "/"))
            for c in CELLS]
problems = S.check_table(S.ROUTER_BASE_DATE)
assert not problems, problems

F1V = S.VARIANTS["F1"]
DEL = S.DELTAS


def hours(td):
    return int(td.total_seconds() // 3600)


# ---------------------------------------------------------------- per-model table

model_rows = []
for m in MODELS:
    s1, s2 = A["by_model_arm_seen"][m]["R1"], A["by_model_arm_seen"][m]["R2"]
    a1, a2 = VC["all"]["R1"]["by_model"][m], VC["all"]["R2"]["by_model"][m]
    c1, c2 = VC["clock_needed"]["R1"]["by_model"][m], VC["clock_needed"]["R2"]["by_model"][m]
    g = GA_BY_MODEL.get(m, {"n": 0, "clock_read": 0})
    model_rows.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        m, kofn(s1["correct"], s1["settled_n"]), kofn(s2["correct"], s2["settled_n"]),
        kofn(s1["unfounded"], s1["unsettled_n"]), kofn(s2["unfounded"], s2["unsettled_n"]),
        rcw_short(c1), rcw_short(c2), rcw_short(a1), rcw_short(a2), kofn(g["clock_read"], g["n"])))

pair_rows = []
for p, v in PAIRS.items():
    cl = A["pair_class"][p]
    pair_rows.append("| %s | %s | %s | %s |" % (p, {"clock_needed": "clock line needed", "date_settles":
                                                     "date alone settles", "never": "never settled"}[cl],
                                                 rcw_short(v["R1"]) if "R1" in v else "not run",
                                                 rcw_short(v["R2"]) if "R2" in v else "not run"))

opt_rows = []
for k, v in OPTS.items():
    fam = k.split()[0]
    a, b = S.OPTIONS[fam]
    opt_rows.append("| %s | %d (%s) | %d (%s) | %d | %d |" % (k, v[0], a, v[1], b, v[2], v[4]))

hand_notes = []
for n in HR["notes"]:
    if n["kind"] == "decision":
        hand_notes.append("- %s, %s, variant %d (%s%s): %s" % (
            n["model"], n["cell"], n["variant"], n["read_as"],
            ", added by the checker" if n.get("source") == "independent check" else "", n["note"]))
f6_notes = []
for n in HR["notes"]:
    if n["kind"] == "f6":
        f6_notes.append("- %s, %s, true %d s (%s): %s" % (n["model"], "hook on" if n["R"] == "hook" else "hook off",
                                                         n["sleep_true_s"], n["read_as"], n["note"]))
f6_rows = []
for r in J["claude"]["f6"]:
    f6_rows.append("| %s | %s | %d | %s | %s | %s |" % (
        r["model"], "on" if r["R"] == "hook" else "off", r["sleep_true_s"], r["estimate"], r["method"],
        "%d to %d" % tuple(r["clock_bounds_s"]) if r["clock_bounds_s"] else "-"))

cost_rows = ["| %s | %s | %d | %d | %.4f |" % (m, ", ".join(v["model_ids"]), v["calls"], v["rows"], v["cost_usd"])
             for m, v in CALLS["by_model"].items()]

# ---------------------------------------------------------------- the README

L = []
add = L.append
add("# Does a clock line help an agent use time?")
add("")
add("This folder holds one experiment. It asks whether an agent makes better decisions that depend on elapsed "
    "time when each prompt carries a clock line, and whether it notices when the time it needs is missing.")
add("")
add("The clock line is the text that `hooks/clock-line.py`, a Claude Code hook in this project, adds to each "
    "prompt: weekday, date, time of day and zone, and, after 10 minutes or more of silence, how long the "
    "silence was. One that a model received in this run:")
add("")
add("```")
add(EX_LINE)
add("```")
add("")
add("**What ran.** Only the Claude Code arm: four Claude models (%s), %d decision rows and %d duration rows, on "
    "%s between %s and %s UTC. The other arm, open models through Hugging Face Inference Providers, did not run. "
    "The account's pre-paid credit ran out at %s UTC the same day, during the group experiment in "
    "`experiments/consensus/`, before this arm's first call at %s UTC; both of its calls got HTTP 402 and cost "
    "nothing. So nothing is known from this experiment about open models, about the condition with no date at "
    "all, or about the stale-date family F5. The command that runs that arm once the account has credit is under "
    "\"Limits\"." % (", ".join(MODELS), N_DEC, N_F6, DATE, hm(FIRST), hm(LAST), hm(CREDIT_OUT_UTC),
                     hm(ROUTER_FIRST)))
add("")
add("## Results in short")
add("")
add("Counts are k of n. The samples are small: %d rows per cell, 1 or 2 per model, from one afternoon on one "
    "machine. \"Hook on\" means the clock line was given; \"hook off\" means it was not, but the model could still "
    "run `date`." % N_PER_CELL)
add("")
add("- **Where the clock line settles the answer and the date alone does not** (%d rows per arm). Hook on: %s. "
    "Hook off: %s; %d of the %d right answers came from the model running `date` itself, and %d were lucky "
    "guesses." % (CN2["n"], rcw(CN2), rcw(CN1), CN1["right_grounded"], CN1["right"], CN1["right_lucky"]))
add("- **Notes with no time on them** (%d rows per arm). By design, a note without a written time cannot be "
    "placed in time, so no answer of this kind is settled, with or without the clock line. The models said so "
    "(CANNOT_TELL) in %s rows: %d with the hook off and %d with it on. The other reply, with the hook on, chose "
    "an option and was wrong." % (NV1["n"], kofn(N0_CT, N0_N), NV1["cannot_tell"], NV2["cannot_tell"]))
add("- **Reading the clock unasked.** With the hook off, the models ran `date` in %s rows where one reading would "
    "settle the answer, and in 0 of the %d rows where a reading would add nothing. With the hook on, no model ran a "
    "clock command in F1 to F4 (0 of %d)." % (kofn(GA1["clock_read"], GA1["n"]), NOHELP_N, CRT["R2"]["n"]))
add("- **Waiting inside one session** (F1). With the hook off, no reply showed that 3 minutes differ from 14: in "
    "%d rows none answered SAFE_NOW (%d CANNOT_TELL, %d NOT_YET). With it on, %s. The %s wrong were haiku answering "
    "NOT_YET after the wait had passed; one of the two worked the times out correctly and stayed cautious." % (
        F1R1["n"], F1R1_CT, F1R1_EARLYOPT, rcw(F1R2), words(F1R2["wrong"])))
add("- **Wrong answers against the world** (pairs that ran in both arms): %s with the hook on, %s with it off. "
    "All %d are haiku's; %s gave no wrong answer in either arm." % (
        kofn(AL2["wrong"], AL2["n"]), kofn(AL1["wrong"], AL1["n"]), len(WRONG),
        ", ".join(CLEAN[:-1]) + " and " + CLEAN[-1]))
add("- **How long a task took** (F6, %d rows). With clock lines before and after the task, %s replies gave a "
    "number (%d from the clock lines, off by %d to %d s; %d from `date`, exact). With the hook off, %s did (all %s, "
    "using `date` before and after, off by %d to %d s)." % (
        N_F6, kofn(F6H["numeric"], F6H["n"]), F6H_CLOCK,
        F6H["abs_error_range_clock_lines_available"][0], F6H["abs_error_range_clock_lines_available"][1],
        F6H_DATE, kofn(F6N["numeric"], F6N["n"]), F6N_MODELS[0], F6N["abs_error_min_s"], F6N["abs_error_max_s"]))
add("- **Notes with a written time** (F2 to F4 with a Written line). With the clock line, every row was right "
    "(%s). With the hook off, %s; %d of the right answers came from the model's own `date`. See \"Hand-overs "
    "between agents\"." % (kofn(N1R2["right"], N1R2["n"]), rcw(N1R1_RUN), GA1["read_then"]["right"]))
add("")

add("## Words used here")
add("")
add("- **Clock line**: the line the hook adds to each prompt (example above).")
add("- **Hook on / hook off**: the two conditions of the Claude Code arm. They are called R2 and R1 in the code "
    "and the data. Claude Code always tells the model today's date, so hook off still gives the date. One tool "
    "was allowed in both: running `date`.")
add("- **Note**: a journal entry written by another agent (families F2 to F4). **N0**: the note uses relative "
    "words only (\"I have just claimed\", \"starts tomorrow\"). **N1**: the same note with a first line "
    "\"Written: YYYY-MM-DD HH:MM UTC\".")
add("- **Early / late**: each scenario is asked twice, once when the first option is right (early) and once "
    "when the second is right (late).")
add("- **Settled**: the information the model has fixes the right option. Worked out per cell (and per row in "
    "this arm), before looking at replies. \"Has\" includes a time the model read itself with `date`.")
add("- **World answer**: the option that is right given the true times, whether or not the model could know them.")
add("- **Right / wrong against the world**: the option chosen is, or is not, the world answer. CANNOT_TELL is "
    "counted apart.")
add("- **Unfounded decision**: an option chosen in a cell that is not settled, instead of CANNOT_TELL. "
    "**Lucky** if it happens to be the world answer, **unlucky** if not. A right answer in a settled cell is "
    "**right with grounds**.")
add("- **Matched pair**: the hook-off and hook-on rows of one scenario (same family, note form and timing), "
    "with the same wordings for each model. Pairs fall into three **classes**: the clock line is needed (settled "
    "with it, not by the date alone), the date alone settles it, or never settled (the note carries no time).")
add("- **Clock read**: a command that ran and printed the time (`date`, in practice). **Tried**: any command "
    "that runs `date`, whether it ran or was refused.")
add("")

add("## The question")
add("")
add("When the right action depends on how much time has passed, does giving the agent the current time, and "
    "giving notes an absolute timestamp, change what it does? And when the needed time is missing, does the "
    "agent say so (CANNOT_TELL), or does it guess?")
add("")
add("## The design in plain words")
add("")
add("Every prompt describes a situation, offers two options and CANNOT_TELL, and asks for one line "
    "`DECISION: <option>` and one sentence of reason. CANNOT_TELL is always allowed, and the prompt says it means "
    "\"the information you have does not settle the question\".")
add("")
add("Families (each has a threshold; three wordings each, with different names, durations and times):")
add("")
add("- **F1 wait** (own session). The person says a change went in just now and needs a fixed wait before the "
    "next step; the state cannot be checked. Later the person asks whether the next step is safe. NOT_YET / "
    "SAFE_NOW. In the Claude Code arm the wait is %d minutes and the session is resumed for real after about %d "
    "(early) or about %d minutes (late)." % (S.CLAUDE_F1_WAIT_MIN, S.CLAUDE_F1_RESUME_MIN["early"],
                                             S.CLAUDE_F1_RESUME_MIN["late"]))
add("- **F2 lease** (hand-over). Another agent's journal entry: it claimed a task with a %d-hour lease; take "
    "over only after the lease expires. WAIT / TAKE_OVER. Asked %d h (early) or %d h (late) after the claim." % (
        hours(S.LEASE), hours(DEL["F2"]["early"]), hours(DEL["F2"]["late"])))
add("- **F3 window** (agreement by silence). A proposal passes if nobody objects within %d hours; no objection is "
    "recorded. WAIT / APPLY. Asked %d h or %d h after it was opened." % (
        hours(S.WINDOW), hours(DEL["F3"]["early"]), hours(DEL["F3"]["late"])))
add("- **F4 relative day** (hand-over). A note says a freeze \"starts tomorrow at 09:00 UTC\" and runs seven "
    "days. Is it in force? NOT_YET / IN_FORCE. Asked %d h or %d h after the note." % (
        hours(DEL["F4"]["early"]), hours(DEL["F4"]["late"])))
add("- **F5 stale date** (router arm only). The conversation began with \"Today's date is D0\"; nine days later the "
    "person asks how many days are left to a deadline at D0 + 12. Not run.")
add("- **F6 duration** (Claude Code arm only, optional). The model runs a script that sleeps for a hidden %d to "
    "%d seconds and says how long it took. The spec asked for %d to %d seconds; a design check before the full "
    "run changed it, because the clock line shows whole minutes, so an estimate from two clock lines can be off "
    "by up to a minute, which is most of such a short task." % (RC.F6_RANGE_S + RC.F6_RANGE_S_SPEC))
add("")
add("Two arms were planned:")
add("")
add("- **Router arm**: %d open models through Hugging Face Inference Providers, with the whole context written by "
    "the script, so it has three time conditions: R0 nothing, R1 the date only, R2 the date and a clock line made "
    "by the hook's own code; %d cells, 3 wordings, %d calls planned. Not run (see \"What ran\")." % (
        len(ROUTER_MODELS), len(CELLS), ROUTER_PLANNED))
add("- **Claude Code arm**: the real harness (Claude Code %s, `claude -p`), the real hook passed with "
    "`--settings`, and real waiting. No user settings, no MCP servers, an empty working folder outside the "
    "project. Hook off and hook on differ only in the `--settings` value. One tool was allowed, `%s`, and "
    "commands that print a time (%s) were denied in both conditions. F2 to F4 ran as one fresh session per row, "
    "with note times computed from the real time of the call. F1 created each session, waited, and resumed it "
    "with `--resume`. Each cell got %d rows: %s, with the same wordings in the hook-off and hook-on rows of a "
    "pair." % (CALLS["claude_versions"][0].split()[0], RC.DATE_TOOL,
               ", ".join("`%s`" % t[len("Bash("):-len(":*)")] for t in RC.DENIED_TOOLS), N_PER_CELL,
               ", ".join("%d %s for %s" % (k, "wording" if k == 1 else "wordings", m)
                         for m, k in RC.VARIANTS_PER_MODEL.items())))
add("")
add("An F2 prompt with a Written line (N1), as sent at %s UTC; with the hook on, the model also received `%s`:" % (
    hm(EX_F2["call_start_utc"]), EX_F2["clock_lines_seen"][0]))
add("")
add("```")
add(EX_F2["prompt"])
add("```")
add("")
add("An F1 session with the hook on. First call: \"%s\" Second call, %.0f s later: \"%s\" plus the same reply "
    "instruction. Clock lines received: `%s`, then `%s`." % (
        EX_F1["prompt_first"], EX_F1["resume_delay_s"], EX_F1["prompt"].split("\n")[0], EX_F1_LINES[0],
        EX_F1_LINES[1]))
add("")

add("## The cell table")
add("")
add("Which cells are settled, worked out by hand for the router arm and checked against a mechanical reading "
    "(interval arithmetic in `scenarios.settle`, `check_table()`: 0 disagreements over %d cells and 3 wordings). "
    "A bold option means the cell is settled and that option is right. %d of %d router cells are settled. The "
    "Claude Code arm uses the R1 (hook off) and R2 (hook on) columns; its last column gives the rows it has." % (
        len(CELLS), len(SETTLED_ROUTER), len(CELLS)))
add("")
add("| family | note | timing | world answer | R0 nothing | R1 date | R2 date + clock line | Claude Code rows "
    "(hook off / on) |")
add("|---|---|---|---|---|---|---|---|")
L += cell_rows
add("")
add("| F5 cell | settled | world answer | reason |")
add("|---|---|---|---|")
L += F5_ROWS
add("")
add("Three things differ in the Claude Code arm, and each row is scored with its own reading:")
add("")
add("- Hook off is not the router's R1. The model could run `date`. A row where it did, and the reading settles "
    "the cell, is scored as settled. This is why F2 and F3 with a Written line can be settled with the hook off.")
add("- Note times are computed from the time of the call, so what a cell means depends on the hour. The F2 to F4 "
    "rows ran at %s to %s UTC. At that hour the F4 early note was written on the same date as the question (at "
    "%s UTC), so \"tomorrow at 09:00\" is the next day and the date alone settles NOT_YET. In the router design it "
    "does not. The runner therefore skipped the hook-off rows of F4-N1-early (all %d), and the hook-on rows of that "
    "pair say nothing about the clock line." % (hm(W["F2-F4"][0]), hm(W["F2-F4"][1]),
                                                " to ".join([F4E_HOURS[0], F4E_HOURS[-1]]), N_PER_CELL))
add("- F1 with the hook off: a single `date` at the question does not settle it, because nothing places the "
    "person's \"just now\" in time. Only a reading taken already in the first call would.")
add("")

add("## Results")
add("")
add("All numbers below are computed by `score.py` from the rows and written to `summary.md` and `summary.json`; "
    "this file is written from `summary.json` by `make_readme.py`.")
add("")
add("### Router arm")
add("")
add("Not run (see \"What ran\" above). The runner sent one date-canary call to the cheapest model (%s) at %s UTC, "
    "and the same call again %d minutes later; both were refused (HTTP 402), and the runner stopped. Calls %d, "
    "failed %d, "
    "decision rows %d, spend USD %.2f (cap USD %.2f). The other %d models were not called. The planned models: "
    "%s." % (", ".join(ROUTER_CALLED), hm(ROUTER_FIRST), ROUTER_GAP_MIN, RT["calls"], RT["failed_calls"],
             RT["decision_rows"], RT["cost_counted_usd"], RR.CAP_USD, len(ROUTER_MODELS) - len(ROUTER_CALLED),
             ", ".join("`%s`" % m for m in ROUTER_MODELS)))
add("")
add("One entry of the arm's price table names another model than the one it prices: `%s` is priced as `%s` "
    "(`priced_as` in `run_context_router.json`). That model was never called, so nothing here depends on it." %
    PRICED_AS_OTHER[0])
add("")
add("An earlier smoke test of this arm (24 replies from two models, an older design) is kept in `smoke/` and "
    "is not a result.")
add("")

add("### Claude Code arm: did the set-up work?")
add("")
add("- Calls %d, rows %d (%s), failed calls %d. Rows planned %d; missing %d, all in %s (see above). "
    "`python3 -I -B run_claude.py --scratch DIR --cells %s` fills them when run from %s, the hours when every F2 "
    "to F4 cell matches the router table." % (
        CALLS["total_calls"], CALLS["total_rows"],
        ", ".join("%s %d" % kv for kv in sorted(CALLS["rows_by_kind"].items())), CALLS["failed_rows"],
        A["plan"]["planned"], len(A["plan"]["missing"]), ", ".join(MISSING_CELLS), ",".join(MISSING_CELLS),
        WINDOW_TEXT))
add("- The clock line reached the model in %s hook-on rows and in %s hook-off rows. A canary with the hook on "
    "quoted the line; one with the hook off said there was none." % (
        kofn(D["r2_with_clock_line"], D["r2_n"]), kofn(D["r1_with_clock_line"], D["r1_n"])))
add("- F1: %s resumes reported the same session as their first call, and a canary confirmed that a resumed "
    "session carries the first turn. Resumes came %.0f to %.0f s (early) and %.0f to %.0f s (late) after the first "
    "call. The gap sentence appeared in %s late hook-on resumes and in %s early ones, as the hook's 10-minute "
    "rule says." % (kofn(D["f1_resumed_same_session"], D["f1_n"]), D["resume_delay_s"]["early"][0],
                    D["resume_delay_s"]["early"][1], D["resume_delay_s"]["late"][0], D["resume_delay_s"]["late"][1],
                    kofn(D["f1_late_r2_gap_sentence"], D["f1_late_r2_n"]),
                    kofn(D["f1_early_r2_gap_sentence"], D["f1_early_r2_n"])))
add("- Replies: %s have exactly one DECISION line, and it is the first line; none was unparsed. %d replies, all "
    "%s's, put the reason on the DECISION line itself instead of the next line; the parse is the same. How the "
    "replies were read by hand is under \"Hand reading\"." % (
        kofn(A["format"]["one_decision_line_first"], A["format"]["replies"]), REASON_ON_LINE,
        REASON_ON_LINE_MODELS[0]))
add("- The hook in every row is the file with SHA-256 `%s...`%s." % (
    HOOK_ROWS[:16], ", the same as `hooks/clock-line.py` now" if HOOK_ROWS == HOOK_NOW
    else "; `hooks/clock-line.py` has changed since"))
add("")

add("### Settled and unsettled cells")
add("")
add("Pooled over models, each row scored with what the model saw (its prompt, the date line, the clock lines and "
    "any clock it read itself):")
add("")
add("| | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded (lucky / unlucky) | "
    "unsettled: CANNOT_TELL |")
add("|---|---|---|---|---|---|")
for name, x in (("hook off", SEEN1), ("hook on", SEEN2)):
    add("| %s | %s | %s | %s | %s (%d / %d) | %s |" % (
        name, kofn(x["correct"], x["settled_n"]), kofn(x["cannot_tell_when_settled"], x["settled_n"]),
        kofn(x["wrong"], x["settled_n"]), kofn(x["unfounded"], x["unsettled_n"]), x["unfounded_lucky"],
        x["unfounded_unlucky"], kofn(x["abstained"], x["unsettled_n"])))
add("")
add("The two rows cover different cells, so they are not a comparison; the matched pairs below are. With the "
    "hook off, %d of the %d settled rows were settled only because the model ran `date`; scored on the prompt "
    "alone, those %d would count as unfounded decisions, and the hook-off row would read %s unfounded instead of "
    "%s. Every unfounded decision (%d in all) is haiku's, and in a settled cell no model ever answered "
    "CANNOT_TELL." % (A["settled_by_own_read"], SEEN1["settled_n"], A["settled_by_own_read"],
                      kofn(CTX1["unfounded"], CTX1["unsettled_n"]), kofn(SEEN1["unfounded"], SEEN1["unsettled_n"]),
                      len(UNF)))
add("")

add("### Against the world: matched pairs")
add("")
add("Right / CANNOT_TELL / wrong against the world answer, of n, pooled over models. Each pair has the same "
    "wordings with the hook off and on.")
add("")
add("| pair | class | hook off | hook on |")
add("|---|---|---|---|")
L += pair_rows
add("")
add("By class, over the pairs that ran in both arms:")
add("")
add("| class | hook off: right (with grounds / lucky) | CANNOT_TELL | wrong | hook on: right (with grounds / lucky) "
    "| CANNOT_TELL | wrong | n per arm |")
add("|---|---|---|---|---|---|---|---|")
for cl, name in (("clock_needed", "clock line needed"), ("date_settles", "date alone settles"),
                 ("never", "never settled"), ("all", "all")):
    a, b = VC[cl]["R1"], VC[cl]["R2"]
    add("| %s | %d (%d / %d) | %d | %d | %d (%d / %d) | %d | %d | %d |" % (
        name, a["right"], a["right_grounded"], a["right_lucky"], a["cannot_tell"], a["wrong"], b["right"],
        b["right_grounded"], b["right_lucky"], b["cannot_tell"], b["wrong"], a["n"]))
add("")

add("### Per model")
add("")
add("Settled and unsettled use each row's own reading; the pair columns are right / CANNOT_TELL / wrong against "
    "the world. The last column is how often the model ran `date` with the hook off in the rows where one "
    "reading would settle the cell (F2 and F3 with a Written line).")
add("")
add("| model | settled correct, hook off | hook on | unfounded, hook off | hook on | clock-needed pairs, hook "
    "off | hook on | all pairs, hook off | hook on | ran `date` when it would settle |")
add("|---|---|---|---|---|---|---|---|---|---|")
L += model_rows
add("")
add("Model ids reported: %s." % "; ".join("%s = `%s`" % (m, ", ".join(v["model_ids"]))
                                          for m, v in CALLS["by_model"].items()))
add("")

add("### Options chosen, and the pull of the wording")
add("")
add("Every note and every F1 first turn is worded as if no time has passed (\"just now\", \"I have just "
    "claimed\", \"starts tomorrow\"), which points to the first option. In F1 to F3 the first option is also the "
    "cautious one; in F4 it is not. Pooled over note forms and models:")
add("")
add("| family, arm, timing | first option | second option | CANNOT_TELL | n |")
add("|---|---|---|---|---|")
L += [r.replace(" R1 ", " hook off ").replace(" R2 ", " hook on ") for r in opt_rows]
add("")
add("Every unfounded decision and every wrong answer in this run chose the first option. Without the hook, F1 "
    "never got the second option (SAFE_NOW), early or late.")
add("")

add("### What the clock line changed, and what it did not")
add("")
add("Changed:")
add("")
add("- In the pairs where it is needed, it turned CANNOT_TELL into right answers: CANNOT_TELL %d to %d, right "
    "%d to %d (of %d)." % (CN1["cannot_tell"], CN2["cannot_tell"], CN1["right"], CN2["right"], CN1["n"]))
add("- The gain was largest where `date` on request could not help: in F1 %s with the hook off, %s with it on. "
    "In F2 and F3 with a Written line the models could and mostly did read the clock themselves, so the gain "
    "was smaller: %s with the hook off, %s with it on." % (
        rcw(F1R1), rcw(F1R2), rcw(pair_sum(["F2-N1-early", "F2-N1-late", "F3-N1-early", "F3-N1-late"], "R1")),
        rcw(pair_sum(["F2-N1-early", "F2-N1-late", "F3-N1-early", "F3-N1-late"], "R2"))))
add("- With the clock line, no model ran a clock command in F1 to F4 (0 of %d), against %s with the hook off "
    "(%s tried; the %s refused were the F1 transcript reads described below)." % (
        CRT["R2"]["n"], kofn(CRT["R1"]["clock_read"], CRT["R1"]["n"]), kofn(CRT["R1"]["date_tried"], CRT["R1"]["n"]),
        words(CRT["R1"]["date_refused"])))
add("")
add("Did not change, or made worse:")
add("")
add("- A note with no time on it stayed unanswerable, as designed: no right answer in %d hook-off and %d hook-on "
    "rows, and %d and %d CANNOT_TELL. With the hook on, %s of these replies quoted the clock line's time: %d of "
    "them answered CANNOT_TELL, and 1 (%s) used the clock line's date to place \"tomorrow\" and answered "
    "wrong." % (NV1["n"], NV2["n"], NV1["cannot_tell"], NV2["cannot_tell"], kofn(NEVER_R2_QUOTE, NV2["n"]),
                NEVER_R2_QUOTE_CT, QUOTE_OTHER_TEXT))
add("- Wrong answers did not go down. Over the pairs that ran in both arms there were %s with the hook on and %s "
    "with it off, all haiku's. Two are F1 late rows where haiku saw both clock lines and still chose NOT_YET: one "
    "read \"14 minutes ago\" as an upper bound, the other computed that the wait had ended and stayed cautious. "
    "The third (F4, no Written line) placed \"tomorrow\" on the day after the clock line's date. These are %d rows "
    "from one model: they show that a clock line does not by itself make a model use the time well, not how often "
    "that happens." % (kofn(AL2["wrong"], AL2["n"]), kofn(AL1["wrong"], AL1["n"]), AL2["wrong"]))
add("- Unfounded decisions were already rare with the hook off: %s, against %s with it on." % (
    kofn(SEEN1["unfounded"], SEEN1["unsettled_n"]), kofn(SEEN2["unfounded"], SEEN2["unsettled_n"])))
add("- Where the date alone settles the answer, both arms were right in every row (%s and %s)." % (
    kofn(DS1["right"], DS1["n"]), kofn(DS2["right"], DS2["n"])))
add("")

add("### Did Claude read the clock by itself when it had no clock line?")
add("")
add("Yes, and mostly when it helped. With the hook off:")
add("")
add("- In the %d rows where one reading at the question settles the cell (F2 and F3 with a Written line), the "
    "model ran `date` in %d. All %d of those were right. The %d that did not read the clock all answered "
    "CANNOT_TELL, each saying in some form that it did not know the current time, although `date` was "
    "allowed." % (GA1["n"], GA1["clock_read"], GA1["read_then"]["n"], GA1["no_read_then"]["n"]))
assert len(NO_READ_NOTES) == GA1["no_read_then"]["n"] == GA1["no_read_then"]["cannot_tell"]
add("- By model: %s. Each rate rests on %d to %d rows, too few to rank the models." % (
    ", ".join("%s %s" % (m, kofn(v["clock_read"], v["n"])) for m, v in GA_BY_MODEL.items()), GA_N[0], GA_N[-1]))
add("- In the %d rows where a reading could not help (the note has no time, or the date already settles it), "
    "no model ran `date`. %s replies said so: knowing the current time would not show whether a lease with no "
    "start time had expired (%s)." % (NOHELP_N, words(len(RWNH)).capitalize(), "; ".join(
        "%s, %s, variant %d" % (n["model"], n["cell"], n["variant"]) for n in RWNH)))
add("- In F1 (own session) no model read the clock in the first call of the session, which is the only reading "
    "that could have settled it. In the second call %d of %d tried one command that combined `date` with `ls` "
    "and `grep` over Claude Code's own session transcript files, which hold a timestamp for every turn. The "
    "permission system refused each whole command, because `ls` is denied, and the replies said so. Those files "
    "are a clock source the design did not list." % (GF1["date_tried"], GF1["n"]))
add("- With the hook on, no model ran a clock command in F1 to F4 (0 of %d). In F6 with the hook on, %s ran `date` "
    "before and after the task in %s row, and %s tried Python clock reads, which were refused (see \"How long a "
    "task took\")." % (CRT["R2"]["n"], " and ".join(F6H["date_ran_models"]), words(len(F6H["date_ran_models"])),
                      " and ".join(F6H_PY_MODELS)))
add("")

add("### How long a task took (F6)")
add("")
add("Two rows per model and condition, %d in all. The task slept for a hidden %d to %d s. Hook on here means "
    "the hook on two events: a clock line when the prompt is sent and one after each command. `time` was denied, "
    "so the task could not be timed directly. Clock bounds: what the two clock lines allow (their minutes, plus "
    "or minus 60 s)." % (N_F6, F6_TRUE_MIN, F6_TRUE_MAX))
add("")
add("| model | hook | true s | estimate | method | clock bounds s |")
add("|---|---|---|---|---|---|")
L += f6_rows
add("")
add("- Hook off: %s gave a number, all %s, by running `date` before and after (off by %d to %d s). %s other "
    "replies said CANNOT_TELL; %d of them had first tried `time` (denied)." % (
        kofn(F6N["numeric"], F6N["n"]), F6N_MODELS[0], F6N["abs_error_min_s"], F6N["abs_error_max_s"],
        words(F6N["cannot_tell"]).capitalize(), F6N["tried_time"]))
add("- Hook on: %s gave a number, all inside the clock bounds: %d from the clock lines (off by %d to %d s) and %d "
    "from `date` (exact). The %s CANNOT_TELL (%s) had the clock lines and declined to use them because they "
    "include its own turn time; the true time was inside the bounds." % (
        kofn(F6H["numeric"], F6H["n"]), F6H_CLOCK, F6H["abs_error_range_clock_lines_available"][0],
        F6H["abs_error_range_clock_lines_available"][1], F6H_DATE, words(F6H["cannot_tell"]),
        ", ".join(F6H_CT_MODELS)))
add("- So in this run the clock line made a duration estimate common (%s against %s), at about a minute's "
    "precision. This rests on %d rows per arm, %d per model. `date` before and after was precise to a few "
    "seconds, but it was used in only %s rows (%s)." % (
        kofn(F6H["numeric"], F6H["n"]), kofn(F6N["numeric"], F6N["n"]), F6H["n"], list(F6_PER_MODEL)[0],
        kofn(F6_DATE_N, N_F6), F6_DATE_TEXT))
add("")

add("### Calls and cost")
add("")
add("| model | model id reported | calls | rows | cost USD reported by the CLI |")
add("|---|---|---|---|---|")
L += cost_rows
add("| total | | %d | %d | %.4f |" % (CALLS["total_calls"], CALLS["total_rows"], CALLS["total_cost_usd"]))
add("")
add("The cost is Claude Code's own `total_cost_usd` per call, summed over the stored rows (an F1 row stores its "
    "second call only). How it is billed on the account was not checked.")
add("")

add("## Elapsed time inside a session")
add("")
add("F1 and F6 ask about time the model lived through, not time written in a note. Reading the clock on request "
    "gives the time now; it says how long something took only if the model also read the clock at the start. "
    "In this run that rarely happened:")
add("")
add("- F1, hook off: the change was announced in the session's first call, and no model read the clock in that "
    "call (0 of %d sessions). So at the question nothing could settle the answer: %s." % (GF1["n"], rcw(F1R1)))
add("- F6, hook off: %s replies read the clock before and after the task, and they gave the only numbers." % (
    kofn(F6N["date_before_and_after"], F6N["n"])))
add("- The clock line puts a time on every turn without being asked, so the start is always on record. F1 with "
    "it: %s. F6 with it: %s replies gave a number." % (rcw(F1R2), kofn(F6H["numeric"], F6H["n"])))
add("")
add("## Hand-overs between agents")
add("")
add("F2 (a lease), F3 (a proposal that passes by silence, a simple form of agreement) and F4 (a freeze announced "
    "with \"tomorrow\") are notes one agent leaves for another. What this run shows about them:")
add("")
assert (N0R1["cannot_tell"] + N0R2["cannot_tell"], N0R1["n"] + N0R2["n"]) == (N0_CT, N0_N)
add("- Without a Written line, by design no answer is settled: a reader with a perfect clock still cannot place "
    "\"just\" or \"tomorrow\". No right answer in %d hook-off and %d hook-on rows; %d and %d CANNOT_TELL, so the "
    "models said so in %s rows." % (N0R1["n"], N0R2["n"], N0R1["cannot_tell"], N0R2["cannot_tell"],
                                    kofn(N0_CT, N0_N)))
add("- With a Written line and the clock line, every row was right: %s. With a Written line and the hook off: "
    "%s; %d of the right ones came from the model's own `date`, and %d from F4 late, where the date line settles "
    "it." % (kofn(N1R2["right"], N1R2["n"]), rcw(N1R1_RUN), GA1["read_then"]["right"], DS1["right"]))
add("- Agreement by silence (F3) with a Written line: %s with the hook on, %s with it off. Leases (F2): %s on, "
    "%s off." % (rcw(F3N1R2), rcw(F3N1R1), rcw(F2N1R2), rcw(F2N1R1)))
add("- So the clock line could only help notes that carry a written time, as designed. On those notes it made every "
    "answer right; without it the reader had to think of running `date`, and in %s rows where that would have "
    "settled the answer it did not." % kofn(GA1["no_read_then"]["n"], GA1["n"]))
add("")
add("This run took every Written line at its word. Whether such a line is true is a different question; the "
    "message stamps described in the main README address it, and they were not used here.")
add("")

add("## Hand reading")
add("")
add("The agent that wrote the summary read every reply after the run: %d decision replies and %d F6 replies. "
    "Each decision reply opens with its DECISION line, and that reading agreed with the parser on all of them "
    "(%d read differently). It kept notes on the %d replies that were unusual (`hand_reads.json`, listed below); "
    "for the other replies no record is kept, so that part of the reading cannot be checked from the files." % (
        HR["decision_replies_read"], HR["f6_replies_read"], HR["decisions_read_differently_from_parser"],
        HRA["notes_first_reading"]))
add("")
add("An independent checker later re-read %d decision rows chosen at random (one from each of the %d cells that "
    "have rows, then %d more) and all %d F6 replies, and agreed with every stored label and estimate. It added "
    "%s note, marked below. `hand_reads.json` lists the rows it read, each with its label." % (
        HRA["checker_decision_rows"], len(HRA["checker_cells"]), IC_EXTRA, HRA["checker_f6_replies_read"],
        words(HRA["notes_independent_check"])))
add("")
add("`score.py` stops if `rows_claude.jsonl` is not the file these readings describe (it checks the file's "
    "SHA-256), if a noted or checked row reads differently, or if a count no longer matches. The replies that "
    "went wrong, guessed, or did something unusual:")
add("")
L += hand_notes
add("")
add("F6:")
add("")
L += f6_notes
add("")

add("## Limits")
add("")
add("- **One arm.** The router arm did not run. The account's pre-paid credit ran out at %s UTC the same day, "
    "during the group experiment in `experiments/consensus/`, before this arm's first call at %s UTC; both calls "
    "got HTTP 402 and cost nothing. So nothing is known from this experiment about open models, about the "
    "condition with no date at all, about the stale-date family F5, or about a condition with the date but no way "
    "to read the clock: hook off here is \"date plus a clock on request\". Once the account has credit, the arm "
    "runs from this folder with `\"$PY\" -I -B run_router.py`, `PY` set as in the re-run block below; it runs "
    "every row not yet done and stops at USD %.2f." % (hm(CREDIT_OUT_UTC), hm(ROUTER_FIRST), RR.CAP_USD))
add("- **Small and narrow.** %d decision rows, %d per cell, 1 or 2 per model; %d F6 rows. One sitting (%s, %s "
    "to %s UTC), one machine, one network, Claude Code %s. Differences of one or two rows are noise." % (
        N_DEC, N_PER_CELL, N_F6, DATE, hm(FIRST), hm(LAST), CALLS["claude_versions"][0].split()[0]))
add("- **The hour matters.** F2 to F4 note times follow the time of the call. In this run the F4 early note fell "
    "on the day of the question, so F4-N1-early is settled by the date and its hook-off rows were skipped. Every "
    "F2 to F4 cell matches the router design only from %s (London winter time; computed with the runner's own "
    "rule). This run's F2 to F4 rows ran at %s to %s UTC, outside that window." % (
        WINDOW_TEXT, hm(W["F2-F4"][0]), hm(W["F2-F4"][1])))
assert not (WINDOWS[0][0].strftime("%H:%M") <= hm(W["F2-F4"][0]) <= WINDOWS[0][1].strftime("%H:%M"))
assert len(A["plan"]["missing"]) == N_PER_CELL
add("- **The wording leans one way.** Every scenario is worded as if no time has passed, and in F1 to F3 that is "
    "also the cautious option. In the N0 and F1 hook-off cells the early and late prompts of one wording are the "
    "same text, so \"lucky\" and \"unlucky\" there show a model's default, not reasoning; all %d unfounded "
    "hook-off decisions are in F1. (With a Written line the early and late prompts differ.)" % len(UNF_R1))
add("- **\"One tool\" was not enforced.** Claude Code runs commands it treats as read-only (`echo` ran in the "
    "canary). The commands that print a time were denied, and a command with a denied part is refused as a "
    "whole; that is what stopped the %s attempts to read the session transcripts. Other permissions could "
    "change the hook-off F1 numbers." % words(GF1["date_refused"]))
add("- **Frame.** The clock line arrives as hook context, which the model sees as a system note, not as part of "
    "the person's message.")
add("- **F1 scoring** assumes the person's \"just now\" was at most %d minutes before the first message." % (
    int(S.JUST_NOW_SLACK.total_seconds() // 60)))
add("- **F6 clock bounds** are rough: the first line comes when the prompt is sent, before the task starts.")
add("- **Written lines** were taken at their word.")
add("- **Context.** Claude Code put account details in the model's context even with all setting sources off "
    "(the hook-off canary reply mentions an e-mail block). No such detail is stored in the rows; they were "
    "scrubbed and checked.")
add("- **Rows edited after the run.** %s stored strings were scrubbed again after the run. They are the "
    "`%s` of %s F1 hook-off rows, each a copy of a refused command's error text; the runner had cut them short "
    "before scrubbing, so they kept the start of the scratch folder's name. They were rebuilt from the same rows' "
    "scrubbed tool results. No reply, decision or label changed. `run_claude.py` now scrubs before it cuts, and "
    "`score.py` stops if a row holds a piece of the scratch folder's name." % (
        words(len(RESCRUB)).capitalize(), HRA["rows_rescrubbed_field"], words(len(RESCRUB))))
add("- **Cost** is as the CLI reports it; billing was not checked. Model ids are as Claude Code reported them.")
add("")

add("## Files and how to re-run")
add("")
add("| File | What it is |")
add("|---|---|")
add("| `scenarios.py` | Families, wordings, timelines, the expected-answer table (`EXPECTED`), the mechanical "
    "reading (`settle`), the clock line made by the hook's own code, the reply parser. `python3 -I -B "
    "scenarios.py` checks the table. |")
add("| `run_claude.py` | Claude Code arm. |")
add("| `run_router.py` | Router arm (not run). |")
add("| `common.py` | Scrubbing and JSON-lines helpers. |")
add("| `slow_task.py` | The F6 task: sleeps for `TIME_USE_SLEEP_S` seconds, prints DONE. |")
add("| `rows_claude.jsonl` | %d rows: every call, reply, command, clock line and expected reading. |" %
    CALLS["total_rows"])
add("| `rows_router.jsonl` | %d rows, both failed calls (HTTP 402). |" % RT["calls"])
add("| `run_context_router.json` | The router arm's models, prices and base date. |")
add("| `score.py` | Re-parses every reply, labels the rows, writes `summary.md` and `summary.json`. |")
add("| `hand_reads.json` | Notes from the hand reading, the rows the independent checker re-read, and the SHA-256 "
    "of `rows_claude.jsonl` with the record of the %s re-scrubbed strings. |" % words(len(RESCRUB)))
add("| `make_readme.py` | Writes this file from `summary.json`. |")
add("| `smoke/` | Smoke-test rows from before the full run; not results. |")
add("")
add("From this folder (the working folder for Claude Code must be outside the project; its sessions are "
    "deleted with `--purge` once the rows are stored):")
add("")
add("```")
add("python3 -I -B scenarios.py                                   # table check")
add("python3 -I -B run_claude.py --scratch DIR --canary            # hook on/off and resume checks")
add("python3 -I -B run_claude.py --scratch DIR --families F1       # any hour; about 15 minutes")
add("python3 -I -B run_claude.py --scratch DIR --families F2,F3,F4 # matches the router table %s" % WINDOW_TEXT)
add("python3 -I -B run_claude.py --scratch DIR --f6                # optional; up to about 2 hours")
add("python3 -I -B run_claude.py --scratch DIR --purge")
add("PY=\"$(head -1 \"$(command -v hf)\" | sed 's/^#!//')\"")
add("\"$PY\" -I -B run_router.py                                    # needs Inference Providers credits; stops at USD 4")
add("python3 -I -B score.py")
add("python3 -I -B make_readme.py")
add("```")
add("")

add("## Appendix: the expected-answer table")
add("")
add("For the router arm's timelines (all %d cells, the same for each of the 3 wordings). \"stale\" marks F5-R1s, "
    "scored on its own: at the prompt's word the answer is 12, in the world 3." % len(CELLS))
add("")
add("| cell | settled | right option | world answer | reason |")
add("|---|---|---|---|---|")
L += APPENDIX
add("")

text = "\n".join(L) + "\n"
# Nothing private in a published file: no home or scratch path, no e-mail address, and the
# scrub rules (home path, user name, host name) change nothing.
for bad in ("/Users/", "/home/", "/private/", "/tmp/", "@"):
    assert bad not in text, bad
common.init_scrub()
assert common.scrub(text) == text
with open(OUT, "w") as f:
    f.write(text)
print("wrote", OUT)
