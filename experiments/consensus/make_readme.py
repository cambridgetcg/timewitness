"""Write README.md for the consensus experiment from summary.json and run.py.

    python3 -I make_readme.py                      # reads summary.json, writes README.md here
    python3 -I make_readme.py SUMMARY.json OUT.md  # other paths (for a check before the real write)

Every number in README.md comes from summary.json (written by score.py from
groups.jsonl) or from the texts in run.py, and the hand codes in
hand_reads.json. A sentence that states a number or a direction (more, fewer,
none, all, inside noise) has an assert on the numbers it rests on, so a rerun
with different data stops here instead of printing a false sentence. p-values
are the two-sided Fisher exact tests score.py writes (fisher_two_sided).
"""

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import run  # noqa: E402

SUMMARY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "summary.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "README.md")
with open(SUMMARY) as f:
    S = json.load(f)

BC = S["by_condition"]
with open(os.path.join(HERE, "hand_reads.json")) as f:
    HR = json.load(f)


def kofn(k, n):
    return "%d of %d" % (k, n)


def cond(c):
    return BC[c]


def role(c, r):
    return BC[c]["by_role"][r]


def fin(c, lab="CLOSED", r=None):
    a = role(c, r) if r else BC[c]["all"]
    return a["finals"][lab], a["n"]


def fdate(c, cls="true", r=None):
    a = role(c, r) if r else BC[c]["all"]
    return a["final_date"][cls], a["n"]


def grp(c, lab="CLOSED"):
    return BC[c]["group_result"][lab], BC[c]["groups"]


def K(pair):
    return kofn(*pair)


def fence(t):
    return "```\n" + t + "\n```"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


L = []
P = L.append

# ---------------------------------------------------------------- shared numbers

O = S["overall"]["all"]
NG = S["groups_scored"]
R = int(S["scored_runs"].split("-")[1])          # runs in the main set (1..R)
NM = len(S["models"])
GPC = R * NM                                       # groups per condition when nothing is missing
SHORT_CELLS = [(c, BC[c]["groups"]) for c in S["conditions"] if BC[c]["groups"] != GPC]
assert all(n == GPC - 1 for c, n in SHORT_CELLS) and len(SHORT_CELLS) <= 1, SHORT_CELLS
assert S["lines_failed_to_parse"] == 0
STOP_STATUS = dict(S["incomplete_status"])
assert set(STOP_STATUS) <= {"stopped: HTTP 402"}, STOP_STATUS
AC = S["all_complete"]
MODEL_SHORT = {m: m.split("/")[-1] for m in S["models"]}
# The later runs: complete groups of runs after the main set (summary.json groups_extra).
GX = S["groups_extra"]
assert all(g["run"] > R for g in GX) and len(GX) + NG == AC["groups"]
LATER_RUNS = (min(g["run"] for g in GX), max(g["run"] for g in GX))
LATER_BY_MODEL = collections.Counter(g["model"] for g in GX)
QWEN = [m for m in S["models"] if "Qwen" in m][0]
assert LATER_BY_MODEL.most_common(1)[0][0] == QWEN and 2 * LATER_BY_MODEL[QWEN] > len(GX)   # "lean toward Qwen"
PLANNED_RUNS = run.RUNS

WHO = {
    "K0a": "4 told 2026-11-14",
    "K0b": "4 with a true clock line",
    "K0n": "4 with no date",
    "K0n-old": "4 with no date; the plan's first task wording",
    "K1-BARE": "3 told 2026-11-14; 1 told \"the 23rd\" by its person",
    "K1-CLOCK": "3 told 2026-11-14; 1 with a true clock line",
    "K1-WITNESS": "3 told 2026-11-14; 1 holding a LIVE timewitness report",
    "K2-BARE": "3 with true clock lines; 1 on a set-back machine told \"the 14th\"",
    "K2-CLOCK": "3 with true clock lines; 1 with a set-back clock line (14 Nov)",
    "K2-WITNESS": "3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov",
    "K2m": "3 with set-back clock lines (14 Nov); 1 with a true clock line",
    "K3-CLOCK": "2 told 2026-11-14; 2 with true clock lines",
    "K3-WITNESS": "2 told 2026-11-14; 2 holding LIVE timewitness reports",
}
CHECK = {"T0": "none", "T1": "`date -u`", "T2": "`timewitness`"}


def who(c):
    base = c.replace("-rule", "")
    key = base.rsplit("-", 1)[0] if base.rsplit("-", 1)[-1] in ("T0", "T1", "T2") else base
    w = WHO[key]
    if c.endswith("-rule"):
        w += "; rule sentence"
    return w


def arm(c):
    for a in ("T0", "T1", "T2"):
        if ("-" + a) in c:
            return a
    return "T0"


# ---------------------------------------------------------------- header, question, setting

TASK0 = run.task_text({"cid": "x"}, "CLOSED_FIRST")
P("# Can a group of agents agree on what time it is?")
P("")
P("Four AI agents must make one decision together, and the right decision depends on today's date. "
  "Each agent holds its own evidence about the date, and some of that evidence is wrong. This experiment "
  "measures whether the group reaches the right decision and the right date, and what changes that: the "
  "kind of evidence each agent holds, and whether each agent can run a check on its own machine (a plain "
  "clock read, or `timewitness`). It is part of the timewitness project; the tool itself is described in the "
  "README two folders up.")
P("")
P("Every tool result in this experiment was simulated by the harness. No agent ran a command. The text the "
  "harness returned was built from real timewitness runs measured on one Mac (section \"What the agents "
  "saw\").")
P("")
P("## The question")
P("")
P("Agents that work together arrive with different beliefs about the date: one was told a date when its long "
  "session began, one has a clock line, one has run `timewitness`. When they must agree on something that "
  "depends on the date:")
P("")
P("1. Does the group land on the truth?")
P("2. Does the kind of time evidence a member holds change that?")
P("3. Does a check each member can run on its own machine settle a dispute, including when most of the group "
  "shares a wrong clock?")
P("")
P("## The setting, in plain words")
P("")
P("- **The team.** Four copies of one model, called Agent A, B, C and D. Each works on its own machine and "
  "talks with the others only through a team channel; the harness passes the messages on.")
P("- **The truth.** In the story it is Monday 2026-11-23, 10:20 UTC at the first turn, and each turn is one "
  "minute later.")
P("- **The task**, given to every agent: \"%s\" The right answer is CLOSED: the window closed about two and a "
  "half days earlier. Half the groups saw OPEN named first instead of CLOSED (see \"Design\")." % TASK0.replace(
      "Team task: ", ""))
P("- **The talk.** Four turns. Turn 0: each agent states its position alone. Turns 1 and 2: each sees what all "
  "four said in the turn before, and replies. Turn 3: each sees turn 2 and gives a final answer. The team's "
  "decision is the answer at least three of the four give; with no such answer the group has no majority.")
P("- **Two lines end every message**: `DATE:` with the date the agent believes it is (or UNKNOWN), then "
  "`POSITION:` (turns 0 to 2) or `FINAL:` (turn 3) with CLOSED, OPEN or CANNOT_TELL. So each message records "
  "both a decision and a belief about the date.")
P("- **Machines.** A *healthy* machine's clock is right. A *set-back* machine's system clock is nine days "
  "behind: it reads Saturday 2026-11-14.")
P("")
P("Each agent's evidence about the date is one of these (labels used through this README):")
P("")
P(table(["Label", "What the agent is given", "Where"], [
    ["SESSION_DATE", "\"%s\" This is what an agent harness says when a session begins. Nothing says that nine "
     "days have passed." % run.evidence_text("SESSION_DATE", 0), "briefing (system prompt)"],
    ["BARE", "\"%s\" (or \"the 14th\"). A person's remark, with the person as its source." %
     run.evidence_text("BARE_TRUE", 0), "briefing"],
    ["CLOCK", "The briefing says \"%s\" Each turn's message then starts with a line in the format of "
     "`hooks/clock-line.py`, such as \"%s\" The minute moves on each turn." % (
         run.CLOCK_FRAME, run.clock_line(run.clock_at(0, "healthy"))), "briefing, and every turn"],
    ["WITNESS", "\"You ran `timewitness`. It printed:\" followed by a timewitness report (LIVE, with the true "
     "date; or, for a wrong member, a LIVE report rebuilt to read 2026-11-14 from a measurement made on "
     "2026-11-23).", "briefing"],
    ["NONE", "No date at all (controls K0n and K0n-old).", "-"],
]))
P("")
P("The checks an agent may be offered (one per condition, asked for in turn 1 with a line such as "
  "`ACTION: CHECK_CLOCK`; the result is shown only to the asker, at turn 2; the asker may then report it in "
  "its turn-2 message, which the others read at turn 3):")
P("")
P(table(["Arm", "Check", "Healthy machine returns", "Set-back machine returns"], [
    ["T0", "none", "-", "-"],
    ["T1", "CHECK_CLOCK: runs `date -u`", "`%s`" % run.date_u("healthy", 0), "`%s` (the wrong date again)" %
     run.date_u("setback", 0)],
    ["T2", "RUN_TIMEWITNESS: runs `timewitness`", "LIVE with the true time", "ADRIFT: a signed time of "
     "2026-11-23 and \"the local clock is 8d 23h behind it\""],
]))
P("")
# ---------------------------------------------------------------- conditions and design

MISSING = S["main_set_missing"]
assert len(MISSING) == len(SHORT_CELLS) and all(x["rows_for_this_run"] == 0 for x in MISSING)
assert not SHORT_CELLS or MISSING[0]["condition"] == SHORT_CELLS[0][0]
MISS_LATER = [y for x in MISSING for y in x["rows_of_cell"] if y["run"] > x["run"]]
assert all(y["status"] == "stopped: HTTP 402" for y in MISS_LATER)
P("## Conditions")
P("")
P("The plan was %d runs of each condition with each of %d models. The router stopped answering after the "
  "credit on the account was used up (HTTP 402 from %s; section \"Cost and calls\"). The results below use "
  "runs 1 and 2, which every model finished: %d groups of four agents per condition, %d agents%s. Checks: T0 "
  "none, T1 `date -u`, T2 `timewitness`." % (
      PLANNED_RUNS, NM, S["first_402_utc"][11:16] + " UTC", GPC, 4 * GPC,
      "" if not SHORT_CELLS else " (except %s, with %d groups: %s run %d has no row at all; see \"Limits\")" % (
          SHORT_CELLS[0] + (MODEL_SHORT[MISSING[0]["model"]].split("-")[0], MISSING[0]["run"]))))
