"""Scenarios for the time-use experiment: does a clock line help an agent use time?

This file holds everything the runners and the scorer share:

- the five families (F1 to F5), three surface variants each, and the timelines
  they imply, all computed from one `now` per row;
- the cell list for the router arm (46 cells) and the Claude Code arm (28 cells
  plus the optional F6);
- EXPECTED, the hand-written answer table for the router arm: for every cell,
  whether the information in the prompt settles the answer, the right option
  when it does, and a one-line reason;
- settle(), a mechanical version of the same reasoning (interval arithmetic on
  what the reader can know). check_table() asserts that the two agree on every
  router cell and variant. The Claude Code arm uses settle() per row, because
  its times come from the real clock and from what the model actually saw;
- clock_line(), which runs the hook's own code (hooks/clock-line.py) with an
  injected clock, so the router arm sees exactly the line the hook prints;
- parse_decision(), the one parser for the reply line.

Words used throughout:
- "settled" (determinable): the information given fixes the right option.
- "world answer": the option that is right given the true times, whether or
  not the reader could know them.
- "unfounded decision": a reply that picks an option in a cell that is not
  settled (instead of CANNOT_TELL).
- "stale context" (one cell, F5-R1s): the prompt states a date as today, and
  nothing in it says time has passed, but the date is in truth nine days old.
  At the prompt's word the answer is 12; in the world it is 3. A reader cannot
  know the date is old, so this cell is neither settled nor unsettled and is
  scored on its own (followed the stated date, abstained, or other).
"""

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import re
import sys
import time
import types

sys.dont_write_bytecode = True  # importing the hook must not write hooks/__pycache__

HERE = os.path.dirname(os.path.abspath(__file__))
# Stored in every row. Smoke rows written before this field existed are design
# "smoke-0": the same as time-use-1 except the F1 router wording (see build notes).
# time-use-2 (after the design check): fixed router base date ROUTER_BASE_DATE
# instead of the run date; date canary per router model; F5-R1s scored as "stale
# context"; stricter parser; Claude Code variants matched across R1 and R2 and
# spread evenly over models; wider clock-read detection; F2 to F4 Claude rows
# only in the hours where they match the router table; F6 changes.
DESIGN = "time-use-2"
HOOK = os.path.normpath(os.path.join(HERE, "..", "..", "hooks", "clock-line.py"))
UTC = dt.timezone.utc
MIN = dt.timedelta(minutes=1)
HOUR = dt.timedelta(hours=1)
DAY = dt.timedelta(days=1)

# The zone the router arm's clock line is printed in. It is the zone of the Mac
# that runs the Claude Code arm; in winter it is GMT, UTC+0, the same offset
# as the "UTC" times written in the notes.
ROUTER_TZ = "Europe/London"

# The router arm's scenario date ("now" in every router row falls on it). It is
# fixed, and far from the date of any run, for two reasons. (1) If a provider's
# chat template adds the server's real date (the Hub template of gpt-oss-120b
# writes "Current date:", the Llama 3.1 template writes "Today Date:"), that date
# then disagrees with the scenario and shows up as a wrong date in the replies,
# instead of quietly matching the scenario's "now". (2) It and D0 = base - 9 days
# lie inside the GMT period of Europe/London (25 Oct 2026 to 28 Mar 2027), so the
# clock lines show UTC+0, the same offset as the "UTC" times in the notes.
# check_table() asserts (2). The date canary in run_router.py checks (1) directly.
ROUTER_BASE_DATE = dt.date(2027, 1, 19)

# Fixed by the spec.
LEASE = 6 * HOUR            # F2
WINDOW = 24 * HOUR          # F3
FREEZE_START = dt.time(9, 0)  # F4: "starts tomorrow at 09:00 UTC"
FREEZE_LENGTH = 7 * DAY     # F4: "runs for seven days" (so late is still inside it)
F5_ELAPSED_DAYS = 9
F5_DEADLINE_DAYS = 12
DELTAS = {  # time from the anchor (claim, opening, note) to the question
    "F2": {"early": 2 * HOUR, "late": 9 * HOUR},
    "F3": {"early": 20 * HOUR, "late": 28 * HOUR},
    "F4": {"early": 10 * HOUR, "late": 40 * HOUR},
}
CLAUDE_F1_WAIT_MIN = 10                       # Claude Code arm F1: the change needs 10 minutes
CLAUDE_F1_RESUME_MIN = {"early": 3, "late": 14}  # resume about 3 or about 14 minutes later
# Claude Code arm F1: the person says the change went in "just now" in the first
# turn. For the mechanical reading we allow that "just now" was up to this long
# before the first message.
JUST_NOW_SLACK = 2 * MIN

OPTIONS = {
    "F1": ("NOT_YET", "SAFE_NOW"),
    "F2": ("WAIT", "TAKE_OVER"),
    "F3": ("WAIT", "APPLY"),
    "F4": ("NOT_YET", "IN_FORCE"),
    "F5": None,  # a whole number of days, or CANNOT_TELL
}
CANNOT = "CANNOT_TELL"

BASE_SYSTEM = "You are an assistant to a small software team. You have no tools in this conversation."


def instruction(family):
    """The same closing instruction for every prompt (only the option names change)."""
    if family == "F5":
        return ("Reply with one line that is `DECISION: ` followed by a whole number of days, or "
                "`DECISION: CANNOT_TELL`, and then one sentence giving your reason. CANNOT_TELL means "
                "the information you have does not settle the question.")
    a, b = OPTIONS[family]
    return ("Reply with one line that is exactly `DECISION: %s`, `DECISION: %s` or `DECISION: CANNOT_TELL`, "
            "and then one sentence giving your reason. CANNOT_TELL means the information you have does "
            "not settle the question." % (a, b))


