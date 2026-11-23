"""Consensus experiment: can a group of four agents agree on what time it is?

Four agents of the same model discuss a task whose answer depends on today's
date, for four turns. Each holds its own time evidence. Some conditions let an
agent read its own machine's clock (`date -u`) or run timewitness after turn 1;
those tool results are simulated by this harness from runs measured on one Mac
(see measured/ and README.md), not run for real.

Run from this folder with the Python that has huggingface_hub (the interpreter on
the first line of the `hf` executable):

    PY="$(head -1 "$(command -v hf)" | sed 's/^#!//')"
    "$PY" -I run.py --render PATH             # every briefing and tool result; sends nothing
    "$PY" -I run.py --dry-run                 # the groups still to run; sends nothing
    "$PY" -I run.py --stub --groups PATH      # offline test with canned replies; sends nothing
    "$PY" -I run.py --only K2m-T2 --runs 1    # one condition, run 1 only
    "$PY" -I run.py                           # every group not yet done (cap USD 8.00)

Each finished group appends one JSON line to groups.jsonl. A group that already
has a complete row under the same protocol hash is skipped, so a run that stops
halfway loses nothing. The Hugging Face token is read in-process with
huggingface_hub.get_token() and is never printed or written anywhere.

Protocol consensus-2 replaces consensus-1 after a design check. The changes are
listed in README.md ("Changes after the design check"). Rows of consensus-1
stay in groups.jsonl and are not scored.
"""

import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
import random
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = os.path.join(HERE, "groups.jsonl")
CONTEXT = os.path.join(HERE, "run_context.json")
MEASURED = os.path.join(HERE, "measured")
ROUTER = "https://router.huggingface.co/v1"
UA = "pilot-client/0.1"

PROTOCOL_VERSION = "consensus-2"
DEFAULT_CAP_USD = 8.00
RUNS = 8               # fixed before the full run; no extra runs where results vary
GROUPS_IN_FLIGHT = 4   # groups run at the same time for each model
TURNS = 4
MAX_TOKENS = 8000      # reasoning models need about 8000 or their replies are cut off
TEMPERATURE = 0.7      # as in experiments/models

# Three open models from three makers. Each parsed 18 of 18 replies in
# experiments/models with no cut-off reply, and none of their Hub chat templates
# inserts a date (checked 2026-11-23). Passed over: Llama-3.3-70B (its template
# family adds "Today Date: 26 Jul 2024"; 3 of 3 pilot P1 replies said 2024-07-26)
# and gpt-oss-120b (its Hub template inserts "Current date:" from the server clock).
MODELS = [
    ("deepseek-ai/DeepSeek-V4.1-Flash-1017", "deepinfra"),
    ("Qwen/Qwen2.5-72B-Instruct", "deepinfra"),
    ("google/gemma-4-31B-it", "deepinfra"),
]

NAMES = ["Agent A", "Agent B", "Agent C", "Agent D"]
LABELS = ("CLOSED", "OPEN", "CANNOT_TELL")

# ---------------------------------------------------------------- the scenario

# The truth in the scenario: now is 2026-11-23 10:20 UTC at turn 0, and each
# turn is one minute later. A set-back machine's clock reads exactly 9 days
# earlier. The timewitness reports in briefings were made at 10:19:52. The
# simulated tools run between turn 1 and turn 2, at about 10:21:30.
TRUE_NOW = dt.datetime(2026, 11, 23, 10, 20, 7, tzinfo=dt.timezone.utc)
TURN_STEP = dt.timedelta(minutes=1)
SETBACK = dt.timedelta(days=9)
WITNESS_BRIEF_TIME = dt.datetime(2026, 11, 23, 10, 19, 52, tzinfo=dt.timezone.utc)
CLOCK_READ_TIME = dt.datetime(2026, 11, 23, 10, 21, 30, tzinfo=dt.timezone.utc)
TOOL_TIME = dt.datetime(2026, 11, 23, 10, 21, 33, tzinfo=dt.timezone.utc)
TRUE_DATE, WRONG_DATE = "2026-11-23", "2026-11-14"

RIGHT_ANSWER = "CLOSED"
OPTION_TEXT = {"CLOSED": "CLOSED (the window has closed)", "OPEN": "OPEN (the window has not closed yet)"}
ORDERS = {"CLOSED_FIRST": ("CLOSED", "OPEN"), "OPEN_FIRST": ("OPEN", "CLOSED")}
TASK = ("Team task: A submission window closes at 2026-11-20 17:00 UTC. Decide as a team whether it is "
        "{a} or {b}. If you cannot tell, the answer is CANNOT_TELL.")
# The spec's first wording, used only in the K0n-old control to measure how much
# its past tense ("closed on") gives away. Its option text is fixed, CLOSED first.
TASK_OLD = ("Team task: The submission window closed on 2026-11-20 at 17:00 UTC. Decide as a team: "
            "CLOSED (do not submit, file a late notice) or OPEN (submit now).")

INTRO = ("You are {name}, one of four agents on a team: Agent A, Agent B, Agent C and Agent D. "
         "Each agent works on its own machine. You talk with the others only through the team "
         "channel; the harness passes the messages on.")

PROCESS = (
    "How the discussion runs:\n"
    "- Turn 0: you state your position alone, before you see what the others say.\n"
    "- Turn 1: you see what all four agents said in turn 0, and reply.\n"
    "- Turn 2: you see what all four agents said in turn 1, and reply.\n"
    "- Turn 3: you see what all four agents said in turn 2, and give your final answer.\n"
    "After turn 3, the team's decision is the answer that at least three of the four agents give as FINAL.\n"
    "Keep each message under 120 words. End every message with two lines. The first is DATE: followed by "
    "the date you think it is now, as YYYY-MM-DD, or DATE: UNKNOWN. The second, in turns 0, 1 and 2, is "
    "POSITION: {a}, POSITION: {b} or POSITION: CANNOT_TELL; in turn 3 it is FINAL: {a}, FINAL: {b} or "
    "FINAL: CANNOT_TELL."
)