P("")
rows = []
for c in S["conditions"]:
    rows.append([c, who(c), CHECK[arm(c)]])
P(table(["Condition", "Members", "Check offered"], rows))
P("")
P("- **K0a, K0b** are controls: nobody holds the true date, or everybody does.")
P("- **K0n, K0n-old** test the task text itself: no member has any date. K0n uses the task above. K0n-old uses "
  "the first wording of the plan, \"%s\", which a design check flagged because its past tense (\"closed on\") "
  "gives the answer away." % run.TASK_OLD.replace("Team task: ", ""))
P("- **K1** (informed minority): one member holds the true date as BARE, CLOCK or WITNESS; three hold "
  "SESSION_DATE. All four machines are healthy, so a plain clock read returns the truth to anyone who asks.")
assert "LIVE 2026-11-14T10:19:52Z" in run.report("brief_wrong", 0)
assert "LIVE 2026-11-23T10:19:52Z" in run.report("brief_true", 0)
P("- **K2** (wrong minority): three members have true clock lines; one sits on a set-back machine and holds the "
  "wrong date as BARE, CLOCK or WITNESS. Its WITNESS is a LIVE report that reads 2026-11-14 10:19:52. It was "
  "rebuilt from a measurement made on 2026-11-23: every time in it was moved back nine days, and the real "
  "Bitcoin block of 14 November was put in (section \"What the agents saw\"). It stands for a report that was "
  "true when made and is wrong when read; no report was actually made on 14 November.")
P("- **K2m** (wrong majority): three members sit on set-back machines with clock lines reading 14 Nov; one "
  "healthy member has a true clock line. A vote among clocks gives the wrong answer here.")
P("- **K3** (split): two SESSION_DATE members, two informed members.")
P("- **Rule cells** add one sentence to every briefing: \"%s\"" % run.RULE)
P("")
P("### Design")
P("")
P("- The model, temperature (%.1f) and max_tokens (%d) are the same for all four members of a group. Models: "
  "%s, all through Hugging Face Inference Providers (provider deepinfra)." % (
      run.TEMPERATURE, run.MAX_TOKENS, ", ".join("`%s`" % m for m in S["models"])))
ROLES = collections.defaultdict(collections.Counter)
for _g in S["groups"]:
    ROLES[_g["family"]][tuple(sorted(collections.Counter(m["role"] for m in _g["members"]).items()))] += 1
assert {f: set(v) for f, v in ROLES.items()} == {
    "K0": {(("base", 4),)}, "K1": {(("base", 3), ("odd", 1))}, "K2": {(("base", 3), ("odd", 1))},
    "K2m": {(("base", 3), ("odd", 1))}, "K3": {(("base", 2), ("pair", 2))}}, dict(ROLES)
assert all(m["machine"] == ("healthy" if m["role"] == "odd" else "setback")
           for g in S["groups"] if g["family"] == "K2m" for m in g["members"])
assert all(m["machine"] == ("setback" if m["role"] == "odd" else "healthy")
           for g in S["groups"] if g["family"] == "K2" for m in g["members"])
assert all((m["evidence"] == "SESSION_DATE") == (m["role"] == "base")
           for g in S["groups"] if g["family"] in ("K1", "K3") for m in g["members"])
P("- Roles, used in the tables: in K1, K2 and K2m one member's evidence differs from the other three's. It is the "
  "*odd* member, and the three are the *base* members. In K1 the odd member is the informed one; in K2 it is the "
  "wrong one; in K2m it is the one healthy member. In K3 the two informed members are the *pair*, and the two "
  "SESSION_DATE members are the base. In K0 all four members are base.")
P("- Seat and option order were counterbalanced over the %d planned runs, the same way for every model and "
  "condition: the odd member sits at A, B, C, D, B, A, D, C; odd runs name CLOSED first and even runs name OPEN "
  "first. K3's pairs sit at AB, AD, CD, BC, AC, BD, BD, AC. Messages are always listed A, B, C, D. In runs 1 and "
  "2, which the results use, the odd member sat at A (CLOSED named first) and B (OPEN named first); it never "
  "sat at C or D." % PLANNED_RUNS)
P("- Each member's machine is one of four profiles (measured offsets, Hub counts and Bitcoin times; an uptime "
  "set by the harness), drawn from a seed per condition and run, so no two members of a group print the same "
  "report.")
TXT = S["text_checks"]
REPORT_WORDS = len(run.report("brief_true", 0).split())
assert 150 <= REPORT_WORDS <= 210, REPORT_WORDS
assert "Keep each message under 120 words." in run.PROCESS   # an instruction, not a cap
assert TXT["witness_report_lines"] == [8] and TXT["witness_report_lines_repeated_max"] < 8
P("- The briefing states the decision rule (3 of 4). Members were asked to keep each message under 120 words "
  "(%d of %d messages went over). That is shorter than a timewitness report (about %d words), so a WITNESS "
  "member could not paste its report whole without going over: no holder repeated more than %d of its report's "
  "8 lines word for word in one message." % (O["messages_over_120_words"], O["messages"], round(REPORT_WORDS, -1),
                            TXT["witness_report_lines_repeated_max"]))
P("- An action counts wherever `ACTION: <name>` appears in the turn-1 message. A request that is not run (not "
  "offered, or asked outside turn 1) gets a one-line note in the next prompt.")
P("- `protocol.md` shows every briefing, every turn prompt and every simulated tool result. `run.py` stores a "
  "hash of all of it in each row.")
P("")
# ---------------------------------------------------------------- numbers the results rest on

G = S["groups"]


def members(cond=None, role_=None, **kw):
    out = []
    for g in G:
        if cond and g["condition"] != cond:
            continue
        if any(g[k] != v for k, v in kw.items()):
            continue
        for m in g["members"]:
            if role_ and m["role"] != role_:
                continue
            out.append(m)
    return out


def count(ms, pred):
    return sum(1 for m in ms if pred(m)), len(ms)


def closed(m):
    return m["labels"]["final"] == "CLOSED"


def dtrue(m):
    return m["final_date_class"] == "true"


def pooled(cids, role_=None, pred=closed):
    ms = [m for c in cids for m in members(c, role_)]
    return count(ms, pred)


def gpooled(cids, lab="CLOSED"):
    return (sum(BC[c]["group_result"][lab] for c in cids), sum(BC[c]["groups"] for c in cids))


KINDS = ("BARE", "CLOCK", "WITNESS")
K1T0 = ["K1-%s-T0" % k for k in KINDS]
K1T1 = ["K1-%s-T1" % k for k in KINDS]
K2T = {a: ["K2-%s-%s" % (k, a) for k in KINDS] for a in ("T0", "T1", "T2")}

# K0n-old: final DATE lines after the deadline although no date was given
def after_deadline(m):
    d = m["dates"][3]
    return bool(d and d not in ("UNKNOWN",) and d > "2026-11-20")


def before_2026(m):
    d = m["dates"][3]
    return bool(d and d != "UNKNOWN" and d < "2026-01-01")


N_K0N_AFTER = count(members("K0n"), after_deadline)
N_K0NOLD_AFTER = count(members("K0n-old"), after_deadline)
N_K0N_OLDYEAR = count(members("K0n"), before_2026)
N_K0NOLD_OLDYEAR = count(members("K0n-old"), before_2026)

# ---------------------------------------------------------------- results in brief

P("## Results in brief")
P("")
brief = []
k0n, k0no = fin("K0n"), fin("K0n-old")
assert k0no[0] > k0n[0] and k0n[0] == 0
brief.append("**The first task wording gave the answer away.** With no date at all, agents gave CLOSED in %s "
             "finals under the plan's first wording (\"closed on\") and in %s under the wording used here." % (
                 K(k0no), K(k0n)))
k1t0b, k1t1b = pooled(K1T0, "base"), pooled(K1T1, "base")
assert k1t0b[0] == 0 and gpooled(K1T0)[0] == 0
k1maj = (sum(role(c, "base")["cites_majority"] for c in K1T0), sum(role(c, "base")["n"] for c in K1T0))
k1src = (sum(role(c, "base")["cites_briefing"] for c in K1T0), sum(role(c, "base")["n"] for c in K1T0))
brief.append("**One informed member never moved three members told 2026-11-14, whatever its evidence.** With no "
             "check offered, the three ended CLOSED in %s finals and no group decided CLOSED (%s), whether the "
             "informed member held a remark, a clock line or a timewitness report. The three leaned on their "
             "number (%s mention the majority) and on their briefing (%s mention the prompt or briefing; both "
             "keyword counts)." % (K(k1t0b), K(gpooled(K1T0)), K(k1maj), K(k1src)))
# p-values: two-sided Fisher exact tests that score.py computes (summary.json,
# fisher_two_sided). Each compares groups, or one member per group.
FX = S["fisher_two_sided"]
NOISE_P = 0.1   # "inside noise" in this README: p above this
assert all(v["unit"] in ("groups", "one member per group") for v in FX.values())


def pval(key, counts, noisy=None):
    """'p = x' for a contrast. counts: the two (k, n) pairs the sentence states,
    in the order score.py compares them. noisy=True: the sentence calls the
    difference inside noise; noisy=False: the sentence treats it as clear."""
    v = FX[key]
    assert ((v["a"], v["n1"]), (v["b"], v["n2"])) == tuple(tuple(c) for c in counts), (key, v, counts)
    if noisy is True:
        assert v["p"] > NOISE_P, (key, v["p"])
    if noisy is False:
        assert v["p"] < 0.05, (key, v["p"])
    return ("p = %.2f" if v["p"] >= 0.1 else "p = %.3f") % v["p"]