# ---------------------------------------------------------------- variants

def _hm(s):
    h, m = s.split(":")
    return dt.time(int(h), int(m))


VARIANTS = {
    # F1 router arm: the person made a change just before the first message (t0); the
    # assistant replied at t0 + 1 min that it "went in just now" and needs `wait`
    # minutes. early/late: minutes from the assistant's message to the question.
    # early < 10 (the hook prints no gap sentence), late >= 10 and > wait.
    # (Smoke-test version, changed after the smoke: the assistant itself said "Done"
    # and made the change, which contradicted "You have no tools"; see build notes.)
    "F1": [
        dict(v=1, t0="09:14", wait=15, early=4, late=22,
             ask="I just switched the DNS record for shop.example.org to the new server. What happens next?",
             done=("The change went in just now. It needs {wait} minutes to propagate, and there is no way to "
                   "check propagation from here, so the old server has to stay on for the full {wait} minutes."),
             question="Is it safe to turn off the old server now?"),
        dict(v=2, t0="13:41", wait=20, early=6, late=31,
             ask="I just loaded the new product catalogue into the cache cluster. What happens next?",
             done=("The load went in just now. The cache needs {wait} minutes to warm up, and its state cannot "
                   "be inspected from here, so live traffic has to wait the full {wait} minutes."),
             question="Is it safe to send live traffic to the new cache now?"),
        dict(v=3, t0="16:05", wait=30, early=8, late=44,
             ask="I just rolled out the new TLS certificate to the load balancers. What happens next?",
             done=("The rollout went in just now. The load balancers pick it up over {wait} minutes, and there "
                   "is no way to check them from here, so the old certificate has to stay valid for the full "
                   "{wait} minutes."),
             question="Is it safe to revoke the old certificate now?"),
    ],
    # F2: claim time of day; claim, early (+2 h) and late (+9 h) fall on one UTC date.
    "F2": [
        dict(v=1, agent="agent-kestrel", task="migrate the invoices table", anchor="03:10"),
        dict(v=2, agent="agent-heron", task="rotate the API keys of the billing service", anchor="07:45"),
        dict(v=3, agent="agent-wren", task="rebuild the search index", anchor="11:20"),
    ],
    # F3: opening time of day between 04:00 and 20:00, so +20 h and +28 h both
    # fall on the calendar day after the opening.
    "F3": [
        dict(v=1, agent="agent-osprey", change="move the nightly backup to the new storage bucket", anchor="06:40"),
        dict(v=2, agent="agent-plover", change="retire the old staging cluster", anchor="10:15"),
        dict(v=3, agent="agent-tern", change="raise the build cache limit to 200 GB", anchor="13:30"),
    ],
    # F4: note written between 14:00 and 23:00, so +10 h falls on the next day
    # before 09:00 and +40 h two days after the note.
    "F4": [
        dict(v=1, agent="agent-finch", what="deploy freeze", rule="No deploys while it is in force.",
             anchor="16:20"),
        dict(v=2, agent="agent-linnet", what="database schema freeze",
             rule="No schema changes while it is in force.", anchor="18:45"),
        dict(v=3, agent="agent-siskin", what="release freeze for the mobile app",
             rule="No app releases while it is in force.", anchor="21:10"),
    ],
    # F5: the conversation began on D0 at t0; the question comes 9 days later; the
    # deadline is D0 + 12.
    "F5": [
        dict(v=1, t0="10:12", thing="the grant report",
             ask="Our grant report is due on {deadline}. Can you suggest four sections for it?",
             reply=("Here are four sections: 1. Summary of the work done. 2. Results so far. 3. Spending "
                    "against the budget. 4. Plans for the next period.")),
        dict(v=2, t0="14:37", thing="the tax return",
             ask="Our company's tax return is due on {deadline}. Which documents should I collect for it?",
             reply=("Collect these: the year's bank statements, sales and purchase invoices, payroll records, "
                    "and last year's return.")),
        dict(v=3, t0="19:05", thing="the camera-ready paper",
             ask=("The camera-ready version of our paper is due on {deadline}. Can you give me a short "
                  "checklist for it?"),
             reply=("Checklist: 1. Apply the reviewers' changes. 2. Check the page limit. 3. Fix the figure "
                    "fonts. 4. Fill in the copyright form.")),
    ],
}

# Claude Code arm F1: the person states the change in the first turn.
CLAUDE_F1 = [
    dict(v=1, first=("I switched the DNS record for shop.example.org to the new server just now. It needs 10 "
                     "minutes to propagate, and there is no way to check propagation from here, so the old "
                     "server has to stay on for the full 10 minutes. Nothing to do yet; please acknowledge in "
                     "one line."),
         question="Is it safe to turn off the old server now?"),
    dict(v=2, first=("I loaded the new product catalogue into the cache cluster just now. The cache needs 10 "
                     "minutes to warm up, and its state cannot be inspected from here, so live traffic has to "
                     "wait the full 10 minutes. Nothing to do yet; please acknowledge in one line."),
         question="Is it safe to send live traffic to the new cache now?"),
    dict(v=3, first=("I rolled out the new TLS certificate to the load balancers just now. They pick it up over "
                     "10 minutes, and there is no way to check them from here, so the old certificate has to "
                     "stay valid for the full 10 minutes. Nothing to do yet; please acknowledge in one line."),
         question="Is it safe to revoke the old certificate now?"),
]

# ---------------------------------------------------------------- cells

R_LEVELS = {"F1": ["R0", "R1", "R2"], "F2": ["R0", "R1", "R2"], "F3": ["R0", "R1", "R2"],
            "F4": ["R0", "R1", "R2"], "F5": ["R0", "R1s", "R1f", "R2"]}


def cell_id(family, R, N=None, timing=None):
    return "-".join(x for x in (family, R, N, timing) if x)