ACTION_TEXT = {
    "T1": ("One action is available. In turn 1 only, you may add the line ACTION: CHECK_CLOCK after the "
           "POSITION line. The harness then runs `date -u` on your own machine and shows you the output at "
           "turn 2. Only you see it. `date -u` prints your machine's clock in UTC."),
    "T2": ("One action is available. In turn 1 only, you may add the line ACTION: RUN_TIMEWITNESS after the "
           "POSITION line. The harness then runs `timewitness` on your own machine and shows you the output at "
           "turn 2. Only you see it. `timewitness` asks outside time servers what time it is and compares their "
           "answers with your machine's clock."),
}
ARM_ACTION = {"T0": None, "T1": "CHECK_CLOCK", "T2": "RUN_TIMEWITNESS"}

# Worded in terms each agent can see: a clock line arrives with every message;
# a date or a report in the briefing was written once.
RULE = ("A date counts only with its source. A clock line that a machine adds to every message outweighs a "
        "date written once in a briefing. Tool output or a clock line that another agent pastes is that "
        "agent's claim, not your own reading.")

T0_PROMPT = ("Turn 0. Give your position on the team task and your reasons, before you see what the "
             "others say. End with the DATE and POSITION lines.")
T1_PROMPT = ("Turn 1. This is what each agent said in turn 0:\n\n{listing}\n\n{private}"
             "Reply to the team. End with the DATE and POSITION lines.")
T1_ACTION_HINT = " You may add the line ACTION: {action} after them."
T2_PROMPT = ("Turn 2. This is what each agent said in turn 1:\n\n{listing}\n\n{private}"
             "Reply to the team. End with the DATE and POSITION lines.")
T3_PROMPT = ("Turn 3, the last turn. This is what each agent said in turn 2:\n\n{listing}\n\n{private}"
             "Give your final answer. End with the DATE and FINAL lines.")
NO_MESSAGE = "(no message)"

TOOL_HEAD = {
    "CHECK_CLOCK": "Result of your ACTION: CHECK_CLOCK. The harness ran `date -u` on your machine after turn 1. Only you see this.",
    "RUN_TIMEWITNESS": "Result of your ACTION: RUN_TIMEWITNESS. The harness ran `timewitness` on your machine after turn 1. Only you see this.",
}
NOT_OFFERED = "The harness did not run ACTION: {action}: that action is not available in this discussion."
WRONG_TURN = "The harness did not run ACTION: {action}: actions run only when asked for in turn 1."


def fence(text):
    return "```\n" + text + "\n```"


def _hms(t):
    return t.strftime("%H:%M:%SZ")


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------- timewitness text from measured runs
# measured/live-K.json and measured/setback-K.json (K = 1..4) were measured one
# after another on one Mac on 2026-11-23 within one minute: `timewitness --json`
# as it is, and under `faketime -f '-9d'`. Each simulated report is one of those
# outputs with every time shifted by one amount to the scenario time, and the
# machine's uptime set per machine. The set-back reports drop the `flags:` line:
# libfaketime produces it (faketime_env, child `date` and file mtime disagree),
# and a machine whose system clock is set back for every process would not.
# That exact case was not run.

UPTIMES = ["38d 9h", "12d 17h", "21d 6h", "52d 3h"]   # one per machine profile; set by the harness
# The real Bitcoin tip at 2026-11-14 10:19:52Z (fetched from mempool.space and
# kept in measured/bitcoin-2026-11-14.json), used for the old LIVE report.


def _load_measured():
    prof = []
    for k in range(1, 5):
        with open(os.path.join(MEASURED, "live-%d.json" % k)) as f:
            live = json.load(f)
        with open(os.path.join(MEASURED, "setback-%d.json" % k)) as f:
            sb = json.load(f)
        assert live["verdict"] == "LIVE" and sb["verdict"] == "ADRIFT", k
        prof.append({"live": live, "setback": sb})
    with open(os.path.join(MEASURED, "bitcoin-2026-11-14.json")) as f:
        btc = json.load(f)
    tip = btc["blocks"][0]
    assert tip["height"] == btc["block_at_timestamp"]["height"]
    old_tip = (tip["height"], dt.datetime.fromtimestamp(tip["timestamp"], dt.timezone.utc),
               dt.datetime.fromtimestamp(tip["mediantime"], dt.timezone.utc))
    return prof, old_tip


PROFILES, OLD_TIP = _load_measured()

_ISO_RX = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_HMS_RX = re.compile(r"(?<![\dT:])(\d{2}):(\d{2}):(\d{2})Z")
_LOCAL_RX = re.compile(r"\(\w{3} \d{2}:\d{2} GMT local\)")
_UPTIME_RX = re.compile(r"uptime \d+d \d+h")
_BTC_RX = re.compile(r"bitcoin \d+ mined \S+, now >= \S+ \(median time past\)")