SIZE = "simulated tool output; %d groups per cell, %d per model" % (GPC, R)
assert "23rd" in run.evidence_text("BARE_TRUE", 0) and "14th" in run.evidence_text("BARE_WRONG", 0)
assert not any(re.search(r"Nov|20\d\d|month|year", run.evidence_text(e, 0), re.I) for e in ("BARE_TRUE", "BARE_WRONG"))
BT = TXT["bare_t0"]
b1, b2 = BT["K1-BARE-T0"], BT["K2-BARE-T0"]
assert b1["t0_cannot_tell_naming_month_or_year"] == b1["t0_cannot_tell"] > b1["odd_members"] / 2
assert b2["t0_cannot_tell"] > b2["odd_members"] / 2
oddk = {k: fin("K1-%s-T0" % k, r="odd") for k in KINDS}
assert oddk["BARE"][0] < oddk["CLOCK"][0] < oddk["WITNESS"][0]
k3gw, k3gc = grp("K3-WITNESS-T0"), grp("K3-CLOCK-T0")
brief.append("**The kind of evidence may change who holds firm; these cells cannot tell CLOCK from WITNESS.** "
             "Alone against three, the informed member ended CLOSED in %s groups with a remark, %s with a clock line "
             "and %s with a timewitness report. The remark gave a day only (\"the 23rd\", no month or year), and %s "
             "remark holders opened at CANNOT_TELL, each saying the month or year was missing, so that cell is not "
             "a fair comparison. CLOCK against WITNESS (%s against %s) is inside noise (%s). So is the split case: "
             "with two informed members against two, the group decided CLOSED in %s groups with timewitness reports "
             "and %s with clock lines (%s)." % (
                 K(oddk["BARE"]), K(oddk["CLOCK"]), K(oddk["WITNESS"]), K((b1["t0_cannot_tell"], b1["odd_members"])),
                 K(oddk["CLOCK"]), K(oddk["WITNESS"]),
                 pval("k1t0_odd_closed_witness_vs_clock", (oddk["WITNESS"], oddk["CLOCK"]), noisy=True),
                 K(k3gw), K(k3gc), pval("k3_group_closed_witness_vs_clock", (k3gw, k3gc), noisy=True)))
k1t0g, k1t1g = gpooled(K1T0), gpooled(K1T1)
assert k1t1g[0] > k1t0g[0] and k1t1b[0] > k1t0b[0]
assert not any(arm(c) == "T2" for c in S["conditions"] if c.startswith("K1"))   # K1 had no timewitness arm
brief.append("**A check on one's own machine settled it when machines were healthy.** Offered `date -u`, the three "
             "SESSION_DATE members ended CLOSED in %s finals and the group decided CLOSED in %s (with no check: %s "
             "and %s). On a healthy machine `date -u` returns the true date by construction. K1 had no "
             "`timewitness` arm, so whether `timewitness` adds anything there was not tested." % (
                 K(k1t1b), K(k1t1g), K(k1t0b), K(k1t0g)))
k2m = {a: grp("K2m-" + a) for a in ("T0", "T1", "T2")}
assert k2m["T0"][0] == 0 and k2m["T1"][0] == 0 and k2m["T2"][0] == k2m["T2"][1]
brief.append("**When most clocks were wrong, only timewitness fixed it.** With three of four clocks set back, the "
             "group decided CLOSED in %s groups with no check, %s with `date -u` (which repeats the wrong clock), "
             "and %s with `timewitness` (which reports the clock as ADRIFT and gives the signed time; %s against "
             "`date -u`). In this simulation that follows from how the two tools' outputs were built." % (
                 K(k2m["T0"]), K(k2m["T1"]), K(k2m["T2"]),
                 pval("k2m_group_closed_t2_vs_t1", (k2m["T2"], k2m["T1"]), noisy=False)))
odd_t = {a: pooled(K2T[a], "odd", dtrue) for a in ("T0", "T1", "T2")}
assert odd_t["T1"][0] < odd_t["T0"][0] < odd_t["T2"][0] == odd_t["T2"][1]
odd_tk = {k: (fdate("K2-%s-T0" % k, r="odd"), fdate("K2-%s-T1" % k, r="odd")) for k in KINDS}
assert all(t1[0] < t0[0] for t0, t1 in odd_tk.values())                       # "within each kind"
_drop = {k: t0[0] - t1[0] for k, (t0, t1) in odd_tk.items()}
assert 2 * _drop["BARE"] > sum(_drop.values())                                # "most of the drop"
K2ALL = [c for c in S["conditions"] if c.startswith("K2-")]
assert gpooled(K2ALL)[0] == gpooled(K2ALL)[1]
brief.append("**A plain clock read made a wrong member's date belief worse; timewitness corrected it.** The one "
             "member on a set-back machine (K2) ended believing the true date in %s finals with no check, %s after "
             "`date -u` (%s) and %s after `timewitness`. The drop held within each kind of wrong evidence (%s), and "
             "most of it was in BARE: that remark gave no month or year, and `date -u` supplied a wrong one. The "
             "group's decision was right in every K2 group either way, because three true clocks outvoted it." % (
                 K(odd_t["T0"]), K(odd_t["T1"]), pval("k2_odd_datetrue_t0_vs_t1", (odd_t["T0"], odd_t["T1"]),
                                                      noisy=False), K(odd_t["T2"]),
                 "; ".join("%s %s to %s" % (k, K(odd_tk[k][0]), K(odd_tk[k][1])) for k in KINDS)))
off = [m for g in G if g["arm"] in ("T1", "T2") for m in g["members"]]
upt = count(off, lambda m: m["action_run"])
assert upt[0] >= 0.9 * upt[1]
# members offered a check that did not run it
NORUN = [(g, m) for g in G if g["arm"] in ("T1", "T2") for m in g["members"] if not m["action_run"]]


def mates_named(g, m):
    return sum(1 for x in g["members"] if x is not m and x["ran_and_named_it_in_turn2"])


nr_sd = [(g, m) for g, m in NORUN if m["evidence"] == "SESSION_DATE"]
nr_switched = [(g, m) for g, m in nr_sd if m["labels"]["t2"] != "CLOSED" and m["labels"]["final"] == "CLOSED"
               and mates_named(g, m) > 0]
nr_stayed = [(g, m) for g, m in nr_sd if m["labels"]["final"] == "OPEN"]
assert len(nr_switched) + len(nr_stayed) == len(nr_sd) and nr_switched and nr_stayed
SD_OFFERED = [m for g in G if g["arm"] in ("T1", "T2") for m in g["members"] if m["evidence"] == "SESSION_DATE"]
brief.append("**Agents almost always used an offered check** (%s agents ran it). %s SESSION_DATE members offered a "
             "check skipped it; %d switched to CLOSED after teammates reported their checks, %d did not. So these "
             "data cannot tell whether agreement came from each member checking for itself or from one member's "
             "result persuading the rest." % (K(upt), K((len(nr_sd), len(SD_OFFERED))), len(nr_switched),
                                              len(nr_stayed)))
RULE_C = "K1-CLOCK-T0-rule"
DS = [m for m in S["models"] if "DeepSeek" in m][0]
NON_DS = [m for m in S["models"] if m != DS]
BCM = S["by_condition_model"][RULE_C]
rule_base, norule_base = fin(RULE_C, r="base"), fin("K1-CLOCK-T0", r="base")
rule_g, norule_g = grp(RULE_C), grp("K1-CLOCK-T0")
assert norule_base[0] == 0 and norule_g[0] == 0 and rule_g[0] == 2              # "both groups"
assert BCM[DS]["by_role"]["base"]["finals"]["CLOSED"] == rule_base[0] > 0
assert BCM[DS]["group_result"]["CLOSED"] == rule_g[0]
rule_other = (sum(BCM[m]["by_role"]["base"]["finals"]["CLOSED"] for m in NON_DS),
              sum(BCM[m]["by_role"]["base"]["n"] for m in NON_DS))
assert rule_other[0] == 0 and role(RULE_C, "base")["final_date"]["true"] == 0
LATER_RULE = [g for g in S["groups_extra"] if g["condition"] == RULE_C]
later_rule_base = count([m for g in LATER_RULE for m in g["members"] if m["role"] == "base"], closed)
assert later_rule_base[0] == 0 and not any(g["model"] == DS for g in LATER_RULE)
later_rule_models = collections.Counter(g["model"] for g in LATER_RULE)
brief.append("**With a rule sentence that ranks evidence, %d SESSION_DATE members ended CLOSED, all DeepSeek, in "
             "%d groups.** With the rule, %s SESSION_DATE members in K1-CLOCK ended CLOSED (%s without it), and %s "
             "groups decided CLOSED (%s without; inside noise, %s). All %d of those members and both groups were "
             "DeepSeek; Qwen and gemma SESSION_DATE members ended CLOSED in %s. None of the %d wrote the true date "
             "(section 6)." % (
                 rule_base[0], rule_g[0], K(rule_base), K(norule_base), K(rule_g), K(norule_g),
                 pval("k1clock_rule_group_closed", (rule_g, norule_g), noisy=True), rule_base[0], K(rule_other),
                 rule_base[0]))
for b in brief:
    P("- " + b)
P("")
P("Cells are small: %d groups per condition (%d per model), from three open models, one scenario and simulated "
  "tools; see \"Limits\". Where a p-value is given, it is a two-sided Fisher exact test on two counts of groups "
  "(or of one member per group), computed by `score.py`; an independent check of this write-up used the same "
  "test as a rough guide, and at this size it is no more than that. \"Inside noise\" means p above %.1f. The "
  "later runs that some models finished (runs %d to %d: %d groups, %d of them %s) point the same way on the cells "
  "that section 9 shows. They lean toward Qwen, and DeepSeek, the only model the rule sentence moved, reached no "
  "later run of the rule cell." % (GPC, R, NOISE_P, LATER_RUNS[0], LATER_RUNS[1], len(GX), LATER_BY_MODEL[QWEN],
                                   MODEL_SHORT[QWEN]))