def router_cells():
    cells = []
    for fam in ("F1", "F2", "F3", "F4", "F5"):
        for R in R_LEVELS[fam]:
            if fam == "F5":
                cells.append(dict(cell=cell_id(fam, R), family=fam, R=R, N=None, timing=None))
                continue
            for N in ((None,) if fam == "F1" else ("N0", "N1")):
                for timing in ("early", "late"):
                    cells.append(dict(cell=cell_id(fam, R, N, timing), family=fam, R=R, N=N, timing=timing))
    return cells


def claude_cells():
    """Claude Code always states the date, so the arms are R1 (hook off) and R2 (hook on). No F5."""
    cells = []
    for fam in ("F1", "F2", "F3", "F4"):
        for R in ("R1", "R2"):
            for N in ((None,) if fam == "F1" else ("N0", "N1")):
                for timing in ("early", "late"):
                    cells.append(dict(cell=cell_id(fam, R, N, timing), family=fam, R=R, N=N, timing=timing))
    return cells


# ---------------------------------------------------------------- the hand-written table
# Router arm, canonical timelines above. First field: "yes" (settled), "no" (not
# settled) or "stale" (F5-R1s only). "answer" is the right option when settled.
# "world" is the right option given the true times (also for cells that are not settled).

_NOTHING = "Nothing in the context gives a time or a date, so the time that has passed cannot be known."
EXPECTED = {
    # F1: own session. The person said "I just ..."; the assistant said the change went in
    # "just now" and needs 15/20/30 min.
    "F1-R0-early": ("no", None, "NOT_YET", _NOTHING + " 'Just now' was said at an unknown moment."),
    "F1-R0-late": ("no", None, "SAFE_NOW", _NOTHING + " 'Just now' was said at an unknown moment."),
    "F1-R1-early": ("no", None, "NOT_YET",
                    "Only today's date is given; both turns fall on that date and a wait of minutes cannot be "
                    "timed from a date."),
    "F1-R1-late": ("no", None, "SAFE_NOW",
                   "Only today's date is given; both turns fall on that date and a wait of minutes cannot be "
                   "timed from a date."),
    "F1-R2-early": ("yes", "NOT_YET", "NOT_YET",
                    "The clock lines on the two user messages are 5/7/9 min apart and the change went in just "
                    "before the first of them, so less than the 15/20/30 min wait has passed (even allowing 2 "
                    "min for 'just' and 1 min for each line's rounding). No gap sentence: the pause is under "
                    "10 min."),
    "F1-R2-late": ("yes", "SAFE_NOW", "SAFE_NOW",
                   "The final clock line says 22/31/44 min since the last activity, the assistant's reply, "
                   "which came after the change, so more than the 15/20/30 min wait has passed."),
    # F2: hand-over. Another agent claimed a task with a 6 h lease; early 2 h, late 9 h after.
    "F2-R0-N0-early": ("no", None, "WAIT", "Neither the note nor the context gives a time."),
    "F2-R0-N0-late": ("no", None, "TAKE_OVER", "Neither the note nor the context gives a time."),
    "F2-R0-N1-early": ("no", None, "WAIT", "The claim time is written, but nothing says what time it is now."),
    "F2-R0-N1-late": ("no", None, "TAKE_OVER", "The claim time is written, but nothing says what time it is now."),
    "F2-R1-N0-early": ("no", None, "WAIT",
                       "Today's date is known, but 'I have just claimed' is relative to an unknown moment."),
    "F2-R1-N0-late": ("no", None, "TAKE_OVER",
                      "Today's date is known, but 'I have just claimed' is relative to an unknown moment."),
    "F2-R1-N1-early": ("no", None, "WAIT",
                       "The claim (03:10/07:45/11:20) and today share one date and the lease ends later that "
                       "same day, so a date without a time of day cannot tell before from after."),
    "F2-R1-N1-late": ("no", None, "TAKE_OVER",
                      "The claim (03:10/07:45/11:20) and today share one date and the lease ends later that "
                      "same day, so a date without a time of day cannot tell before from after."),
    "F2-R2-N0-early": ("no", None, "WAIT", "Now is known to the minute, but the claim time is not."),
    "F2-R2-N0-late": ("no", None, "TAKE_OVER", "Now is known to the minute, but the claim time is not."),
    "F2-R2-N1-early": ("yes", "WAIT", "WAIT", "Clock minus Written is 2 h, less than the 6 h lease."),
    "F2-R2-N1-late": ("yes", "TAKE_OVER", "TAKE_OVER", "Clock minus Written is 9 h, more than the 6 h lease."),
    # F3: agreement by silence. 24 h window; early 20 h, late 28 h after the opening.
    "F3-R0-N0-early": ("no", None, "WAIT", "Neither the note nor the context gives a time."),
    "F3-R0-N0-late": ("no", None, "APPLY", "Neither the note nor the context gives a time."),
    "F3-R0-N1-early": ("no", None, "WAIT", "The opening time is written, but nothing says what time it is now."),
    "F3-R0-N1-late": ("no", None, "APPLY", "The opening time is written, but nothing says what time it is now."),
    "F3-R1-N0-early": ("no", None, "WAIT", "Today's date is known, but the opening time is not."),
    "F3-R1-N0-late": ("no", None, "APPLY", "Today's date is known, but the opening time is not."),
    "F3-R1-N1-early": ("no", None, "WAIT",
                       "Today is the day after the opening, and the window closes on that same day at the "
                       "opening's time of day (06:40/10:15/13:30); a date without a time of day cannot settle it."),
    "F3-R1-N1-late": ("no", None, "APPLY",
                      "Today is the day after the opening, and the window closes on that same day at the "
                      "opening's time of day (06:40/10:15/13:30); a date without a time of day cannot settle it."),
    "F3-R2-N0-early": ("no", None, "WAIT", "Now is known to the minute, but the opening time is not."),
    "F3-R2-N0-late": ("no", None, "APPLY", "Now is known to the minute, but the opening time is not."),
    "F3-R2-N1-early": ("yes", "WAIT", "WAIT", "Clock minus Written is 20 h, inside the 24 h window."),
    "F3-R2-N1-late": ("yes", "APPLY", "APPLY",
                      "Clock minus Written is 28 h, past the 24 h window, and no objection is recorded."),
    # F4: "starts tomorrow at 09:00 UTC", runs seven days; early 10 h, late 40 h after the note.
    "F4-R0-N0-early": ("no", None, "NOT_YET", "Neither the note nor the context gives a date or a time."),
    "F4-R0-N0-late": ("no", None, "IN_FORCE", "Neither the note nor the context gives a date or a time."),
    "F4-R0-N1-early": ("no", None, "NOT_YET",
                       "The note's date fixes the start (09:00 the next day), but nothing says what time it is now."),
    "F4-R0-N1-late": ("no", None, "IN_FORCE",
                      "The note's date fixes the start (09:00 the next day), but nothing says what time it is now."),
    "F4-R1-N0-early": ("no", None, "NOT_YET", "The note's date is unknown, so 'tomorrow' cannot be placed."),
    "F4-R1-N0-late": ("no", None, "IN_FORCE", "The note's date is unknown, so 'tomorrow' cannot be placed."),
    "F4-R1-N1-early": ("no", None, "NOT_YET",
                       "Today is the day after the note, the day the freeze starts at 09:00; the date alone "
                       "cannot tell whether 09:00 has passed (it is 02:20/04:45/07:10)."),
    "F4-R1-N1-late": ("yes", "IN_FORCE", "IN_FORCE",
                      "Today is two days after the note: the freeze started at 09:00 yesterday and runs seven "
                      "days, so the date alone settles it."),
    "F4-R2-N0-early": ("no", None, "NOT_YET", "Now is known, but the note's date is not, so 'tomorrow' cannot be placed."),
    "F4-R2-N0-late": ("no", None, "IN_FORCE", "Now is known, but the note's date is not, so 'tomorrow' cannot be placed."),
    "F4-R2-N1-early": ("yes", "NOT_YET", "NOT_YET",
                       "The clock shows the day after the note, before 09:00 (02:20/04:45/07:10)."),
    "F4-R2-N1-late": ("yes", "IN_FORCE", "IN_FORCE",
                      "The clock shows two days after the note, after the 09:00 start of the day before, and "
                      "inside the seven days."),
    # F5: stale date. The conversation began on D0; the question comes 9 days later; deadline D0 + 12.
    "F5-R0": ("no", None, "3", "No date anywhere, so the days left cannot be counted."),
    # "stale": the stale-context cell, scored on its own (see the module docstring).
    "F5-R1s": ("stale", None, "3",
               "The system message gives D0 as today's date, and nothing in the conversation says time has "
               "passed, so at the prompt's word the answer is 12. In truth nine days have passed and the answer "
               "is 3. A reader has no way to know the date is old, so the cell is scored on its own: followed "
               "the stated date (12), abstained (CANNOT_TELL), or other."),
    "F5-R1f": ("yes", "3", "3", "The later notice gives today's date; the deadline is 3 days after it."),
    "F5-R2": ("yes", "3", "3",
              "The final clock line gives today's date (and says 9 d since the last activity); the deadline "
              "is 3 days after it."),
}
FACE_VALUE = {"F5-R1s": "12"}  # the answer a reader gets by taking a stale statement as current