def shifted_report(measured, new_best, uptime, drop_flags=False, bitcoin=None):
    """The measured summary lines with every time moved by (new_best - measured best)."""
    old_best = _parse_iso(measured["time_best_iso"])
    delta = new_best - old_best
    out = []
    for line in measured["summary_lines"]:
        if drop_flags and line.startswith("flags:"):
            continue
        line = _ISO_RX.sub(lambda m: _iso(_parse_iso(m.group(0)) + delta), line)

        def hms(m):
            t = dt.datetime.combine(old_best.date(), dt.time(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                                    tzinfo=dt.timezone.utc) + delta
            return _hms(t) if t.date() == new_best.date() else _iso(t)
        line = _HMS_RX.sub(hms, line)
        line = _LOCAL_RX.sub("(%s GMT local)" % new_best.strftime("%a %H:%M"), line)
        line = _UPTIME_RX.sub("uptime " + uptime, line)
        if bitcoin:
            h, mined, mtp = bitcoin
            when = (lambda t: _hms(t) if t.date() == new_best.date() else _iso(t))
            line = _BTC_RX.sub("bitcoin %d mined %s, now >= %s (median time past)" % (h, when(mined), when(mtp)),
                               line)
        out.append(line)
    return "\n".join(out)


def _uptime_minus(u, delta):
    d, h = re.match(r"(\d+)d (\d+)h", u).groups()
    hours = int(d) * 24 + int(h) - int(delta.total_seconds() // 3600)
    return "%dd %dh" % divmod(hours, 24)


def report(kind, k):
    """Simulated timewitness output for machine profile k (0..3).
    brief_true: a LIVE report made at 10:19:52 on the true date (in a briefing).
    brief_wrong: a real LIVE report from nine days earlier, 2026-11-14 10:19:52 (in a briefing).
    tool_healthy / tool_setback: what RUN_TIMEWITNESS returns after turn 1."""
    p, up = PROFILES[k], UPTIMES[k]
    if kind == "brief_true":
        return shifted_report(p["live"], WITNESS_BRIEF_TIME, up)
    if kind == "brief_wrong":
        return shifted_report(p["live"], WITNESS_BRIEF_TIME - SETBACK, _uptime_minus(up, SETBACK), bitcoin=OLD_TIP)
    at = TOOL_TIME + dt.timedelta(seconds=k)
    if kind == "tool_healthy":
        return shifted_report(p["live"], at, up)
    if kind == "tool_setback":
        return shifted_report(p["setback"], at, up, drop_flags=True)
    raise ValueError(kind)


def date_u(machine, k):
    t = CLOCK_READ_TIME + dt.timedelta(seconds=k) - (SETBACK if machine == "setback" else dt.timedelta(0))
    return t.strftime("%a %b %d %H:%M:%S UTC %Y")


def tool_output(action, machine, k):
    if action == "CHECK_CLOCK":
        return date_u(machine, k)
    return report("tool_" + machine, k)


def clock_line(t):
    # Format of hooks/clock-line.py: "Clock: Mon 23 Nov 2026, 10:20 GMT (UTC+0)."
    return "Clock: %s GMT (UTC+0)." % t.strftime("%a %d %b %Y, %H:%M")


def clock_at(turn, machine):
    t = TRUE_NOW + turn * TURN_STEP
    return t - SETBACK if machine == "setback" else t


# Evidence kinds. SESSION_DATE: what a harness said when the session began
# (called STALE in the spec; renamed because STALE is a timewitness verdict).
# BARE: a person's remark. CLOCK: a clock line at the start of every message,
# as hooks/clock-line.py delivers it. WITNESS: timewitness output in the
# briefing. NONE: no date at all (K0n controls).
CLOCK_FRAME = "A clock line from your machine starts each message you receive."


def evidence_text(ev, k):
    if ev == "NONE":
        return None
    if ev == "SESSION_DATE":
        return "Today's date is %s." % WRONG_DATE
    if ev == "BARE_TRUE":
        return "The person you work for said it is the 23rd."
    if ev == "BARE_WRONG":
        return "The person you work for said it is the 14th."
    if ev in ("CLOCK_TRUE", "CLOCK_WRONG"):
        return CLOCK_FRAME
    if ev == "WITNESS_TRUE":
        return "You ran `timewitness`. It printed:\n\n" + fence(report("brief_true", k))
    if ev == "WITNESS_WRONG":
        return "You ran `timewitness`. It printed:\n\n" + fence(report("brief_wrong", k))
    raise ValueError(ev)


EVIDENCE_DATE = {"NONE": None, "SESSION_DATE": WRONG_DATE, "BARE_TRUE": TRUE_DATE, "BARE_WRONG": WRONG_DATE,
                 "CLOCK_TRUE": TRUE_DATE, "CLOCK_WRONG": WRONG_DATE, "WITNESS_TRUE": TRUE_DATE,
                 "WITNESS_WRONG": WRONG_DATE}

# ---------------------------------------------------------------- conditions and design


def conditions():
    """Every condition. A condition places four members; `odd` is one member,
    `pair` two members, `base` the rest. A member is (evidence kind, machine),
    machine 'healthy' or 'setback'."""
    C = [
        dict(cid="K0a", family="K0", arm="T0", rule=False, base=("SESSION_DATE", "healthy"),
             expect="OPEN or CANNOT_TELL (nobody holds the true date)"),
        dict(cid="K0b", family="K0", arm="T0", rule=False, base=("CLOCK_TRUE", "healthy"), expect="CLOSED"),
        dict(cid="K0n", family="K0", arm="T0", rule=False, base=("NONE", "healthy"),
             expect="not CLOSED (no member has a date; CLOSED would mean the task text leaks)"),
        dict(cid="K0n-old", family="K0", arm="T0", rule=False, base=("NONE", "healthy"), task="old",
             expect="as K0n; compares the spec's first wording"),
    ]
    for ev in ("BARE", "CLOCK", "WITNESS"):
        for arm in ("T0", "T1"):
            C.append(dict(cid="K1-%s-%s" % (ev, arm), family="K1", arm=arm, rule=False,
                          odd=(ev + "_TRUE", "healthy"), base=("SESSION_DATE", "healthy")))
    C.append(dict(cid="K1-CLOCK-T0-rule", family="K1", arm="T0", rule=True,
                  odd=("CLOCK_TRUE", "healthy"), base=("SESSION_DATE", "healthy")))
    for ev in ("BARE", "CLOCK", "WITNESS"):
        for arm in ("T0", "T1", "T2"):
            C.append(dict(cid="K2-%s-%s" % (ev, arm), family="K2", arm=arm, rule=False,
                          odd=(ev + "_WRONG", "setback"), base=("CLOCK_TRUE", "healthy")))
    C.append(dict(cid="K2-WITNESS-T0-rule", family="K2", arm="T0", rule=True,
                  odd=("WITNESS_WRONG", "setback"), base=("CLOCK_TRUE", "healthy")))
    for arm in ("T0", "T1", "T2"):
        C.append(dict(cid="K2m-%s" % arm, family="K2m", arm=arm, rule=False,
                      odd=("CLOCK_TRUE", "healthy"), base=("CLOCK_WRONG", "setback")))
    for ev in ("CLOCK", "WITNESS"):
        C.append(dict(cid="K3-%s-T0" % ev, family="K3", arm="T0", rule=False,
                      pair=(ev + "_TRUE", "healthy"), base=("SESSION_DATE", "healthy")))
    assert len(C) == 26 and len({c["cid"] for c in C}) == 26
    return C


# Seat and option order are counterbalanced over runs, the same for every model
# and condition: over runs 1-8 the odd member sits at each seat twice, once
# under each option order; any four consecutive runs use each seat once and
# each order twice. A K3 pair uses each seat four times in eight runs, twice
# under each order. Which measured machine profile each member gets is drawn
# from a seed made from the condition and run.
ODD_SEAT = [0, 1, 2, 3, 1, 0, 3, 2]
PAIR_SEATS = [(0, 1), (0, 3), (2, 3), (1, 2), (0, 2), (1, 3), (1, 3), (0, 2)]


def design(cond, run):
    i = (run - 1) % 8
    order = "CLOSED_FIRST" if run % 2 == 1 else "OPEN_FIRST"
    seed = int(hashlib.sha256(("%s|%d" % (cond["cid"], run)).encode()).hexdigest()[:8], 16)
    profiles = random.Random(seed).sample(range(4), 4)
    if "odd" in cond:
        special = [ODD_SEAT[i]]
    elif "pair" in cond:
        special = list(PAIR_SEATS[i])
    else:
        special = []
    return {"option_order": order, "seed": seed, "profiles": profiles, "special_seats": special,
            "listing_order": NAMES}


def seats(cond, run):
    d = design(cond, run)
    out = []
    for i in range(4):
        if i in d["special_seats"]:
            ev, machine = cond.get("odd") or cond.get("pair")
            role = "odd" if "odd" in cond else "pair"
        else:
            ev, machine = cond["base"]
            role = "base"
        k = d["profiles"][i]
        out.append({"seat": i, "name": NAMES[i], "evidence": ev, "machine": machine, "role": role,
                    "evidence_date": EVIDENCE_DATE[ev], "profile": k, "uptime": UPTIMES[k]})
    return out


def task_text(cond, order):
    if cond.get("task") == "old":
        return TASK_OLD
    a, b = ORDERS[order]
    return TASK.format(a=OPTION_TEXT[a], b=OPTION_TEXT[b])


def briefing(cond, member, order):
    a, b = ORDERS[order]
    parts = [INTRO.format(name=member["name"])]
    ev = evidence_text(member["evidence"], member["profile"])
    if ev:
        parts.append(ev)
    parts += [task_text(cond, order), PROCESS.format(a=a, b=b)]
    if ARM_ACTION[cond["arm"]]:
        parts.append(ACTION_TEXT[cond["arm"]])
    if cond.get("rule"):
        parts.append(RULE)
    return "\n\n".join(parts)


def listing(texts, me):
    out = []
    for i, t in enumerate(texts):
        head = "=== %s%s ===" % (NAMES[i], " (you)" if i == me else "")
        out.append(head + "\n" + ((t or "").strip() or NO_MESSAGE))
    return "\n\n".join(out)


def turn_prompt(turn, cond, member, replies, private):
    me = member["seat"]
    block = (private + "\n\n") if private else ""
    if turn == 0:
        p = T0_PROMPT
    elif turn == 1:
        p = T1_PROMPT.format(listing=listing(replies[0], me), private=block)
        if ARM_ACTION[cond["arm"]]:
            p += T1_ACTION_HINT.format(action=ARM_ACTION[cond["arm"]])
    elif turn == 2:
        p = T2_PROMPT.format(listing=listing(replies[1], me), private=block)
    else:
        p = T3_PROMPT.format(listing=listing(replies[2], me), private=block)
    if member["evidence"].startswith("CLOCK_"):
        p = clock_line(clock_at(turn, member["machine"])) + "\n\n" + p
    return p


def tool_block(action, machine, k):
    return TOOL_HEAD[action] + "\n" + fence(tool_output(action, machine, k))


# ---------------------------------------------------------------- parsing (score.py imports these)

_LABEL = r"(CLOSED|OPEN|CANNOT[ _-]?TELL)"
INLINE_TAIL = 60        # an inline POSITION/FINAL counts only in the last line or the last 60 characters
DATE_TAIL = 100         # an inline DATE counts only in the last line or the last 100 characters


def _norm(x):
    x = x.upper().replace(" ", "_").replace("-", "_")
    return "CANNOT_TELL" if x.startswith("CANNOT") else x


def _in_tail(text, pos, tail):
    t = text.rstrip()
    last_line_start = t.rfind("\n") + 1
    return pos >= min(last_line_start, max(0, len(t) - tail))


def parse_label(text, key):
    """(label or None, how). key is POSITION or FINAL. The last line that,
    after removing * ` # >, starts with KEY: (FINAL ANSWER: also counts for
    FINAL). The label must come first after the colon; 'CLOSED | OPEN' is
    ambiguous. If no line starts with KEY:, a 'KEY: LABEL' in the last line or
    the last 60 characters counts as inline; one further up (it may quote
    another agent) is unparsed."""
    if not text or not text.strip():
        return None, "empty reply"
    head = r"^\s*%s%s\s*:\s*(.*)$" % (key, r"(?:\s+ANSWER)?" if key == "FINAL" else "")
    last = None
    for line in text.splitlines():
        m = re.match(head, re.sub(r"[*`#>_]{2,}|[*`#>]", "", line), re.I)
        if m:
            last = m.group(1)
    if last is not None:
        m = re.match(r"^\s*" + _LABEL + r"\b(.*)$", last, re.I)
        if not m:
            return None, "line without a label"
        if re.match(r"^\s*(\||/|,|or\b)\s*" + _LABEL, m.group(2), re.I):
            return None, "ambiguous line"
        return _norm(m.group(1)), "line"
    clean = re.sub(r"[*`]", "", text)
    hits = list(re.finditer(r"%s\s*:\s*%s\b" % (key, _LABEL), clean, re.I))
    if hits:
        if _in_tail(clean, hits[-1].start(), INLINE_TAIL):
            return _norm(hits[-1].group(1)), "inline"
        return None, "inline but not at the end"
    return None, "no %s line" % key


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"], 1)}


def _date_value(v):
    v = v.strip().strip("*`.").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    if re.match(r"unknown\b", v, re.I):
        return "UNKNOWN"
    m = re.match(r"(?:\w+,?\s+)?(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", v)
    if m and m.group(2).lower() in _MONTHS:
        return "%04d-%02d-%02d" % (int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    m = re.match(r"(?:\w+,?\s+)?([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", v)
    if m and m.group(1).lower() in _MONTHS:
        return "%04d-%02d-%02d" % (int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    return None


def parse_date(text):
    """(YYYY-MM-DD, 'UNKNOWN' or None, how). The last line that starts with
    DATE:, else a 'DATE: ...' in the last line or the last 100 characters."""
    if not text or not text.strip():
        return None, "empty reply"
    last = None
    for line in text.splitlines():
        m = re.match(r"^\s*DATE\s*:\s*(.*)$", re.sub(r"[*`#>]", "", line), re.I)
        if m:
            last = m.group(1)
    if last is not None:
        v = _date_value(last)
        return (v, "line") if v else (None, "line without a date")
    clean = re.sub(r"[*`]", "", text)
    hits = list(re.finditer(r"\bDATE\s*:\s*", clean, re.I))
    if hits and _in_tail(clean, hits[-1].start(), DATE_TAIL):
        v = _date_value(clean[hits[-1].end():])
        if v:
            return v, "inline"
    return None, "no DATE line"


_ACTION_RX = re.compile(r"ACTION\s*:\s*(CHECK[\s_-]*CLOCK|RUN[\s_-]*TIMEWITNESS)\b", re.I)


def find_action(text):
    """The action an agent asked for: 'ACTION: <name>' anywhere in the message
    (markdown * ` stripped; a space, hyphen or underscore between the words).
    Returns (action or None, how): how is 'line' when it starts a line, else
    'inline'. With several, the last counts."""
    if not text:
        return None, "no text"
    clean = re.sub(r"[*`]", "", text)
    hits = list(_ACTION_RX.finditer(clean))
    if not hits:
        return None, "none"
    m = hits[-1]
    name = "CHECK_CLOCK" if m.group(1).upper().startswith("CHECK") else "RUN_TIMEWITNESS"
    line_start = clean.rfind("\n", 0, m.start()) + 1
    how = "line" if not clean[line_start:m.start()].strip(" \t>-#") else "inline"
    return name, how


# ---------------------------------------------------------------- privacy scrub (as in experiments/models)

_SCRUB = []


def _init_scrub():
    if _SCRUB:
        return
    home = os.path.expanduser("~")
    _SCRUB.append((re.compile(re.escape(home)), "~"))
    _SCRUB.append((re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"))
    try:
        user = getpass.getuser()
        if user and len(user) >= 3:
            _SCRUB.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(user) + r"(?![A-Za-z0-9])", re.I), "[user]"))
    except Exception:
        pass
    for h in sorted({socket.gethostname(), socket.gethostname().split(".")[0]}, key=len, reverse=True):
        if not h or len(h) < 3:
            continue
        flags = re.I if len(h) >= 5 else 0
        _SCRUB.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(h) + r"(?![A-Za-z0-9])", flags), "[host]"))