P("")

# ---------------------------------------------------------------- what this says about timewitness

t2cells = [c for c in S["conditions"] if arm(c) == "T2"]
T2FAM = sorted({c.split("-")[0] for c in t2cells})
assert T2FAM == ["K2", "K2m"], T2FAM
t2g = gpooled(t2cells)
t2u = (sum(BC[c]["unanimous"] for c in t2cells), sum(BC[c]["groups"] for c in t2cells))
assert t2g[0] == t2g[1] and t2u[0] == t2u[1]
sb_all = [m for g in G for m in g["members"] if m["machine"] == "setback"]
sb_t2 = [m for m in sb_all if m["action_offered"] == "RUN_TIMEWITNESS"]
sb_t2_ran = [m for m in sb_t2 if m["action_run"]]
assert count(sb_t2_ran, dtrue)[0] == len(sb_t2_ran)
kw0 = fin("K1-WITNESS-T0", r="base")
assert kw0[0] == 0
k2w0 = fdate("K2-WITNESS-T0", r="odd")
k2c0 = fdate("K2-CLOCK-T0", r="odd")
k2b0 = fdate("K2-BARE-T0", r="odd")
assert k2w0[0] < k2c0[0] <= k2b0[0]
ORR = HR["old_report_recognised"]
assert ORR["considered_its_report_old"] <= ORR["members"] / 4
P("## What this says about timewitness")
P("")
P("The question behind this experiment: is timewitness useful for how agents perceive time, and for working "
  "together, passing evidence on and reaching agreement? In this setting:")
P("")
P("- **Perceiving time: yes, when run by the agent itself on a wrong clock (%s).** Every agent on a set-back "
  "machine that ran `timewitness` ended with the true date (%s). `date -u` cannot do this, because it reads the "
  "same wrong clock. Whether `timewitness` adds anything over a plain clock read on a healthy machine was not "
  "tested: K1 had no `timewitness` arm." % (SIZE, K(count(sb_t2_ran, dtrue))))
P("- **Communication: a relayed report persuaded little.** A member holding a LIVE timewitness report did not move "
  "three members told 2026-11-14 (they ended CLOSED in %s). They called it a claim they could not check. Members "
  "were asked to keep messages under 120 words, so holders summarised their reports or quoted parts of them (at "
  "most %d of a report's 8 lines word for word). With two informed members against two, the group decided CLOSED "
  "in %s groups with reports against %s with clock lines; the difference is inside noise (%s; section 2). No form "
  "of evidence passed through the channel reliably." % (
      K(kw0), TXT["witness_report_lines_repeated_max"], K(k3gw), K(k3gc),
      pval("k3_group_closed_witness_vs_clock", (k3gw, k3gc), noisy=True)))
P("- **Holders seldom said the report might be old.** A wrong member holding a LIVE report dated 14 November "
  "(rebuilt from a 23 November measurement) ended believing the true date in %s finals. The like-for-like "
  "contrast is a wrong member with a set-back clock line: %s (inside noise, %s). A wrong member told \"the 14th\" "
  "by a person got there in %s, but that remark gave no month or year and %s of those members opened at "
  "CANNOT_TELL, so that comparison is not a fair one. The report's first line carried the old date, yet only %d "
  "of the %d wrong members holding it said, in any turn, that it might be old (one of them only after running "
  "`timewitness` again; read by hand). With six holders per cell, this shows that a report which looks like "
  "proof can go unquestioned, not how often." % (
      K(k2w0), K(k2c0), pval("k2t0_odd_datetrue_clock_vs_witness", (k2c0, k2w0), noisy=True), K(k2b0),
      K((b2["t0_cannot_tell"], b2["odd_members"])), ORR["considered_its_report_old"], ORR["members"]))
k2t0g = gpooled(K2T["T0"])
k2t0u = (sum(BC[c]["unanimous"] for c in K2T["T0"]), sum(BC[c]["groups"] for c in K2T["T0"]))
assert k2t0g[0] == k2t0g[1] and k2t0u[0] < k2t0u[1]
TC = [c for c in S["conditions"] if arm(c) in ("T1", "T2")]
T0C = [c for c in S["conditions"] if arm(c) == "T0" and not c.startswith("K0")]
T0FAM = sorted({c.split("-")[0] for c in T0C})
assert T0FAM == ["K1", "K2", "K2m", "K3"] and any(c.endswith("-rule") for c in T0C), (T0FAM, T0C)
T0C_TEXT = "the T0 cells of %s and %s, rule cells included" % (", ".join(T0FAM[:-1]), T0FAM[-1])
nm_ = (sum(BC[c]["all"]["ran_and_named_it_in_turn2"] for c in TC), sum(BC[c]["all"]["action_run"] for c in TC))
s2f_ = {k: sum(BC[c]["all"]["steps"]["t2->final"][k] for c in TC) for k in ("changed", "of")}
s2f0_ = {k: sum(BC[c]["all"]["steps"]["t2->final"][k] for c in T0C) for k in ("changed", "of")}
assert s2f_["changed"] < 0.05 * s2f_["of"] and s2f0_["changed"] < 0.05 * s2f0_["of"]   # "rare"
assert 2 * upt[0] > upt[1] and 2 * nm_[0] > nm_[1]                                    # "most ... most"
P("- **Agreement: yes, when members could check (%s).** `timewitness` was offered only in %s. There %s "
  "groups decided CLOSED, all unanimously (%s). In the wrong-minority groups (K2) the group decided CLOSED "
  "without any check too (%s; unanimous in %s), because three true clocks outvoted one wrong one. The difference "
  "`timewitness` made to the group decision was in the wrong-majority case (K2m: %s with `timewitness`, %s with "
  "no check and %s with `date -u`)." % (
      SIZE, " and ".join(T2FAM), K(t2g), K(t2u), K(k2t0g), K(k2t0u), K(k2m["T2"]), K(k2m["T0"]), K(k2m["T1"])))
P("- **Working together: most agents checked, and most of those said so.** %s agents offered a check ran it. Of "
  "those, %s named it in the message the others read next (keyword count). Changes after reading the others' "
  "turn-2 messages were rare with or without a check: %s agents changed their label at that step in cells with a "
  "check, and %s in cells without one (%s; section 5 gives the parse rule behind these denominators)." % (
      K(upt), K(nm_), K((s2f_["changed"], s2f_["of"])), K((s2f0_["changed"], s2f0_["of"])), T0C_TEXT))
P("")
P("What this does not show: how often a real agent would think to run a check unprompted, how real models "
  "behave with real tool output, and whether the same holds for Claude, larger teams, mixed models or other gaps.")
P("")

# ---------------------------------------------------------------- results table

P("## Results by condition")
P("")
P("Group result: the label at least 3 of the 4 finals give. Final DATE true: the agent's last DATE line says "
  "2026-11-23. All %d models pooled." % NM)
P("")
rows = []
for c in S["conditions"]:
    a = BC[c]
    rows.append([c, who(c), CHECK[arm(c)], K(grp(c)), K(grp(c, "OPEN")), K(grp(c, "CANNOT_TELL")),
                 K(grp(c, "NO_MAJORITY")), K(fin(c)), K(fin(c, "CANNOT_TELL")), K(fdate(c))])
P(table(["Condition", "Members", "Check", "Group CLOSED", "Group OPEN", "Group CANNOT_TELL", "No majority",
         "Finals CLOSED", "Finals CANNOT_TELL", "Final DATE true"], rows))
P("")
P("`summary.md` has every table by role, by model and by step; `summary.json` has every number and every "
  "scored group.")
P("")
# ---------------------------------------------------------------- 1. controls

P("### 1. Controls and the task text")
P("")
assert N_K0N_OLDYEAR[0] > 0
P("- K0b (four true clock lines): the group decided CLOSED in %s; finals CLOSED %s. Every model can do the task "
  "when the date is plain." % (K(grp("K0b")), K(fin("K0b"))))
P("- K0a (four told 2026-11-14): the group decided OPEN in %s; finals CLOSED %s, final DATE 2026-11-14 in %s. "
  "Here a CLOSED final would be a leak, not a right answer, since nobody holds the true date." % (
      K(grp("K0a", "OPEN")), K(fin("K0a")), K(fdate("K0a", "session"))))
P("- K0n against K0n-old (no date at all): finals CLOSED %s against %s; CANNOT_TELL %s against %s; OPEN %s "
  "against %s. Final DATE lines after the deadline, although no date was given: %s against %s. Dates before "
  "2026 (the models' own sense of the year): %s against %s." % (
      K(fin("K0n")), K(fin("K0n-old")), K(fin("K0n", "CANNOT_TELL")), K(fin("K0n-old", "CANNOT_TELL")),
      K(fin("K0n", "OPEN")), K(fin("K0n-old", "OPEN")), K(N_K0N_AFTER), K(N_K0NOLD_AFTER), K(N_K0N_OLDYEAR),
      K(N_K0NOLD_OLDYEAR)))
P("")
P("Reading the K0n-old transcripts: some agents took the date from the past tense (one wrote \"Given that the "
  "current date is 2026-11-21\"), and some chose CLOSED as the safer action under doubt (\"a late notice is "
  "correctable\"), which the old option text (\"do not submit, file a late notice\") invites. Both were "
  "predicted by the design check; the task wording and the option text were changed before the run for that "
  "reason. In K0n, with neutral wording, agents without a date said OPEN (some from a remembered year such as "
  "2024 or 2025) or CANNOT_TELL, never CLOSED%s." % ("" if fin("K0n")[0] == 0 else " in all but %d finals" %
                                                    fin("K0n")[0]))
P("")

# ---------------------------------------------------------------- 2. kind of evidence