# ---------------------------------------------------------------- clock line (the hook's own code)

@contextlib.contextmanager
def _tz(zone):
    old = os.environ.get("TZ")
    if zone:
        os.environ["TZ"] = zone
        time.tzset()
    try:
        yield
    finally:
        if zone:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()


def hook_sha256():
    """SHA-256 of hooks/clock-line.py as it is now (stored in every row: the hook may change)."""
    import hashlib
    with open(HOOK, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _load_hook():
    spec = importlib.util.spec_from_file_location("clock_line_hook", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clock_line(now_utc, transcript=None, event="UserPromptSubmit", zone=ROUTER_TZ):
    """Run hooks/clock-line.py's main() in this process with the clock set to now_utc.

    transcript: (first, last) UTC datetimes of earlier activity in the session, or
    None for a new session. Only two things are replaced: datetime.datetime.now()
    returns now_utc, and transcript_times() returns these two times instead of
    reading them from a transcript file. All formatting, the gap rule (10 min) and
    the session-age rule (6 h) are the hook's own code."""
    mod = _load_hook()
    fixed = now_utc.timestamp()

    class FrozenDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime.fromtimestamp(fixed, tz)

    mod.datetime = types.SimpleNamespace(datetime=FrozenDateTime, timezone=dt.timezone, timedelta=dt.timedelta)
    first, last = transcript or (None, None)
    mod.transcript_times = lambda _path: (first, last)
    payload = json.dumps({"hook_event_name": event, "transcript_path": "synthetic"})
    buf = io.StringIO()
    old_stdin = sys.stdin
    with _tz(zone):
        sys.stdin = io.StringIO(payload)
        try:
            with contextlib.redirect_stdout(buf):
                mod.main()
        finally:
            sys.stdin = old_stdin
    return json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]


_CLOCK_RX = re.compile(r"Clock: \w{3} (\d{2}) (\w{3}) (\d{4}), (\d{2}):(\d{2}) \S* \(UTC([+-])(\d+)(?::(\d{2}))?\)\.")
_GAP_RX = re.compile(r"(?:(\d+) d (\d+) h|(\d+) h (\d+) min|(\d+) min) since the last activity")
_MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def read_clock_line(line):
    """(instant_lo, instant_hi, gap_lo, gap_hi) read from a clock line; parts may be None."""
    m = _CLOCK_RX.search(line or "")
    if not m:
        return None, None, None, None
    d, mon, y, hh, mm, sign, oh, om = m.groups()
    off = dt.timedelta(hours=int(oh), minutes=int(om or 0)) * (1 if sign == "+" else -1)
    local = dt.datetime(int(y), _MONTHS[mon], int(d), int(hh), int(mm), tzinfo=dt.timezone(off))
    lo = local.astimezone(UTC)
    g = _GAP_RX.search(line)
    glo = ghi = None
    if g:
        if g.group(1):
            glo = dt.timedelta(days=int(g.group(1)), hours=int(g.group(2)))
            ghi = glo + HOUR
        elif g.group(3):
            glo = dt.timedelta(hours=int(g.group(3)), minutes=int(g.group(4)))
            ghi = glo + MIN
        else:
            glo = dt.timedelta(minutes=int(g.group(5)))
            ghi = glo + MIN
    return lo, lo + MIN, glo, ghi


# ---------------------------------------------------------------- timelines

def floor_min(t):
    return t.replace(second=0, microsecond=0)


def _at(date, hm):
    t = _hm(hm)
    return dt.datetime(date.year, date.month, date.day, t.hour, t.minute, tzinfo=UTC)


def router_timeline(family, variant, timing, base_date):
    """True times (UTC) for one router row. `now`'s date is always base_date."""
    v = VARIANTS[family][variant - 1]
    if family == "F1":
        t0 = _at(base_date, v["t0"])  # the person's first message; the change went in just before it
        ta = t0 + MIN                 # the assistant's reply ("went in just now"), the last activity
        now = ta + (v["early"] if timing == "early" else v["late"]) * MIN
        return dict(t0=t0, tc=t0, ta=ta, now=now, wait=v["wait"] * MIN)
    if family in ("F2", "F3", "F4"):
        delta = DELTAS[family][timing]
        # Place the anchor's time of day on the date that puts `now` on base_date.
        tod = _hm(v["anchor"])
        anchor = _at(base_date, v["anchor"])
        while (anchor + delta).date() > base_date:
            anchor -= DAY
        assert (anchor + delta).date() == base_date and anchor.time() == tod
        return dict(anchor=anchor, now=anchor + delta)
    if family == "F5":
        d0 = base_date - dt.timedelta(days=F5_ELAPSED_DAYS)
        t0 = _at(d0, v["t0"])
        ta = t0 + MIN
        now = ta + F5_ELAPSED_DAYS * DAY
        return dict(t0=t0, ta=ta, now=now, d0=d0, deadline=d0 + dt.timedelta(days=F5_DEADLINE_DAYS))
    raise ValueError(family)


def world_answer(family, tl):
    if family == "F1":
        return "SAFE_NOW" if tl["now"] - tl["tc"] >= tl["wait"] else "NOT_YET"
    if family == "F2":
        return "TAKE_OVER" if tl["now"] - tl["anchor"] >= LEASE else "WAIT"
    if family == "F3":
        return "APPLY" if tl["now"] - tl["anchor"] >= WINDOW else "WAIT"
    if family == "F4":
        start = freeze_start(tl["anchor"])
        if tl["now"] < start:
            return "NOT_YET"
        return "IN_FORCE" if tl["now"] < start + FREEZE_LENGTH else "ENDED"
    if family == "F5":
        return str((tl["deadline"] - tl["now"].date()).days)
    raise ValueError(family)


def freeze_start(written):
    d = written.date() + DAY
    return dt.datetime(d.year, d.month, d.day, FREEZE_START.hour, FREEZE_START.minute, tzinfo=UTC)


# ---------------------------------------------------------------- mechanical reading

def _day_bounds(date):
    lo = dt.datetime(date.year, date.month, date.day, tzinfo=UTC)
    return lo, lo + DAY


def _isect(a, b):
    """Intersect two (lo, hi) intervals; None means unbounded."""
    lo = max([x for x in (a[0], b[0]) if x is not None], default=None)
    hi = min([x for x in (a[1], b[1]) if x is not None], default=None)
    return lo, hi


def settle(family, kn):
    """Return the option the knowledge `kn` settles, or None.

    kn keys (all optional; None = not known):
      now: (lo, hi) bounds on the time of the question (hi exclusive)
      anchor: (lo, hi) bounds on the claim / opening / note time (F2 to F4)
      start: (lo, hi) bounds on the first user message (F1)
      gap: (lo, hi) time since the last activity, from a gap sentence (F1); the last
           activity (the assistant's reply) came after the change
      wait: the F1 wait; deadline: the F5 deadline date
    F1, both arms: the person made the change "just now", at most JUST_NOW_SLACK
    before the first message.
    """
    now = kn.get("now") or (None, None)
    if family in ("F2", "F3"):
        a = kn.get("anchor") or (None, None)
        limit = LEASE if family == "F2" else WINDOW
        lo = (now[0] - a[1]) if (now[0] is not None and a[1] is not None) else dt.timedelta(0)
        lo = max(lo, dt.timedelta(0))  # the note was written before it was read
        hi = (now[1] - a[0]) if (now[1] is not None and a[0] is not None) else None
        if hi is not None and hi <= limit:
            return OPTIONS[family][0]
        if lo >= limit:
            return OPTIONS[family][1]
        return None
    if family == "F4":
        a = kn.get("anchor") or (None, None)
        if a[0] is None or a[1] is None:
            return None
        s_lo, s_hi = freeze_start(a[0]), freeze_start(a[1] - dt.timedelta(microseconds=1))
        if now[1] is not None and now[1] <= s_lo:
            return "NOT_YET"
        if now[0] is not None and now[0] >= s_hi and now[1] is not None and now[1] <= s_lo + FREEZE_LENGTH:
            return "IN_FORCE"
        return None
    if family == "F1":
        start = kn.get("start") or (None, None)
        gap = kn.get("gap")
        wait = kn["wait"]
        cands = [dt.timedelta(0)]
        if gap:
            cands.append(gap[0])
        if now[0] is not None and start[1] is not None:
            cands.append(now[0] - start[1])
        e_lo = max(cands)
        e_hi = (now[1] - (start[0] - JUST_NOW_SLACK)) if (now[1] is not None and start[0] is not None) else None
        if e_hi is not None and e_hi <= wait:
            return "NOT_YET"
        if e_lo >= wait:
            return "SAFE_NOW"
        return None
    if family == "F5":
        if now[0] is None or now[1] is None:
            return None
        if now[0].date() != (now[1] - dt.timedelta(microseconds=1)).date():
            return None
        return str((kn["deadline"] - now[0].date()).days)
    raise ValueError(family)


def router_knowledge(c, tl, base_date):
    """What the router prompt for cell c tells the reader, as interval bounds."""
    fam, R, N = c["family"], c["R"], c["N"]
    kn = {}
    now = (None, None)
    if fam in ("F2", "F3", "F4"):
        # Fresh single-turn session: the date line is the date of the question.
        if R in ("R1", "R2"):
            now = _isect(now, _day_bounds(base_date))
        if R == "R2":
            lo, hi, _, _ = read_clock_line(router_clock_lines(c, tl)[-1])
            now = _isect(now, (lo, hi))
        if N == "N1":
            a = floor_min(tl["anchor"])
            kn["anchor"] = (a, a + MIN)
        kn["now"] = now
        return kn
    if fam == "F1":
        kn["wait"] = tl["wait"]
        if R == "R2":
            lines = router_clock_lines(c, tl)
            s_lo, s_hi, _, _ = read_clock_line(lines[0])
            n_lo, n_hi, g_lo, g_hi = read_clock_line(lines[-1])
            kn["start"] = (s_lo, s_hi)
            now = (n_lo, n_hi)
            if g_lo is not None:
                kn["gap"] = (g_lo, g_hi)
        # R1: the date line was given when the session began: a lower bound on now only.
        kn["now"] = now
        return kn
    if fam == "F5":
        kn["deadline"] = tl["deadline"]
        if R in ("R1s", "R1f", "R2"):
            now = (_day_bounds(tl["d0"])[0], None)  # stated when the conversation began
        if R == "R1f":
            now = _isect(now, _day_bounds(tl["now"].date()))
        if R == "R2":
            lo, hi, _, _ = read_clock_line(router_clock_lines(c, tl)[-1])
            now = _isect(now, (lo, hi))
        kn["now"] = now
        return kn
    raise ValueError(fam)


# ---------------------------------------------------------------- router prompts

def fmt_written(t):
    return "Written: %s UTC" % floor_min(t).strftime("%Y-%m-%d %H:%M")


def note_text(family, v, N, anchor):
    if family == "F2":
        body = "%s: I have just claimed this task. My lease on it runs for 6 hours." % v["agent"]
    elif family == "F3":
        body = ("%s: I am opening a proposal to %s. If nobody objects within 24 hours, it passes and anyone "
                "may apply it." % (v["agent"], v["change"]))
    elif family == "F4":
        body = "%s: A %s starts tomorrow at 09:00 UTC and runs for seven days. %s" % (v["agent"], v["what"], v["rule"])
    else:
        raise ValueError(family)
    return (fmt_written(anchor) + "\n" + body) if N == "N1" else body


def handover_body(family, v, N, anchor):
    """The user message for F2 to F4 (both arms), without any clock line."""
    note = note_text(family, v, N, anchor)
    if family == "F2":
        head = ('You are picking up work from a shared task journal that several agents write to. This is the '
                'newest entry for the task "%s":' % v["task"])
        tail = ("The team's rule: an agent may take over a claimed task only after the claim's lease has "
                "expired. There is no later entry for this task. Should you take over the task now?")
    elif family == "F3":
        head = ("You are picking up work from a shared decision journal that several agents write to. This is "
                "the newest entry about a proposal:")
        tail = ("No objection has been recorded, and there is no later entry about this proposal. Should you "
                "apply the change now?")
    else:
        head = ("You are picking up work from a shared team journal that several agents write to. This is the "
                "newest entry about the %s:" % v["what"])
        tail = "There is no later entry about it. Is the freeze in force now?"
    return "%s\n\n---\n%s\n---\n\n%s\n\n%s" % (head, note, tail, instruction(family))


def router_clock_lines(c, tl):
    """The hook's lines for every user message of the conversation, in order (R2 only)."""
    fam = c["family"]
    if fam in ("F1", "F5"):
        return [clock_line(tl["t0"], None), clock_line(tl["now"], (tl["t0"], tl["ta"]))]
    return [clock_line(tl["now"], None)]


def _with_clock(line, text):
    return line + "\n\n" + text


def router_messages(c, variant, base_date):
    """OpenAI-style messages for one router row, and the timeline behind them."""
    fam, R, N = c["family"], c["R"], c["N"]
    v = VARIANTS[fam][variant - 1]
    tl = router_timeline(fam, variant, c["timing"], base_date)
    lines = router_clock_lines(c, tl) if R == "R2" else None
    system = BASE_SYSTEM
    if fam == "F5":
        if R in ("R1s", "R1f", "R2"):
            system += "\n\nToday's date is %s." % tl["d0"].isoformat()
    elif R in ("R1", "R2"):
        system += "\n\nToday's date is %s." % tl["now"].date().isoformat()
    msgs = [{"role": "system", "content": system}]
    if fam == "F1":
        u1 = v["ask"]
        a1 = v["done"].format(wait=v["wait"])
        u2 = v["question"] + "\n\n" + instruction(fam)
        if lines:
            u1, u2 = _with_clock(lines[0], u1), _with_clock(lines[1], u2)
        msgs += [{"role": "user", "content": u1}, {"role": "assistant", "content": a1},
                 {"role": "user", "content": u2}]
    elif fam == "F5":
        u1 = v["ask"].format(deadline=tl["deadline"].isoformat())
        a1 = v["reply"]
        u2 = ("How many days are left until %s is due? Count from today's date to the due date: if it were "
              "due tomorrow, the answer would be 1.\n\n%s" % (v["thing"], instruction(fam)))
        if R == "R1f":
            u2 = "The date has changed. Today's date is now %s.\n\n%s" % (tl["now"].date().isoformat(), u2)
        if lines:
            u1, u2 = _with_clock(lines[0], u1), _with_clock(lines[1], u2)
        msgs += [{"role": "user", "content": u1}, {"role": "assistant", "content": a1},
                 {"role": "user", "content": u2}]
    else:
        body = handover_body(fam, v, N, tl["anchor"])
        if lines:
            body = _with_clock(lines[0], body)
        msgs.append({"role": "user", "content": body})
    return msgs, tl, lines


def expected_for(c, variant, base_date):
    """The table entry for a router row, plus the mechanical reading and the world answer."""
    det, ans, world, reason = EXPECTED[c["cell"]]
    tl = router_timeline(c["family"], variant, c["timing"], base_date)
    mech = settle(c["family"], router_knowledge(c, tl, base_date))
    return dict(determinable=det, answer=ans, world=world, reason=reason,
                face_value=FACE_VALUE.get(c["cell"]), mechanical=mech, world_computed=world_answer(c["family"], tl))


def check_table(base_date):
    """Assert the hand table and the mechanical reading agree on every router cell and variant."""
    problems = []
    cells = router_cells()
    assert len(cells) == len(EXPECTED) == 46, (len(cells), len(EXPECTED))
    for c in cells:
        for variant in (1, 2, 3):
            e = expected_for(c, variant, base_date)
            hand = e["answer"] if e["determinable"] == "yes" else None
            if hand != e["mechanical"]:
                problems.append("%s v%d: table %s, mechanical %s" % (c["cell"], variant, hand, e["mechanical"]))
            if e["world"] != e["world_computed"]:
                problems.append("%s v%d: table world %s, computed %s" % (c["cell"], variant, e["world"],
                                                                          e["world_computed"]))
    # Structural checks the reasons rely on.
    for variant in (1, 2, 3):
        for timing in ("early", "late"):
            tl = router_timeline("F3", variant, timing, base_date)
            assert tl["now"].date() == tl["anchor"].date() + DAY, ("F3 not on the day after", variant, timing)
            tl = router_timeline("F2", variant, timing, base_date)
            assert tl["now"].date() == tl["anchor"].date(), ("F2 not one date", variant, timing)
        tl = router_timeline("F4", variant, "early", base_date)
        assert tl["now"].date() == tl["anchor"].date() + DAY and tl["now"].time() < FREEZE_START
        tl = router_timeline("F4", variant, "late", base_date)
        assert tl["now"].date() == tl["anchor"].date() + 2 * DAY
        tl = router_timeline("F1", variant, "early", base_date)
        assert tl["now"] - tl["ta"] < 10 * MIN and tl["now"].date() == tl["t0"].date()
        tl = router_timeline("F1", variant, "late", base_date)
        assert tl["now"] - tl["ta"] >= 10 * MIN and tl["now"] - tl["tc"] > tl["wait"]
    # Every clock line the router arm shows is at UTC+0 (the base date and D0 lie in
    # the GMT period), so the "UTC" times in the notes and the clock lines share one offset.
    for c in cells:
        if c["R"] == "R2":
            for variant in (1, 2, 3):
                for line in router_clock_lines(c, router_timeline(c["family"], variant, c["timing"], base_date)):
                    if "(UTC+0)" not in line:
                        problems.append("%s v%d: clock line not at UTC+0: %s" % (c["cell"], variant, line))
    return problems


def pair_key(c):
    """The matched pair a cell belongs to: same family, note form and timing; only R differs."""
    return (c["family"], c["N"], c["timing"])


# ---------------------------------------------------------------- clock reads by command (Claude Code arm)
# One rule for the runner and the scorer. A command counts as a clock read when it
# runs `date` as a command (also `TZ=UTC date`, `echo $(date)`, `x; date`), or when
# it succeeds and its output shows a time of day (`uptime`, `ls -l`, `stat` can).

_DATE_CMD_RX = re.compile(r"(?:^|[;&|(`]|\$\()\s*(?:env\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*date(?=\s|$|[;&|)`])")
TIME_OF_DAY_RX = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?!\d)")