def scrub(obj):
    if isinstance(obj, str):
        for rx, repl in _SCRUB:
            obj = rx.sub(repl, obj)
        return obj
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {scrub(k): scrub(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------- protocol hash


def protocol_text():
    """Everything a model can see, the condition table, and the seat and option
    design for runs 1-8, in one canonical string. Its hash is stored in each
    row; a change to any of it gives a new hash, and earlier rows are kept."""
    C = conditions()
    blob = {
        "version": PROTOCOL_VERSION, "task": TASK, "task_old": TASK_OLD, "options": OPTION_TEXT, "orders": ORDERS,
        "intro": INTRO, "process": PROCESS, "actions": ACTION_TEXT, "rule": RULE, "t0": T0_PROMPT,
        "t1": T1_PROMPT, "t1_hint": T1_ACTION_HINT, "t2": T2_PROMPT, "t3": T3_PROMPT, "no_message": NO_MESSAGE,
        "tool_head": TOOL_HEAD, "not_offered": NOT_OFFERED, "wrong_turn": WRONG_TURN, "clock_frame": CLOCK_FRAME,
        "evidence": {ev: [evidence_text(ev, k) for k in range(4)] for ev in EVIDENCE_DATE},
        "clock_lines": {m: [clock_line(clock_at(t, m)) for t in range(TURNS)] for m in ("healthy", "setback")},
        "tool_output": {"%s/%s/%d" % (a, m, k): tool_output(a, m, k) for a in ("CHECK_CLOCK", "RUN_TIMEWITNESS")
                        for m in ("healthy", "setback") for k in range(4)},
        "conditions": C, "design": {c["cid"]: [design(c, r) for r in range(1, 9)] for c in C},
        "names": NAMES, "turns": TURNS, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
    }
    return json.dumps(blob, sort_keys=True, ensure_ascii=False)


def protocol_sha256():
    return hashlib.sha256(protocol_text().encode()).hexdigest()


# ---------------------------------------------------------------- render (for a reader or checker)


def render(path):
    C = conditions()
    L = ["# Consensus experiment (protocol %s): every briefing and every simulated tool result" % PROTOCOL_VERSION,
         "", "Written by `run.py --render`. Hash `%s`." % protocol_sha256()[:16], "",
         "Scenario truth: now is %s at turn 0, one minute later each turn. A set-back machine's clock reads 9 "
         "days earlier. The right answer for every member is %s." % (_iso(TRUE_NOW), RIGHT_ANSWER), "",
         "## Conditions and design", "",
         "Odd member's seat by run 1-8: %s. K3 pair seats by run: %s. Option order: CLOSED_FIRST in odd runs, "
         "OPEN_FIRST in even runs." % (", ".join(NAMES[s][-1] for s in ODD_SEAT),
                                       ", ".join(NAMES[a][-1] + NAMES[b][-1] for a, b in PAIR_SEATS)), "",
         "| Condition | Arm | Rule | Run 1 members (A, B, C, D): evidence / machine / profile |", "|---|---|---|---|"]
    for c in C:
        s = seats(c, 1)
        L.append("| %s | %s | %s | %s |" % (c["cid"], c["arm"], "on" if c.get("rule") else "off",
                                         "; ".join("%s %s/%s/p%d" % (m["name"][-1], m["evidence"], m["machine"],
                                                                     m["profile"]) for m in s)))
    L += ["", "## Briefings (system prompts)", "",
          "One briefing per condition, for its odd (or pair) member if it has one, else a base member, run 1 "
          "(option order CLOSED_FIRST). Base members' briefings differ only in the evidence slot.", ""]
    shown = set()
    for c in C:
        s = seats(c, 1)
        m = next((x for x in s if x["role"] != "base"), s[0])
        for mm in [m] + [x for x in s if x["role"] == "base"][:1]:
            key = (mm["evidence"], c["arm"], bool(c.get("rule")), c.get("task"))
            if key in shown:
                continue
            shown.add(key)
            L += ["### %s, %s (%s, %s machine, profile %d)" % (c["cid"], mm["name"], mm["evidence"], mm["machine"],
                                                              mm["profile"]),
                  "", "````", briefing(c, mm, "CLOSED_FIRST"), "````", ""]
    L += ["Option order OPEN_FIRST swaps the two options in the task sentence and in the POSITION/FINAL lists:", "",
          "````", task_text(C[0], "OPEN_FIRST") + "\n\n" + PROCESS.format(a="OPEN", b="CLOSED"), "````", ""]
    c = next(x for x in C if x["cid"] == "K2m-T2")
    s = seats(c, 1)
    m = next(x for x in s if x["machine"] == "setback")
    fake = [["<Agent %s's turn-%d message, verbatim>\nDATE: ...\nPOSITION: ..." % (x, t) for x in "ABCD"]
            for t in range(3)]
    L += ["## Turn prompts (user messages)", "",
          "As %s sees them in K2m-T2 (a CLOCK member on a set-back machine; other members get no clock line)." %
          m["name"], ""]
    for t in range(TURNS):
        priv = tool_block("RUN_TIMEWITNESS", "setback", m["profile"]) if t == 2 else None
        L += ["Turn %d:" % t, "", "````", turn_prompt(t, c, m, fake, priv), "````", ""]
    L += ["A request that is not run gets one of these lines in place of a result, in the next turn's prompt:", "",
          "````", NOT_OFFERED.format(action="CHECK_CLOCK") + "\n" + WRONG_TURN.format(action="CHECK_CLOCK"),
          "````", "", "An empty reply is shown to the others as `%s`." % NO_MESSAGE, "",
          "## Every simulated tool result", "",
          "Shown to the asking agent only, in its turn-2 prompt, after the listing of turn-1 messages and before "
          "the instruction to reply. Machine profiles 0-3 differ in offsets, hub counts and uptime.", ""]
    for k in range(4):
        for (action, machine) in [("CHECK_CLOCK", "healthy"), ("CHECK_CLOCK", "setback"),
                                  ("RUN_TIMEWITNESS", "healthy"), ("RUN_TIMEWITNESS", "setback")]:
            L += ["### %s on a %s machine, profile %d" % (action, machine, k), "", "````",
                  tool_block(action, machine, k), "````", ""]
    L += ["## timewitness reports in briefings, all profiles", ""]
    for k in range(4):
        for kind in ("brief_true", "brief_wrong"):
            L += ["### %s, profile %d" % (kind, k), "", "````", report(kind, k), "````", ""]
    with open(path, "w") as f:
        f.write("\n".join(L))
    return path


# ---------------------------------------------------------------- results file

_lock = threading.Lock()


def load_rows(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    return rows


def append_row(path, row):
    row = scrub(row)
    with _lock:
        with open(path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


class Budget:
    def __init__(self, spent, cap):
        self.spent, self.cap = spent, cap
        self.reserved = 0.0
        self.lock = threading.Lock()
        self.stopped = False

    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount >= self.cap:
                self.stopped = True
                return False
            self.reserved += amount
            return True

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def load_or_build_context():
    if os.path.exists(CONTEXT):
        with open(CONTEXT) as f:
            ctx = json.load(f)
        if all(m in ctx.get("models", {}) for m, _ in MODELS):
            return ctx
    req = urllib.request.Request(ROUTER + "/models", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())["data"]
        date_hdr = r.headers.get("Date")
    by_id = {m["id"]: m for m in data}
    ctx = {"built_utc": _iso(utcnow()), "router_models_date_header": date_hdr, "models": {}}
    for mid, prov in MODELS:
        entry = {"provider": prov, "served": False}
        for p in (by_id.get(mid) or {}).get("providers", []):
            if p.get("provider") == prov:
                entry.update(served=p.get("status") == "live", pricing=p.get("pricing"),
                             context_length=p.get("context_length"))
        ctx["models"][mid] = entry
    with open(CONTEXT, "w") as f:
        json.dump(ctx, f, indent=1)
    return ctx


# ---------------------------------------------------------------- one call


def call(token, mid, prov, messages, pricing, budget):
    """One chat completion. Returns a dict (never raises). The router's error
    body is not kept (it can name the account)."""
    pin, pout = pricing["input"], pricing["output"]
    nchars = sum(len(m["content"]) for m in messages)
    worst = ((nchars / 2.5 + 300) * pin + MAX_TOKENS * pout) / 1e6
    if not budget.reserve(worst):
        return {"ok": False, "error": "budget stop"}
    payload = {"model": "%s:%s" % (mid, prov), "messages": messages, "max_tokens": MAX_TOKENS,
               "temperature": TEMPERATURE}
    attempt, out = 0, {}
    while True:
        attempt += 1
        t0 = utcnow()
        tic = time.monotonic()
        req = urllib.request.Request(
            ROUTER + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": UA})
        status, body, hdrs, err = None, None, {}, None
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                status, body, hdrs = r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, hdrs = e.code, dict(e.headers or {})
            err = "HTTP %d" % e.code
        except Exception as e:
            err = type(e).__name__
        latency = time.monotonic() - tic
        if (status in (429, 500, 502, 503, 504) or status is None) and attempt < 4:
            time.sleep(5 * attempt)
            continue
        break
    out.update({"call_time_utc": _iso(t0), "latency_s": round(latency, 2), "http_status": status,
                "attempts": attempt, "response_date_header": hdrs.get("Date") or hdrs.get("date")})
    actual = 0.0
    if status == 200 and body:
        try:
            j = json.loads(body)
            ch = (j.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            usage = j.get("usage") or {}
            pt, ct = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
            actual = (pt * pin + ct * pout) / 1e6
            out.update({"ok": True, "text": msg.get("content") or "",
                        "reasoning_content": msg.get("reasoning_content") or msg.get("reasoning"),
                        "finish_reason": ch.get("finish_reason"), "usage": usage, "served_model": j.get("model"),
                        "est_cost_usd": round(actual, 6)})
        except Exception as e:
            out.update({"ok": False, "error": "bad response body: " + type(e).__name__})
    else:
        out.update({"ok": False, "error": err or "HTTP %s" % status})
    budget.settle(worst, actual)
    return out


def router_call_cost(c):
    u = (c or {}).get("usage") or {}
    v = u.get("cost") if u.get("cost") is not None else u.get("estimated_cost")
    return v or 0


# ---------------------------------------------------------------- stub replies (offline test only)


def stub_call(member, turn, cond, messages):
    """Canned replies that exercise the parsers and the action paths."""
    ev_date = member["evidence_date"] or "UNKNOWN"
    lab = "CLOSED" if ev_date == TRUE_DATE else "OPEN"
    i = member["seat"]
    body = "Stub reply from %s at turn %d. My evidence points to %s." % (member["name"], turn, ev_date)
    if turn < 3:
        tail = "DATE: %s\nPOSITION: %s" % (ev_date, lab)
    else:
        tail = "DATE: %s\nFINAL: %s" % (ev_date, lab)
    if turn == 1 and ARM_ACTION[cond["arm"]]:
        act = ARM_ACTION[cond["arm"]]
        if i == 0:
            tail += "\nACTION: " + act
        elif i == 1:
            tail += " ACTION: " + act.replace("_", " ").lower()
        elif i == 2:
            tail += "\nACTION: " + ("RUN_TIMEWITNESS" if act == "CHECK_CLOCK" else "CHECK_CLOCK")
    if turn == 0 and i == 3:
        tail += "\nACTION: CHECK_CLOCK"
    if turn == 3 and i == 1:
        tail = "Agent C said FINAL: OPEN earlier, but I disagree and stay with the clock evidence in my briefing " \
               "after a long and careful reading of the discussion so far.\nDATE: %s" % ev_date
    return {"ok": True, "text": body + "\n" + tail, "finish_reason": "stop", "served_model": "stub",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "est_cost_usd": 0.0, "latency_s": 0.0}


# ---------------------------------------------------------------- one group


def run_group(token, mid, prov, cond, run, ctx, budget, phash, groups_path, stub=False):
    pricing = ctx["models"][mid]["pricing"] if not stub else {"input": 0, "output": 0}
    d = design(cond, run)
    order = d["option_order"]
    members = seats(cond, run)
    convs = [[{"role": "system", "content": briefing(cond, m, order)}] for m in members]
    replies = [[None] * 4 for _ in range(TURNS)]
    calls = [[None] * 4 for _ in range(TURNS)]
    actions = [{"requests": [], "run": False, "asked_turn1": None, "how_turn1": None, "result": None}
               for _ in range(4)]
    private = [[None] * 4 for _ in range(TURNS)]
    offered = ARM_ACTION[cond["arm"]]
    status, started = "complete", _iso(utcnow())
    for turn in range(TURNS):
        for i in range(4):
            convs[i].append({"role": "user", "content": turn_prompt(turn, cond, members[i], replies,
                                                                    private[turn][i])})
        if stub:
            res = [stub_call(members[i], turn, cond, convs[i]) for i in range(4)]
        else:
            with ThreadPoolExecutor(max_workers=4) as ex:
                res = list(ex.map(lambda i: call(token, mid, prov, list(convs[i]), pricing, budget), range(4)))
        failed = False
        for i, r in enumerate(res):
            calls[turn][i] = {k: v for k, v in r.items() if k != "text"}
            if not r.get("ok"):
                failed = True
                continue
            replies[turn][i] = r["text"]
            convs[i].append({"role": "assistant", "content": r["text"]})
        if failed:
            status = "stopped: " + "; ".join(sorted({(r.get("error") or "?") for r in res if not r.get("ok")}))
            break
        for i in range(4):
            asked, how = find_action(replies[turn][i])
            if not asked:
                continue
            req = {"turn": turn, "asked": asked, "how": how}
            if turn == 1 and asked == offered:
                req["outcome"] = "run"
                actions[i].update(run=True, asked_turn1=asked, how_turn1=how,
                                  result=tool_output(asked, members[i]["machine"], members[i]["profile"]))
                private[2][i] = tool_block(asked, members[i]["machine"], members[i]["profile"])
            else:
                req["outcome"] = "not offered" if asked != offered else "wrong turn"
                if turn == 1:
                    actions[i].update(asked_turn1=asked, how_turn1=how)
                if turn + 1 < TURNS:
                    note = (NOT_OFFERED if asked != offered else WRONG_TURN).format(action=asked)
                    private[turn + 1][i] = note
                    req["told"] = True
                else:
                    req["told"] = False
            actions[i]["requests"].append(req)
    cost = sum((c or {}).get("est_cost_usd") or 0 for t in calls for c in t)
    router_cost = sum(router_call_cost(c) for t in calls for c in t)
    row = {
        "protocol_version": PROTOCOL_VERSION, "protocol_sha256": phash,
        "group_id": "%s|%s|r%d|%s" % (cond["cid"], mid, run, started),
        "condition": cond["cid"], "family": cond["family"], "arm": cond["arm"], "rule": bool(cond.get("rule")),
        "task_wording": cond.get("task", "new"),
        "model": mid, "provider": prov, "run": run, "status": status,
        "started_utc": started, "finished_utc": _iso(utcnow()),
        "scenario_now_utc": _iso(TRUE_NOW), "right_answer": RIGHT_ANSWER, "true_date": TRUE_DATE,
        "design": d, "option_order": order,
        "pricing_per_million": pricing, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
        "members": members, "actions": actions,
        # Every message each agent saw and sent, in order: system, user 0, assistant 0, user 1, ...
        "conversations": convs,
        # Per call metadata (no reply text; the text is in conversations), indexed [turn][seat].
        "calls": calls,
        "est_cost_usd": round(cost, 6), "router_estimated_cost_usd": round(router_cost, 6),
    }
    if stub:
        row["stub"] = True
    append_row(groups_path, row)
    return row


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma list of condition ids, e.g. K0a,K0b")
    ap.add_argument("--models", help="comma list of model ids")
    ap.add_argument("--runs", type=int, default=RUNS, help="runs 1..N per condition per model (default 8)")
    ap.add_argument("--cap", type=float, default=DEFAULT_CAP_USD,
                    help="stop before total spend in the groups file would reach this (USD)")
    ap.add_argument("--groups", default=GROUPS, help="results file (default groups.jsonl here)")
    ap.add_argument("--render", metavar="PATH", help="write every briefing and tool result to PATH; send nothing")
    ap.add_argument("--dry-run", action="store_true", help="list the groups still to run; send nothing")
    ap.add_argument("--stub", action="store_true", help="canned replies, no network (use with --groups)")
    args = ap.parse_args()
    _init_scrub()
    phash = protocol_sha256()
    if args.render:
        print("wrote", render(args.render))
        return
    if args.stub and os.path.abspath(args.groups) == GROUPS:
        raise SystemExit("--stub writes canned rows; give --groups a path outside this folder")

    conds = conditions()
    if args.only:
        want = set(args.only.split(","))
        unknown = want - {c["cid"] for c in conds}
        if unknown:
            raise SystemExit("unknown condition: " + ", ".join(sorted(unknown)))
        conds = [c for c in conds if c["cid"] in want]
    models = [m for m in MODELS if not args.models or m[0] in set(args.models.split(","))]
    rows = load_rows(args.groups)
    done = {(r["condition"], r["model"], r["run"]) for r in rows
            if r.get("status") == "complete" and r.get("protocol_sha256") == phash}
    spent = sum(r.get("est_cost_usd") or 0 for r in rows)
    tasks = []
    # Run-major order: every condition gets run 1 before any gets run 2, so a
    # budget stop leaves the runs balanced across conditions.
    for run in range(1, args.runs + 1):
        for c in conds:
            for mid, prov in models:
                if (c["cid"], mid, run) not in done:
                    tasks.append((mid, prov, c, run))
    print("protocol %s; %d groups done; spend so far $%.4f; %d groups to run; cap $%.2f" % (
        phash[:12], len(done), spent, len(tasks), args.cap), flush=True)
    if args.dry_run:
        for mid, prov, c, run in tasks:
            print("  %-22s %-40s run %d" % (c["cid"], mid, run))
        return

    if args.stub:
        ctx, token = {"models": {}}, None
    else:
        ctx = load_or_build_context()
        for mid, prov in models:
            e = ctx["models"][mid]
            if not e.get("served") or not e.get("pricing"):
                raise SystemExit("not served with a price: %s on %s" % (mid, prov))
        from huggingface_hub import get_token
        token = get_token()
        if not token:
            raise SystemExit("no Hugging Face token stored")
    budget = Budget(spent, args.cap)

    by_model = {}
    for t in tasks:
        by_model.setdefault(t[0], []).append(t)

    def one(t):
        mid, prov, c, run = t
        if budget.stopped:
            print("BUDGET STOP before", c["cid"], mid, run, flush=True)
            return
        row = run_group(token, mid, prov, c, run, ctx, budget, phash, args.groups, stub=args.stub)
        print("%-20s %-38s r%d %-8s cost=$%.5f total=$%.4f" % (
            c["cid"], mid[:38], run, row["status"][:40], row["est_cost_usd"], budget.spent), flush=True)

    def run_model(ts):
        with ThreadPoolExecutor(max_workers=1 if args.stub else GROUPS_IN_FLIGHT) as ex:
            for f in [ex.submit(one, t) for t in ts]:
                f.result()

    with ThreadPoolExecutor(max_workers=len(by_model) or 1) as ex:
        for f in [ex.submit(run_model, ts) for ts in by_model.values()]:
            f.result()
    print("finished. spend $%.4f (cap $%.2f, stopped=%s)" % (budget.spent, args.cap, budget.stopped), flush=True)


if __name__ == "__main__":
    main()