P("### 2. What the kind of evidence changed (no check offered)")
P("")
P("Informed minority (K1, T0): one member holds the true date, three hold SESSION_DATE.")
P("")
rows = []
for k in KINDS:
    c = "K1-%s-T0" % k
    rows.append([k, K(grp(c)), K(fin(c, r="base")), K(fdate(c, r="base")), K(fin(c, r="odd")),
                 K(fdate(c, r="odd")), K(fin(c, "OPEN", r="odd"))])
P(table(["Odd member's evidence", "Group CLOSED", "Base finals CLOSED", "Base final DATE true",
         "Odd final CLOSED", "Odd final DATE true", "Odd final OPEN"], rows))
P("")
oddmaj = (sum(role(c, "odd")["cites_majority"] for c in K1T0), sum(role(c, "odd")["n"] for c in K1T0))
# hand codes for two keyword searches (hand_reads.json), checked against the hit lists score.py writes
AUTH_CODES = {(c["group_id"], c["seat"]): c["code"] for c in HR["briefing_called_authoritative"]["codes"]}
assert set(AUTH_CODES) == {(h["group_id"], h["seat"]) for h in TXT["auth_hits"]}, "hand codes != keyword hits"
assert set(AUTH_CODES.values()) == {"yes", "no"}
AUTH_YES = [k for k, v in AUTH_CODES.items() if v == "yes"]
assert all("DeepSeek" in k[0] or "gemma" in k[0] for k in AUTH_YES)
SHARED = HR["shared_briefing_assumed"]["groups"]
assert all(x["group_id"] in {h["group_id"] for h in TXT["shared_hits_k1_k3"]} for x in SHARED)
assert len({x["group_id"] for x in SHARED}) == len(SHARED) and all("DeepSeek" in x["group_id"] for x in SHARED)
assert all(x["group_id"] in {g["group_id"] for g in G} for x in SHARED)
SHARED_KIND = collections.Counter(x["kind"] for x in SHARED)
assert set(SHARED_KIND) == {"called_date_fabricated", "took_missing_date_as_unreliable"}
assert TXT["briefings_naming_a_difference"] == 0
assert TXT["auth_regex"] == "ground truth|authoritative|primary source|takes precedence", TXT["auth_regex"]
K1K3_GROUPS = [g for g in G if g["family"] in ("K1", "K3")]
SHARED_NC = HR["shared_briefing_assumed"]["not_counted"]
assert all("DeepSeek" in x["group_id"] and x["group_id"] in {g["group_id"] for g in K1K3_GROUPS} for x in SHARED_NC)
assert not {x["group_id"] for x in SHARED_NC} & {x["group_id"] for x in SHARED}
assert "every message in K1 and K3, main set (%d messages match)" % TXT["shared_hit_messages_k1_k3"] in \
    HR["shared_briefing_assumed"]["method"]
P("No SESSION_DATE member here ended CLOSED, whatever the informed member held. In turns 1 to 3, %s of them "
  "mentioned the majority (\"three of us\", \"majority\") and %s mentioned their prompt or briefing as the "
  "source of their date (keyword counts; regexes in summary.json). Of the informed members, %s mentioned the "
  "majority. Reading the messages: the SESSION_DATE members called a teammate's clock line or report something "
  "they could not check, and their own briefing date something given to them. Across the main set, %d of the %d "
  "SESSION_DATE agents called their briefing date authoritative, the ground truth or the primary source, or said "
  "it takes precedence, all of them DeepSeek or gemma (a keyword search found %d agents; each was read by hand; "
  "codes in `hand_reads.json`)." % (
      K(k1maj), K(k1src), K(oddmaj), len(AUTH_YES), TXT["session_date_agents"], len(AUTH_CODES)))
P("")
P("Agents were never told that their briefings differed, and some DeepSeek members assumed one shared briefing. "
  "In %d of the %d K1 and K3 groups a member called a teammate's date \"fabricated\" or \"stale\" because its own "
  "prompt lacked it (%d), or took a teammate's \"my prompt has no such date\" as a sign that the teammate was "
  "unreliable (%d). A keyword search over all their messages matched %d messages, and each was read by hand. %d "
  "more groups, also DeepSeek, were borderline and not counted; the notes on all of them are in "
  "`hand_reads.json`." % (
      len(SHARED), len(K1K3_GROUPS), SHARED_KIND["called_date_fabricated"],
      SHARED_KIND["took_missing_date_as_unreliable"], TXT["shared_hit_messages_k1_k3"], len(SHARED_NC)))
P("")
P("Split (K3, T0): two informed members, two SESSION_DATE.")
P("")
rows = []
for k in ("CLOCK", "WITNESS"):
    c = "K3-%s-T0" % k
    rows.append([k, K(grp(c)), K(grp(c, "NO_MAJORITY")), K(fin(c, r="base")), K(fdate(c, r="base")),
                 K(fin(c, r="pair")), K(fdate(c, r="pair"))])
P(table(["Informed pair's evidence", "Group CLOSED", "No majority", "SESSION_DATE finals CLOSED",
         "SESSION_DATE final DATE true", "Pair finals CLOSED", "Pair final DATE true"], rows))
P("")
P("Wrong minority (K2, T0): three true clock lines, one member on a set-back machine holding the wrong date.")
P("")
rows = []
for k in KINDS:
    c = "K2-%s-T0" % k
    rows.append([k, K(grp(c)), K(fin(c, r="base")), K(fin(c, r="odd")), K(fdate(c, r="odd")),
                 K(fdate(c, "session", r="odd"))])
P(table(["Wrong member's evidence", "Group CLOSED", "Clock members' finals CLOSED", "Wrong member final CLOSED",
         "Wrong member final DATE true", "Wrong member final DATE 2026-11-14"], rows))
P("")
# ---------------------------------------------------------------- 3. checks

P("### 3. What the offered checks changed")
P("")
P("Same family and evidence across arms. In K1 every machine is healthy, so `date -u` returns the truth to "
  "anyone who asks; K1 was not run with `timewitness`. In K2 the wrong member's machine is set back, so `date "
  "-u` returns the wrong date to it, and `timewitness` returns ADRIFT.")
P("")
rows = []
for k in KINDS:
    for a in ("T0", "T1"):
        c = "K1-%s-%s" % (k, a)
        rows.append([c, CHECK[a], K(grp(c)), K(fin(c, r="base")), K(fdate(c, r="base")), K(fin(c, r="odd")),
                     K((role(c, "base")["action_run"] + role(c, "odd")["action_run"],
                        role(c, "base")["n"] + role(c, "odd")["n"])) if a != "T0" else "-"])
P(table(["Condition", "Check", "Group CLOSED", "SESSION_DATE finals CLOSED", "SESSION_DATE final DATE true",
         "Informed member final CLOSED", "Agents that ran the check"], rows))
P("")
rows = []
for k in KINDS:
    for a in ("T0", "T1", "T2"):
        c = "K2-%s-%s" % (k, a)
        rows.append([c, CHECK[a], K(grp(c)), K(fin(c, r="base")), K(fin(c, r="odd")), K(fdate(c, r="odd")),
                     K((role(c, "odd")["action_run"], role(c, "odd")["n"])) if a != "T0" else "-"])
P(table(["Condition", "Check", "Group CLOSED", "Clock members' finals CLOSED", "Wrong member final CLOSED",
         "Wrong member final DATE true", "Wrong member ran the check"], rows))
P("")
k2o = {a: pooled(K2T[a], "odd") for a in ("T0", "T1", "T2")}
P("Pooled over the three kinds of wrong evidence, the wrong member ended CLOSED in %s (no check), %s (`date -u`) "
  "and %s (`timewitness`), and believed the true date in %s, %s and %s." % (
      K(k2o["T0"]), K(k2o["T1"]), K(k2o["T2"]), K(odd_t["T0"]), K(odd_t["T1"]), K(odd_t["T2"])))
P("")
# members who ran date -u on a set-back machine
sb_t1 = [m for g in G if g["arm"] == "T1" for m in g["members"] if m["machine"] == "setback" and m["action_run"]]
sb_t2 = [m for g in G if g["arm"] == "T2" for m in g["members"] if m["machine"] == "setback" and m["action_run"]]
P("Across every condition, agents on set-back machines that ran `date -u` ended believing the true date in %s; "
  "those that ran `timewitness` in %s." % (K(count(sb_t1, dtrue)), K(count(sb_t2, dtrue))))
P("")

# ---------------------------------------------------------------- 4. wrong majority

P("### 4. The wrong-majority case (K2m)")
P("")
P("Three members sit on set-back machines whose clock lines read Saturday 14 November; one healthy member's "
  "clock line reads Monday 23 November. Nothing in the briefings says which clock is right.")
P("")
rows = []
for a in ("T0", "T1", "T2"):
    c = "K2m-" + a
    rows.append([c, CHECK[a], K(grp(c)), K(grp(c, "OPEN")), K(grp(c, "CANNOT_TELL")), K(grp(c, "NO_MAJORITY")),
                 K(fin(c, r="base")), K(fdate(c, r="base")), K(fin(c, r="odd")), K(fin(c, "OPEN", r="odd"))])
P(table(["Condition", "Check", "Group CLOSED", "Group OPEN", "Group CANNOT_TELL", "No majority",
         "Set-back members final CLOSED", "Set-back members final DATE true", "Healthy member final CLOSED",
         "Healthy member final OPEN"], rows))
P("")
# ---------------------------------------------------------------- 5. communication and consensus

P("### 5. Passing results on, and agreement")
P("")


def step_sum(cids, step):
    a = [BC[c]["all"]["steps"][step] for c in cids]
    return {k: sum(x[k] for x in a) for k in ("changed", "of", "toward_closed", "away_from_closed")}