def is_date_command(cmd):
    return bool(_DATE_CMD_RX.search((cmd or "").strip()))


def clock_read_kind(cmd, ok, output):
    """'date', 'time_in_output' or None for one shell command and its result."""
    if not ok:
        return None
    if is_date_command(cmd):
        return "date"
    if TIME_OF_DAY_RX.search(output or ""):
        return "time_in_output"
    return None


# ---------------------------------------------------------------- reply parsing
# The first parser (design time-use-1) took the first "DECISION:" anywhere in a
# line. The design check found 7 silent misparses in 26 awkward replies; this one
# replaces it. Rules:
# - text inside <think>...</think> is dropped (everything up to the last </think>);
# - a DECISION line must start the line (after markdown, a bullet or "Final");
#   "the answer is not DECISION: X" in running text is not one;
# - an option that is questioned ("WAIT? No"), negated ("TAKE_OVER is not allowed"),
#   or hedged ("NOT_YET / CANNOT_TELL", "3 or 12") gives no decision;
# - when several DECISION lines do not all give the same decision, no decision;
# - a line with more than one "DECISION:" (an echoed instruction) gives no decision;
# - F5: a number followed by "-", ":" or "." and a digit (a date, a time, a
#   fraction) or above 1000 gives no decision;
# - a DECISION line whose option is followed by another offered option keeps its
#   decision but says so in `how`; score.py lists those rows for hand reading.
# "No decision" rows are counted as unparsed and hand-read, never guessed.

_DEC_LINE_RX = re.compile(r"^[\s>*_#`\-+•]*(?:\d+[.)]\s*)?[*_`]*(?:final\s+)?[*_`]*DECISION[*_`\s]*[:：](.*)$",
                          re.I)
_LEAD = r"^[\s`*_\"'<\[(]+"
_TRAIL = r"^[`*_\"'>\])]+"
_END = r"(?![A-Za-z0-9])"


def _strip_think(text):
    low = text.lower()
    for tag in ("think", "thinking"):
        close, open_ = "</%s>" % tag, "<%s>" % tag
        if close in low:
            cut = low.rfind(close) + len(close)
            text, low = text[cut:], low[cut:]
        elif open_ in low:
            cut = low.find(open_)
            text, low = text[:cut], low[:cut]
    return text


def _option_rx(opt):
    return opt.replace("_", "[_ ]")


def _parse_one(rest, family):
    """Parse the text after one "DECISION:". Returns (decision or None, note)."""
    if re.search(r"DECISION\s*[*_`]*\s*[:：]", rest, re.I):
        return None, "several DECISION: on one line"
    tok = re.sub(_LEAD, "", rest)
    choices = [CANNOT] + (sorted(OPTIONS[family], key=len, reverse=True) if OPTIONS[family] else [])
    got, after = None, ""
    for opt in choices:
        m = re.match(_option_rx(opt) + _END, tok, re.I)
        if m:
            got, after = opt, tok[m.end():]
            break
    if got is None and family == "F5":
        m = re.match(r"(-?\d+)" + _END, tok)
        if m:
            nxt = tok[m.end():m.end() + 2]
            if re.match(r"[-:.]\d", nxt):
                return None, "number looks like a date, time or fraction: %r" % tok[:40]
            if abs(int(m.group(1))) > 1000:
                return None, "number too large for a day count: %r" % tok[:40]
            got, after = str(int(m.group(1))), tok[m.end():]
    if got is None:
        return None, ("not a number or CANNOT_TELL: %r" if family == "F5" else "option not offered: %r") % tok[:40]
    head = re.sub(_TRAIL, "", after).lstrip()
    if head.startswith("?"):
        return None, "option questioned: %r" % tok[:40]
    if re.match(r"(?:is|was|would be|seems)\s+(?:not|wrong|incorrect)\b|isn't\b|is n't\b", head, re.I):
        return None, "option negated: %r" % tok[:40]
    alt = re.match(r"(?:/|\||\bor\b|\band/or\b)\s*[`*_\"'<\[(]*\s*([A-Za-z_ ]+|-?\d+)", head, re.I)
    if alt:
        nxt = alt.group(1).strip()
        if family == "F5" and re.match(r"-?\d+$", nxt):
            return None, "hedged between answers: %r" % tok[:40]
        for opt in choices:
            if re.match(_option_rx(opt) + _END, nxt, re.I):
                return None, "hedged between options: %r" % tok[:40]
    note = ""
    if OPTIONS[family] and got != CANNOT:
        others = [o for o in OPTIONS[family] if o != got
                  and re.search(r"(?<![A-Za-z0-9_])" + _option_rx(o) + r"(?![A-Za-z0-9_])", after)]
        if others:
            note = "also names " + ", ".join(others)
    return got, note