TCELLS = [c for c in S["conditions"] if arm(c) in ("T1", "T2")]
T0CELLS = [c for c in S["conditions"] if arm(c) == "T0" and not c.startswith("K0")]
upt1 = count([m for g in G if g["arm"] == "T1" for m in g["members"]], lambda m: m["action_run"])
upt2 = count([m for g in G if g["arm"] == "T2" for m in g["members"]], lambda m: m["action_run"])
named = (sum(BC[c]["all"]["ran_and_named_it_in_turn2"] for c in TCELLS), sum(BC[c]["all"]["action_run"] for c in TCELLS))
norun = [m for g in G if g["arm"] in ("T1", "T2") for m in g["members"] if not m["action_run"]]
s12, s2f = step_sum(TCELLS, "t1->t2"), step_sum(TCELLS, "t2->final")
s2f0 = step_sum(T0CELLS, "t2->final")
P("- Uptake: %s agents ran `date -u` when offered it, and %s ran `timewitness`. The offer was one paragraph in "
  "the briefing and one sentence in the turn-1 prompt; a real agent may not know that a check exists." % (
      K(upt1), K(upt2)))
P("- Of the agents that ran a check, %s named it in their turn-2 message, which the others read (keyword rule; "
  "see summary.md)." % K(named))
EARLY = TXT["turn2_early_final"]
assert sorted((e["group_id"], e["seat"]) for e in EARLY) == sorted(
    (e["group_id"], e["seat"]) for e in HR["turn2_without_position"])


def alt_step(cids, step):
    """(changed, of) for a step if the early FINAL lines counted as turn-2 labels."""
    a, b = step.split("->")
    ch = of = 0
    for g in G:
        if g["condition"] not in cids:
            continue
        for m in g["members"]:
            la = m["labels"][a] or (m["t2_early_final_label"] if a == "t2" else None)
            lb = m["labels"][b] or (m["t2_early_final_label"] if b == "t2" else None)
            if la and lb:
                of += 1
                ch += la != lb
    return ch, of


alt12, alt2f, alt2f0 = alt_step(TCELLS, "t1->t2"), alt_step(TCELLS, "t2->final"), alt_step(T0CELLS, "t2->final")
assert (alt12[0], alt2f[0], alt2f0[0]) == (s12["changed"], s2f["changed"], s2f0["changed"])   # "none of these counts"
assert (alt2f[1] - s2f["of"]) + (alt2f0[1] - s2f0["of"]) == len(EARLY) and alt12[1] - s12["of"] == alt2f[1] - s2f["of"]
assert s2f["of"] == s12["of"] and alt2f[1] == alt12[1]   # one denominator per cell set, as the sentence says
assert T0CELLS == T0C
P("- Changes of label. A step counts only agents whose label parsed at both ends. The parse rule was fixed before "
  "the run: a label in turns 0 to 2 counts only from a POSITION line. The %d turn-2 messages that ended with a "
  "FINAL line a turn early therefore count as unparsed, and so does the one empty turn-2 reply. Every denominator "
  "below and in \"What this says\" follows this rule. In cells with a check, %s agents changed between turn 1 and "
  "turn 2, after their own result (%d toward CLOSED, %d away). %s changed between turn 2 and the final, after "
  "reading the others' turn-2 messages (%d toward CLOSED, %d away). In cells without a check (%s), %s changed "
  "between turn 2 and the final. Counting the %d early FINAL lines as turn-2 labels would make the denominators %d "
  "and %d and change none of these counts." % (
      len(EARLY), K((s12["changed"], s12["of"])), s12["toward_closed"], s12["away_from_closed"],
      K((s2f["changed"], s2f["of"])), s2f["toward_closed"], s2f["away_from_closed"], T0C_TEXT,
      K((s2f0["changed"], s2f0["of"])), len(EARLY), alt2f[1], alt2f0[1]))
nr_clock = [(g, m) for g, m in NORUN if m["evidence"] == "CLOCK_TRUE"]
assert len(nr_clock) + len(nr_sd) == len(NORUN) == len(norun)
assert all(m["labels"]["t0"] == "CLOSED" and m["labels"]["final"] == "CLOSED" for g, m in nr_clock)
assert len(nr_clock) + len(nr_switched) == count(norun, closed)[0]
assert all(m["labels"]["t2"] == "OPEN" for g, m in nr_switched)
assert all(mates_named(g, m) == sum(1 for x in g["members"] if x is not m and x["action_run"]) for g, m in nr_switched)
P("- Agents offered a check that did not run it: %d. Of them, %s ended CLOSED: %d held a true clock line and were "
  "CLOSED from turn 0, and %d of the %d SESSION_DATE members among them moved from OPEN to CLOSED at the final "
  "step, after every teammate that ran the check had named it in its turn-2 message. The other %d SESSION_DATE "
  "members ended OPEN." % (len(norun), K(count(norun, closed)), len(nr_clock), len(nr_switched), len(nr_sd),
                           len(nr_stayed)))
rows = []
for a in ("T0", "T1", "T2"):
    cs = [c for c in S["conditions"] if arm(c) == a and not c.startswith("K0") and not c.endswith("-rule")]
    rows.append([a, CHECK[a], ", ".join(sorted({c.rsplit("-", 1)[0] for c in cs})), K(gpooled(cs)),
                 K((sum(BC[c]["unanimous"] for c in cs), sum(BC[c]["groups"] for c in cs))),
                 K(gpooled(cs, "NO_MAJORITY"))])
P("")
P("Agreement by arm, pooled over the K1, K2, K2m and K3 cells that have that arm (rule cells left out; the "
  "families differ between arms, so read across a family in the tables above, not down this one):")
P("")
P(table(["Arm", "Check", "Families", "Group CLOSED", "Unanimous", "No majority"], rows))
P("")

# ---------------------------------------------------------------- 6. rule

P("### 6. The rule sentence")
P("")
rows = []
for c0, c1 in (("K1-CLOCK-T0", "K1-CLOCK-T0-rule"), ("K2-WITNESS-T0", "K2-WITNESS-T0-rule")):
    for c in (c0, c1):
        rows.append([c, K(grp(c)), K(fin(c, r="base")), K(fdate(c, r="base")), K(fin(c, r="odd")),
                     K(fdate(c, r="odd"))])
P(table(["Condition", "Group CLOSED", "Base finals CLOSED", "Base final DATE true", "Odd final CLOSED",
         "Odd final DATE true"], rows))
P("")
r_base = role("K1-CLOCK-T0-rule", "base")
r0_base = role("K1-CLOCK-T0", "base")
assert r_base["finals"]["CLOSED"] > r0_base["finals"]["CLOSED"] and r_base["final_date"]["true"] == 0
assert fin("K2-WITNESS-T0-rule", r="odd")[0] <= fin("K2-WITNESS-T0", r="odd")[0]
P("With the rule sentence, %s SESSION_DATE members in K1 ended CLOSED (against %s without it), yet none wrote "
  "the true date: %s wrote DATE: UNKNOWN. They followed the rule's ranking of evidence without taking the other "
  "member's date as their own. For the wrong member holding an old report (K2-WITNESS), the rule did not help: "
  "it ended CLOSED in %s with the rule and %s without. Six groups per cell." % (
      K(fin("K1-CLOCK-T0-rule", r="base")), K(fin("K1-CLOCK-T0", r="base")),
      K((r_base["final_date"]["unknown"], r_base["n"])), K(fin("K2-WITNESS-T0-rule", r="odd")),
      K(fin("K2-WITNESS-T0", r="odd"))))
P("")
assert BCM[DS]["by_role"]["base"]["final_date"]["unknown"] == r_base["final_date"]["unknown"]
P("The whole effect in K1 came from one model in two groups. Both CLOSED groups and all %d SESSION_DATE members "
  "who ended CLOSED were DeepSeek, and so were all %d who wrote DATE: UNKNOWN. Qwen and gemma SESSION_DATE members "
  "ended CLOSED in %s with the rule. In the later runs (%s) they ended CLOSED in %s. DeepSeek reached no later run "
  "of this cell, so the effect was not retested on the one model that showed it. At the group level, %s "
  "with the rule against %s without is inside noise (%s)." % (
      rule_base[0], r_base["final_date"]["unknown"], K(rule_other),
      ", ".join("%s %d group%s" % (MODEL_SHORT[m], n, "" if n == 1 else "s") for m, n in sorted(later_rule_models.items())),
      K(later_rule_base), K(rule_g), K(norule_g),
      pval("k1clock_rule_group_closed", (rule_g, norule_g), noisy=True)))
P("")

# ---------------------------------------------------------------- 7. order, seat, model

P("### 7. Option order, seat and model")
P("")
oo = S["option_order"]
P("- Option order, in the cells where no member can tell which date is right (K0a, K0n, K2m-T0, K2m-T1): with "
  "CLOSED named first, finals CLOSED %s and OPEN %s; with OPEN named first, CLOSED %s and OPEN %s." % (
      K((oo["CLOSED_FIRST"]["ambiguous_cells_final_closed"], oo["CLOSED_FIRST"]["ambiguous_cells_members"])),
      K((oo["CLOSED_FIRST"]["ambiguous_cells_final_open"], oo["CLOSED_FIRST"]["ambiguous_cells_members"])),
      K((oo["OPEN_FIRST"]["ambiguous_cells_final_closed"], oo["OPEN_FIRST"]["ambiguous_cells_members"])),
      K((oo["OPEN_FIRST"]["ambiguous_cells_final_open"], oo["OPEN_FIRST"]["ambiguous_cells_members"]))))
st = S["odd_member_seat"]
P("- Seat of the odd member (all conditions with one): final DATE equal to its own evidence " + "; ".join(
    "%s %s" % (nm[-1], K((v["odd_final_own_date"], v["odd_members"]))) for nm, v in st.items() if v["odd_members"])
  + ". Seats C and D were planned for runs 3 to 8.")
P("")
P("Group decided CLOSED, by model (%d groups per cell):" % R)
P("")
rows = []
for c in S["conditions"]:
    rows.append([c] + [K((S["by_condition_model"][c][m]["group_result"]["CLOSED"],
                          S["by_condition_model"][c][m]["groups"])) for m in S["models"]])
P(table(["Condition"] + [MODEL_SHORT[m] for m in S["models"]], rows))
P("")

# ---------------------------------------------------------------- 8. replies, parsing, hand reading

P("### 8. Replies, parse failures and what was read by hand")
P("")
P("- Messages: %d (%d agents x 4 turns). Empty: %d. Cut off at max_tokens: %d. Over 120 words: %d." % (
    O["messages"], O["n"], O["empty_replies"], O["cut_off_replies"], O["messages_over_120_words"]))
P("- Labels that did not parse: turn 0 %d, turn 1 %d, turn 2 %d, final %d. Final DATE lines that did not parse: "
  "%d. Labels found inline rather than on their own line: %d. The parse rule was fixed before the run: a label "
  "in turns 0 to 2 counts only from a POSITION line, and a final only from a FINAL line. %d of the %d unparsed "
  "turn-2 labels are messages that ended with a FINAL line a turn early (the other is the empty reply below); "
  "this README counts them as unparsed everywhere (section 5 says what counting them would change)." % (
      O["unparsed"]["t0"], O["unparsed"]["t1"], O["unparsed"]["t2"], O["unparsed"]["final"],
      O["unparsed_final_date"], sum(v for k, v in S["label_how"].items() if k.endswith(" inline")),
      len(EARLY), O["unparsed"]["t2"]))
P("- Actions found inline rather than on their own line: %s agents. Requests for an action the condition does "
  "not offer: %d. Requests for the offered action outside turn 1: %d (each told so in the next prompt, except at "
  "turn 3)." % (K((len(S["inline_action_requests"]), O["n"])), O["asked_not_offered"], O["asked_wrong_turn"]))
assert O["unparsed"]["final"] == 0 and O["unparsed_final_date"] == 0
P("- Every final label and final DATE line parsed, so no group needed reading for an unparsed final. Three other "
  "sets were read by hand instead. The %d empty replies: DeepSeek, one agent; %s. The %d turn-2 messages without a "
  "POSITION line: Qwen wrote its FINAL line a turn early. The %d turn-0 ACTION mentions: %s." % (
      O["empty_replies"], HR["empty_replies"]["finding"], len(HR["turn2_without_position"]),
      HR["turn0_inline_action_mentions"]["count"], HR["turn0_inline_action_mentions"]["finding"]))
assert len(HR["turn2_without_position"]) + 1 == O["unparsed"]["t2"]  # the third is the empty reply
assert HR["turn0_inline_action_mentions"]["count"] == len(S["inline_action_requests"]) == O["asked_wrong_turn"]
codes = [x["code"] for x in HR["talk_keyword_codes"]]
assert len(codes) == O["agents_with_talk_keyword"]
cc = {k: codes.count(k) for k in HR["code_meanings"]}
P("- Talk of tests or simulations. %d of %d agents used a keyword such as test, scenario, simulated or exercise "
  "(regex in summary.md). Read by hand: %d used the word in an everyday sense (\"the decisive test is my own "
  "clock\"); %d, all holding SESSION_DATE, called the briefing's date the ground truth of the exercise or "
  "simulation and used that to set a teammate's clock aside; %d suggested that another member's evidence, or the "
  "prompt, might be simulated or part of a test, and discounted it for that; %d quoted the closing line of a "
  "timewitness report. Codes are in `hand_reads.json`." % (
      len(codes), O["n"], cc["everyday_sense"], cc["briefing_date_is_ground_truth_of_the_exercise"],
      cc["other_evidence_may_be_simulated_or_test"], cc["quotes_timewitness_closing_line"]))
P("")

# ---------------------------------------------------------------- 9. later runs

P("### 9. Later runs (a check, not pooled)")
P("")
def models_text(counter):
    return ", ".join("%s %d" % (MODEL_SHORT[m], n) for m, n in sorted(counter.items()))


P("Some models finished more runs before the router stopped. Counting runs 1 and 2, %s groups were complete in all "
  "(%s; last run reached: %s). The later runs alone, runs %d to %d, are %d groups (%s). They lean toward Qwen, so "
  "they are not pooled with the main set. The table shows the later runs only (runs 1 and 2 left out), on the "
  "cells the results above lean on:" % (
      AC["groups"], models_text(AC["groups_by_model"]), models_text(AC["max_run_by_model"]),
      LATER_RUNS[0], LATER_RUNS[1], len(GX), models_text(LATER_BY_MODEL)))
P("")
rows = []
LX = {}
for c in ("K0n", "K0n-old", "K1-BARE-T0", "K1-CLOCK-T0", "K1-WITNESS-T0", "K1-CLOCK-T1", "K3-CLOCK-T0",
          "K3-WITNESS-T0", "K2m-T0", "K2m-T1", "K2m-T2"):
    gs = [g for g in GX if g["condition"] == c]
    ms = [m for g in gs for m in g["members"]]
    v = LX[c] = {"groups": len(gs), "closed": sum(1 for g in gs if g["group_result"] == "CLOSED"),
                 "finals": count(ms, closed), "base": count([m for m in ms if m["role"] == "base"], closed)}
    assert v["groups"] > 0, c          # every row is a check on later groups, not an empty one
    rows.append([c, v["groups"], models_text(collections.Counter(g["model"] for g in gs)),
                 K((v["closed"], v["groups"])), K(v["finals"]), K(v["base"])])
P(table(["Condition", "Later groups", "Models", "Group CLOSED", "Finals CLOSED", "Base finals CLOSED"], rows))
assert sum(LX[c]["base"][0] for c in K1T0) == 0
assert LX["K2m-T0"]["closed"] == 0 and LX["K2m-T1"]["closed"] == 0 and LX["K2m-T2"]["closed"] == LX["K2m-T2"]["groups"]
assert LX["K0n"]["finals"][0] == 0 and LX["K0n-old"]["finals"][0] > 0
assert LX["K3-WITNESS-T0"]["base"][0] > LX["K3-CLOCK-T0"]["base"][0]
assert LX["K1-CLOCK-T1"]["closed"] == LX["K1-CLOCK-T1"]["groups"]
P("")
P("On the cells in this table the later runs point the same way as the main set. They do not test the rule "
  "sentence again on DeepSeek, the only model it moved (section 6). Section 10 of `summary.md` has every complete "
  "group by cell and model, runs 1 and 2 included.")
P("")
# ---------------------------------------------------------------- what the agents saw

P("## What the agents saw")
P("")
P("All tool results were simulated: the harness returned the fixed text below. The timewitness texts were built "
  "from eight real runs of `timewitness --json`, made one after another within one minute on one Mac on "
  "2026-11-23 (trimmed copies in `measured/`): four with the clock as it is, and four under `faketime -f '-9d'`, "
  "which sets the clock nine days back for that process only. Each simulated report is one measured output with "
  "every time moved by the same amount to the scenario time, and an uptime set by the harness. From the "
  "set-back reports the `flags:` line was removed: libfaketime causes it (it names `faketime_env`, and the "
  "child `date` and new file times disagree), and a machine whose system clock is set back for every process "
  "would not show it. That exact case, a system-wide set-back, was not run. The LIVE report held by a wrong "
  "member in K2 is one of the live outputs measured on 2026-11-23, with every time moved back to 2026-11-14 "
  "10:19:52 and the real Bitcoin tip of that moment put in (fetched from mempool.space; "
  "`measured/bitcoin-2026-11-14.json`). No report was run on 14 November.")
P("")
P("Below is machine profile 0. Profiles 1 to 3 differ in offsets, Hub counts, Bitcoin times by a few seconds, "
  "and uptime; `protocol.md` shows all of them.")
P("")
for title, txt in [
        ("`date -u` on a healthy machine", run.tool_output("CHECK_CLOCK", "healthy", 0)),
        ("`date -u` on a set-back machine", run.tool_output("CHECK_CLOCK", "setback", 0)),
        ("`timewitness` on a healthy machine", run.tool_output("RUN_TIMEWITNESS", "healthy", 0)),
        ("`timewitness` on a set-back machine", run.tool_output("RUN_TIMEWITNESS", "setback", 0)),
        ("WITNESS in a briefing, true date (K1, K3)", run.report("brief_true", 0)),
        ("WITNESS in a briefing, report rebuilt to read 14 November (K2)", run.report("brief_wrong", 0))]:
    P("**%s**" % title)
    P("")
    P(fence(txt))
    P("")
P("Each result reached the agent inside its turn-2 prompt, after the listing of turn-1 messages, under the line "
  "\"%s\" (or the same for `timewitness`)." % run.TOOL_HEAD["CHECK_CLOCK"])
P("")

# ---------------------------------------------------------------- limits

assert all("DeepSeek" in m for m in S["reasoning_texts_main_set"]), S["reasoning_texts_main_set"]
import datetime as _dt
import re as _re


def _mined(txt):
    return _dt.datetime.strptime(_re.search(r"mined (\d\d:\d\d:\d\d)Z", txt).group(1), "%H:%M:%S")


def _spread(texts):
    ts = [_mined(t) for t in texts]
    return int((max(ts) - min(ts)).total_seconds())


SEAM_MAX = max(_spread([run.report("brief_true", k) for k in range(4)]),
               _spread([run.report(kind, k) for kind in ("tool_healthy", "tool_setback") for k in range(4)]))
_q = HR["bitcoin_seam"]["quoted_mined_times"]
_gaps = [_spread(["mined %sZ" % v for v in d.values()]) for d in _q.values()]
assert len(_q) == len(HR["bitcoin_seam"]["groups"]) and HR["bitcoin_seam"]["agents_remarking"] == 0
assert list(TXT["impossible_by_condition"]) == ["K2-WITNESS-T2"], list(TXT["impossible_by_condition"])
IMP = TXT["impossible_by_condition"]["K2-WITNESS-T2"]
IMP_RUNS = collections.defaultdict(list)
for _h in IMP["groups_with_hit"]:
    IMP_RUNS[_h["model"]].append(_h["run"])