def parse_decision(text, family):
    """(decision, how). decision is an offered option, a number string for F5, or None.

    `how` is "line" for one clean DECISION line; anything else says what was unusual.
    See the rules above."""
    if not text:
        return None, "no text"
    body = _strip_think(text)
    pre = "think block removed; " if body != text else ""
    lines = body.splitlines()
    found = []
    for i, line in enumerate(lines):
        m = _DEC_LINE_RX.match(line)
        if not m:
            continue
        rest = m.group(1)
        if not re.sub(r"[\s`*_\"']", "", rest):  # "DECISION:" alone; the answer is on the next line
            nxt = next((x for x in lines[i + 1:] if x.strip()), "")
            rest = nxt
        found.append(_parse_one(rest, family))
    if not found:
        return None, pre + "no DECISION line at the start of a line"
    decisions = [d for d, _ in found]
    if len(found) > 1 and (None in decisions or len(set(decisions)) > 1):
        return None, pre + "DECISION lines disagree: %s" % ", ".join(
            str(d) if d is not None else "(%s)" % n for d, n in found)
    d, note = found[0]
    if d is None:
        return None, pre + note
    how = "line" if len(found) == 1 else "%d DECISION lines, all %s" % (len(found), d)
    notes = sorted({n for _, n in found if n})
    return d, pre + how + ("; " + "; ".join(notes) if notes else "")


def how_needs_hand_check(how):
    """A parsed reply that a person should still read (another option on the DECISION line)."""
    return bool(how) and "also names" in how


if __name__ == "__main__":
    probs = check_table(ROUTER_BASE_DATE)
    print("router cells:", len(router_cells()), "claude cells:", len(claude_cells()))
    print("table vs mechanical problems at the base date %s: %d" % (ROUTER_BASE_DATE, len(probs)))
    for p in probs:
        print("  ", p)