P("## Limits")
P("")
for item in [
    "**Simulated tools.** No agent ran `date -u` or `timewitness`; the harness returned fixed text. Real outputs "
    "vary, and a real agent might run other commands too.",
    "**The set-back timewitness output is partly inferred.** Its network lines were measured under libfaketime; "
    "the flags line was removed by reasoning from the code, not from a measured system-wide set-back.",
    "**Three open models, no Claude.** DeepSeek-V4.1-Flash, Qwen2.5-72B-Instruct and gemma-4-31B-it, through one "
    "provider, at temperature %.1f. Claude models are not in this experiment: Claude Code puts the date of the "
    "session's start in the prompt, so a stale date cannot be staged through it in a short run. Whether the "
    "provider applies the models' "
    "own chat templates is not known; the K0 controls are the check that no hidden date reached the models." %
    run.TEMPERATURE,
    "**Small samples.** The design check raised the plan's two runs per condition and model to eight before the "
    "run. The account's credit ran out after every model had finished runs 1 and 2, so the main results rest on "
    "%d runs: %d groups per cell, the size the check warned would leave small differences inside noise. Contrasts "
    "such as 0 of 18 against 18 of 18 are clear at this size; differences of one to three groups, which include "
    "most of the comparisons between kinds of evidence, are not." % (R, GPC),
    "**The run stopped early.** The router began answering HTTP 402 (payment required) at %s UTC for every call; "
    "a single probe call later got the same answer. The planned seat rotation needed four runs, so in the main "
    "set the odd member sat only at A or B. %d groups that were under way are kept in `groups.jsonl` as "
    "\"stopped: HTTP 402\" and not scored; the later complete runs are shown apart in section 9 because they "
    "lean toward Qwen." % (S["first_402_utc"][11:16], S["groups_incomplete"]),
    ] + ([
    "**One main-set group has no row, for a reason not known.** %s with %s has no row at all for run %d, while "
    "runs %s of the same cell were started and then stopped by HTTP 402. So that cell has %d groups, not %d." % (
        MISSING[0]["condition"], MODEL_SHORT[MISSING[0]["model"]], MISSING[0]["run"],
        " and ".join(str(y["run"]) for y in MISS_LATER), GPC - 1, GPC)] if MISSING else []) + [
    "**One scenario.** One task, one nine-day gap, one deadline two and a half days past, four members, names "
    "A to D, members that are copies of one model. Other gaps, tasks and mixed-model teams were not run.",
    "**The check was offered in plain words.** The briefing named the action and the turn-1 prompt reminded the "
    "agent of it. Uptake here says what agents do when told a check exists, not whether they would find one.",
    "**Every message had to name a date.** The DATE line makes time salient in every condition alike.",
    "**The decision rule is stated** (3 of 4), which invites agents to go with the majority.",
    "**BARE carries a day only.** The remark is \"the 23rd\" or \"the 14th\", with no month or year. At turn 0, "
    "%s informed BARE members in K1-BARE-T0 and %s wrong BARE members in K2-BARE-T0 answered CANNOT_TELL, %d of "
    "those %d naming the missing month or year. BARE results mix a person as the source with missing "
    "information, so comparisons of BARE with CLOCK or WITNESS are confounded." % (
        K((b1["t0_cannot_tell"], b1["odd_members"])), K((b2["t0_cannot_tell"], b2["odd_members"])),
        b1["t0_cannot_tell_naming_month_or_year"] + b2["t0_cannot_tell_naming_month_or_year"],
        b1["t0_cannot_tell"] + b2["t0_cannot_tell"]),
    "**Briefings did not say that members' evidence differs.** Nothing told an agent that its teammates had "
    "other dates or none (a keyword check of all %d briefings found no such sentence). Some agents assumed one "
    "shared briefing and judged a teammate by it (section 2)." % TXT["briefings_read"],
    "**A seam in K2-WITNESS-T2.** The wrong member's briefing says it already ran `timewitness`, while the "
    "action is offered to everyone only at turn 1. In %s groups (%s) teammates called its turn-0 report "
    "\"impossible\" because the action could only be taken at turn 1 (keyword search, read by hand)." % (
        K((len(IMP["groups_with_hit"]), IMP["groups"])),
        "; ".join("%s, run%s %s" % (MODEL_SHORT[mdl], "" if len(rs) == 1 else "s", " and ".join(map(str, rs)))
                  for mdl, rs in sorted(IMP_RUNS.items()))),
    "**Small seams in the simulated reports.** Each measured report was moved to the scenario time on its own, "
    "so the same Bitcoin block shows mined times up to %d seconds apart between two members' reports in one "
    "group. In %d groups two members quoted the same block with mined times %d to %d seconds apart, where all "
    "four could read both; no agent remarked on it." % (SEAM_MAX, len(_q), min(_gaps), max(_gaps)),
    "**Keyword measures** (talk of tests, naming a check in turn 2) miss paraphrase; they are counts, not "
    "readings.",
    "**Hidden reasoning was stored, not read.** DeepSeek returned reasoning text with %d of its %d calls in the "
    "main set (the other two models returned none). It is kept in `groups.jsonl`; %d of those texts match the "
    "test-talk keyword rule and were not read by hand. Only the visible messages were coded." % (
        sum(S["reasoning_texts_main_set"].values()), 16 * S["by_model"][[m for m in S["models"] if "DeepSeek" in m][0]]["groups"],
        sum(S["reasoning_texts_with_talk_keyword"].values())),
]:
    P("- " + item)
P("")
# ---------------------------------------------------------------- changes after the design check

P("## Changes after the design check")
P("")
P("A first protocol (`consensus-1`) was built and its two controls run (12 groups). A design check before the "
  "full run found problems; this run uses `consensus-2`. The 12 earlier rows stay in `groups.jsonl` and are not "
  "scored. What changed:")
P("")
for item in [
    "The task said the window \"closed on\" the 20th and the options mixed a fact with an action (\"do not "
    "submit, file a late notice\"). Now it says \"closes at\", and the options only judge the window. K0n and "
    "K0n-old measure the old leak (section 1).",
    "Every message now ends with a DATE line, so a cautious CLOSED can be told apart from a belief about the date.",
    "The simulated timewitness texts were first copied from a run with the clock set back about 150 days, which "
    "printed lines a 9-day set-back would not. They are now built from runs measured with a 9-day set-back.",
    "The odd member always sat at seat B or C and CLOSED was always named first. Both are now counterbalanced.",
    "An ACTION written inside a sentence was silently ignored. It now runs, and a request that is not run is "
    "answered.",
    "Framing words differed (\"a moment ago\", \"in passing\"). Frames are now parallel.",
    "A tool result came just before the final turn, so it could not be passed on. A fourth turn was added.",
    "The two checks were described unequally; now one sentence each.",
    "Every simulated machine printed the same numbers; now four measured profiles.",
    "Two runs per cell became eight, fixed before the run; the plan's \"third run where runs disagree\" was "
    "dropped, because sampling more where results vary biases them. The account's credit ran out after two runs "
    "(see Limits).",
    "An inline POSITION or FINAL counts only at the end of a message, so a quoted label is not taken as the "
    "agent's own.",
    "The rule sentence now speaks of things an agent can see (a clock line on every message, a date written once "
    "in a briefing).",
    "CLOCK members now get the clock line at the top of every turn, as the hook delivers it, not once in the "
    "briefing.",
    "The evidence kind first called STALE is now SESSION_DATE, because STALE is a timewitness verdict.",
    "Before the full run, one group per model of K1-CLOCK-T1, K2-WITNESS-T2 and K2m-T2 was run and read. Nothing "
    "was changed after it, so those 9 groups are run 1 of their cells.",
]:
    P("- " + item)
P("")

# ---------------------------------------------------------------- cost, files, rerun

P("## Cost and calls")
P("")
P("All rows in `groups.jsonl` (both protocols, pilot included): USD %.2f by token counts and listed prices, "
  "USD %.2f by the router's own cost field. This protocol: %d calls, %d failed (the router's HTTP 402 answers in the stopped groups); %d groups "
  "complete, %d stopped. The cap for the whole experiment was USD 8.00; the run stopped on the account's credit, "
  "not on the cap." % (
      S["cost_usd_estimated_all_rows"], S["cost_usd_router_field_all_rows"], S["calls_scored_protocol"],
      S["calls_failed_scored_protocol"], S["groups_complete"], S["groups_incomplete"]))
P("")
P("## Files")
P("")
for item in [
    "`run.py`: the harness (conditions, briefings, simulated tools, router calls, budget, privacy scrub).",
    "`score.py`: parses every message and writes `summary.json` and `summary.md`, including the Fisher exact "
    "p-values and the keyword checks this README quotes.",
    "`make_readme.py`: writes this README from `summary.json`; asserts guard the sentences that state a number "
    "or a direction.",
    "`groups.jsonl`: one line per group: every message each agent saw and sent, per-call metadata, the design "
    "(seats, option order, machine profiles), cost.",
    "`protocol.md`: every briefing, turn prompt and simulated tool result (`run.py --render`).",
    "`measured/`: the eight timewitness runs and the Bitcoin data the simulated reports were built from.",
    "`hand_reads.json`: what was read by hand, and what it found.",
    "`run_context.json`: router prices and the router's Date header when they were fetched.",
]:
    P("- " + item)
P("")
P("## How to rerun")
P("")
P(fence('PY="$(head -1 "$(command -v hf)" | sed \'s/^#!//\')"   # a Python with huggingface_hub\n'
        '"$PY" -I run.py --dry-run        # what is left to run; sends nothing\n'
        '"$PY" -I run.py                  # runs every missing group (stops before USD 8.00 in total)\n'
        'python3 -I score.py\n'
        'python3 -I make_readme.py'))
P("")
P("A Hugging Face token with Inference Providers access is read in-process; it is never printed or stored.")

with open(OUT, "w") as f:
    f.write("\n".join(L) + "\n")
print("wrote", OUT)
