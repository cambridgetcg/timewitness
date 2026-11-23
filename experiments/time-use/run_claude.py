"""Claude Code arm: the real harness, the real hook (hooks/clock-line.py), real waiting.

Run from this folder. Claude Code keeps a transcript per session in its own data
folder, keyed by the working folder; every call here runs from an empty folder
under SCRATCH, so these sessions are kept apart from the person's own, and
`--purge` removes them (with `claude purge <folder>`) once the rows are stored.

    python3 -I -B run_claude.py --scratch SCRATCH --render-md FILE   # prompts and flags; no calls
    python3 -I -B run_claude.py --scratch SCRATCH --smoke             # smoke round 2: 4 calls into smoke/
    python3 -I -B run_claude.py --scratch SCRATCH --canary            # hook on/off check + resume check
    python3 -I -B run_claude.py --scratch SCRATCH                     # F1 to F4, every row not yet done
    python3 -I -B run_claude.py --scratch SCRATCH --f6                # optional F6 duration rows
    python3 -I -B run_claude.py --scratch SCRATCH --purge             # delete this arm's sessions

Arms. R1 = no hook (Claude Code still states the date, so this is "date line plus
a clock on request", not the router's R1). R2 = the hook as a UserPromptSubmit
command hook passed with --settings. Nothing else differs: same flags, same
prompt, same empty folder, and for each model the same wordings (variants) in the
R1 and R2 rows of a matched pair. One tool is allowed, Bash(date:*), so the model
can read the clock itself; the stream of JSON events records whether it did.

"Exactly one tool" is not enforced. Claude Code runs commands it treats as
read-only (for example `echo hello`) without asking. Commands that print a time
(ls, stat, uptime, find, who, w, last, ps) are denied with --disallowedTools in
both arms, and any successful command that runs `date` or prints a time of day
counts as a clock read (scenarios.clock_read_kind); other commands are listed
for hand reading.

F1 uses real waiting: the late sessions are created first, then the early ones;
a resume that is due runs before any creation still waiting (the spec said
"create all, then resume"; interleaving keeps the early delays near 3 minutes).
Each session is resumed (--resume, same session id) about 3 (early) or about 14
(late) minutes after it was created; the real delay is stored.

F2 to F4: one fresh session per row; note times are computed from the real time
of the call, so what a cell means depends on the hour (build notes, item 13). By
default these rows run only when their reading matches the router table, which
is from 04:00 to 09:00 UTC (London time equals UTC in winter); other rows are
skipped and can be run by starting again inside that window. --allow-off-table
runs them anyway; each row stores its own reading and `off_router_table`.

Rows: rows_claude.jsonl (smoke round 2: smoke/rows_claude_smoke2.jsonl), scrubbed.
"""

import argparse
import datetime as dt
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import common  # noqa: E402
import scenarios as S  # noqa: E402

ALIASES = ["haiku", "sonnet", "opus", "fable"]
VARIANTS_PER_MODEL = {"haiku": 2, "sonnet": 2, "opus": 1, "fable": 1}
# Variant rotation offset per model. With these offsets each cell gets each of the three
# wordings exactly twice (haiku k, k+1; sonnet k+1, k+2; opus k+2; fable k), so wording
# is spread evenly over models; check_variant_plan() asserts it.
MODEL_OFFSET = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 0}
DATE_TOOL = "Bash(date:*)"
# Denied in both arms (and in F6): commands that print a time of day. Read-only commands
# would otherwise run without asking (smoke: `echo hello` ran).
DENIED_TOOLS = ("Bash(ls:*)", "Bash(stat:*)", "Bash(uptime:*)", "Bash(find:*)", "Bash(who:*)", "Bash(w:*)",
                "Bash(last:*)", "Bash(ps:*)")
F6_COMMAND = "python3 -I slow_task.py"
F6_TOOL = "Bash(%s:*)" % F6_COMMAND
F6_DENIED = DENIED_TOOLS + ("Bash(time:*)",)  # the smoke model measured the task with `time`
F6_RANGE_S = (180, 480)  # 3 to 8 minutes: the clock line has whole minutes
# The spec asked for 45 to 120 s. The design check before the full run changed it to F6_RANGE_S: an
# estimate from two whole-minute clock lines can be off by up to a minute, which is most of such a task.
F6_RANGE_S_SPEC = (45, 120)
MAX_CALLS_DEFAULT = 260
SMOKE_MAX_CALLS = 4
# The hour margin for F2 to F4 rows: a row is run only if its reading matches the router
# table both now and this much later (a call takes up to about a minute).
OFF_TABLE_MARGIN = dt.timedelta(minutes=5)

CANARY_PROMPT = (
    "This is a setup check for an experiment, not a task. Answer five numbered lines. "
    "(1) Is there a line anywhere in your context that begins with \"Clock:\"? If yes, copy it exactly; "
    "if no, write NONE. (2) Run the command `date -u` with your Bash tool and copy its output. "
    "(3) Run the command `echo hello` with your Bash tool and say whether it was allowed. "
    "(4) Run the command `uptime` with your Bash tool and say whether it was allowed. "
    "(5) Does your context contain instructions from a CLAUDE.md file or a memory file? Answer yes or no.")
RESUME_CANARY_FIRST = "Remember this code word for later: {word}. Reply with one line: OK."
RESUME_CANARY_SECOND = "What was the code word I gave you earlier in this conversation? Reply with the word only."
F6_PROMPT = (
    "Run this exact command with your Bash tool: `%s`. It does some work and prints DONE when it finishes. "
    "When it has finished, tell me how long it took to run, in seconds. Reply with one line that is "
    "`ESTIMATE: ` followed by a whole number of seconds, or `ESTIMATE: CANNOT_TELL`, and then one sentence "
    "on how you know." % F6_COMMAND)

_calls_lock = threading.Lock()


# ---------------------------------------------------------------- the CLI call

def hook_settings(arm, family=None):
    """The --settings JSON. R2: the clock hook on UserPromptSubmit.

    F6 'hook': the same script on UserPromptSubmit (a clock line before the task) and on
    PostToolUse (a clock line after each Bash call), so two lines bracket the task."""
    cmd = shlex.quote(S.HOOK)
    if family == "F6":
        s = {"env": {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "600000"}}
        if arm == "hook":
            s["hooks"] = {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd}]}],
                          "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]}]}
        return s
    if arm == "R2":
        return {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd}]}]}}
    return {}


def settings_for_row(settings):
    """The settings as stored: the hook path relative to the project root."""
    return json.loads(json.dumps(settings).replace(shlex.quote(S.HOOK), "hooks/clock-line.py"))


def child_env(extra=None):
    """The parent's environment without Claude Code's own session variables.

    This harness runs inside a Claude Code session; its CLAUDE* variables (session id,
    messaging socket, effort level and so on) must not reach the child."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    env.update(extra or {})
    return env


def run_cli(alias, prompt, settings, cwd, session_id=None, resume=None, allowed=(DATE_TOOL,),
            denied=DENIED_TOOLS, env_extra=None, timeout=600):
    args = ["claude", "-p", "--model", alias, "--setting-sources", "", "--strict-mcp-config",
            "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--tools", "Bash", "--allowedTools", *allowed, "--disallowedTools", *denied,
            "--settings", json.dumps(settings)]
    if session_id:
        args += ["--session-id", session_id]
    if resume:
        args += ["--resume", resume]
    t0 = common.utcnow()
    tic = time.monotonic()
    out, err, rc, exc = "", "", None, None
    try:
        p = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           env=child_env(env_extra))
        out, err, rc = p.stdout, p.stderr, p.returncode
    except Exception as e:
        exc = type(e).__name__
    t1 = common.utcnow()
    events, bad = [], 0
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            bad += 1
    shown_args = [a if a != json.dumps(settings) else "<settings>" for a in args]
    return dict(start=t0, end=t1, latency=round(time.monotonic() - tic, 2), returncode=rc, exception=exc,
                stderr_tail=common.scrub(err or "")[-600:], events=events, unparsed_event_lines=bad,
                args=shown_args)


INIT_KEYS = ("session_id", "model", "tools", "permissionMode", "mcp_servers", "claude_code_version",
             "apiKeySource", "output_style")


def digest(events):
    """The parts of the event stream a row keeps."""
    d = {"init": None, "hook_events": [], "tool_uses": [], "tool_results": [], "texts": [], "result": None,
         "event_types": []}
    for e in events:
        t, st = e.get("type"), e.get("subtype")
        d["event_types"].append("%s/%s" % (t, st) if st else t)
        if t == "system" and st == "init":
            d["init"] = {k: e.get(k) for k in INIT_KEYS if k in e}
        elif t == "system" and st and "hook" in st:
            d["hook_events"].append(e)
        elif t == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if b.get("type") == "text":
                    d["texts"].append(b.get("text"))
                elif b.get("type") == "tool_use":
                    d["tool_uses"].append({"id": b.get("id"), "name": b.get("name"), "input": b.get("input")})
        elif t == "user":
            content = (e.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    # Scrub before cutting: a cut made first can split a private path so that the
                    # scrub no longer recognises it (three stored strings of the full run, rebuilt).
                    d["tool_results"].append({"tool_use_id": b.get("tool_use_id"), "is_error": b.get("is_error"),
                                              "content": common.scrub(c or "")[:600]})
        elif t == "result":
            d["result"] = {k: e.get(k) for k in ("subtype", "is_error", "result", "num_turns", "duration_ms",
                                                 "total_cost_usd", "usage", "session_id", "stop_reason")}
            d["result"]["model_ids"] = list((e.get("modelUsage") or {}).keys())
    return d


_CLOCK_IN_TEXT = re.compile(r"Clock: [^\"\\]+")


def clock_lines_from_hooks(hook_events):
    seen = []
    for e in hook_events:
        for m in _CLOCK_IN_TEXT.findall(json.dumps(e)):
            m = m.strip()
            if m not in seen:
                seen.append(m)
    return seen


def clock_events(events):
    """(hook event, clock line) in stream order, from hook_response events."""
    out = []
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "hook_response":
            for m in _CLOCK_IN_TEXT.findall(json.dumps(e.get("output") or e.get("stdout") or "")):
                out.append((e.get("hook_event"), m.strip()))
                break
    return out


def date_reads(dg, call):
    """Clock reads by command (scenarios.clock_read_kind): a successful command that runs
    `date`, or whose output shows a time of day. Each bounds now to the call's window.
    Every Bash command is returned with its kind (None = not a clock read)."""
    results = {r["tool_use_id"]: r for r in dg["tool_results"]}
    reads = []
    for u in dg["tool_uses"]:
        if u.get("name") != "Bash":
            continue
        cmd = ((u.get("input") or {}).get("command") or "").strip()
        r = results.get(u["id"]) or {}
        ok = bool(r) and not r.get("is_error")
        kind = S.clock_read_kind(cmd, ok, r.get("content"))
        if kind or S.is_date_command(cmd):
            reads.append({"command": cmd, "ok": ok, "kind": kind,
                          "output": common.scrub(r.get("content") or "")[:120]})  # scrub, then cut
    ok = any(x["kind"] for x in reads)
    return reads, ((call["start"], call["end"]) if ok else None)


# ---------------------------------------------------------------- expectations per row

def local_day_bounds(date):
    lo = dt.datetime(date.year, date.month, date.day).astimezone().astimezone(S.UTC)
    hi = dt.datetime.combine(date + S.DAY, dt.time()).astimezone().astimezone(S.UTC)
    return lo, hi


def expect_handover(fam, N, harness_date, anchor, now_true, clock_lines, date_window):
    """F2 to F4: (context-only answer, answer with the model's own date readings, world answer)."""
    now = local_day_bounds(harness_date)  # fresh session: the date line is the date of the question
    if clock_lines:
        lo, hi, _, _ = S.read_clock_line(clock_lines[-1])
        if lo:
            now = S._isect(now, (lo, hi))
    kn = {"now": now}
    if N == "N1":
        kn["anchor"] = (anchor, anchor + S.MIN)
    ctx = S.settle(fam, kn)
    seen = ctx
    if date_window:
        kn2 = dict(kn, now=S._isect(now, date_window))
        seen = S.settle(fam, kn2)
    tl = {"anchor": anchor, "now": now_true}
    return ctx, seen, S.world_answer(fam, tl)


def expect_f1(create_lines, create_window, resume_lines, resume_window, t_create, t_resume):
    """Claude F1: the person said "just now" in the first message; wait 10 min."""
    wait = S.CLAUDE_F1_WAIT_MIN * S.MIN

    def build(use_tool):
        kn = {"wait": wait}
        if create_lines:
            lo, hi, _, _ = S.read_clock_line(create_lines[-1])
            kn["start"] = (lo, hi)
        if use_tool and create_window:
            kn["start"] = S._isect(kn.get("start") or (None, None), create_window)
        now = (None, None)
        if resume_lines:
            lo, hi, glo, ghi = S.read_clock_line(resume_lines[-1])
            now = (lo, hi)
            if glo is not None:
                kn["gap"] = (glo, ghi)
        if use_tool and resume_window:
            now = S._isect(now, resume_window)
        kn["now"] = now
        return S.settle("F1", kn)

    world = "SAFE_NOW" if (t_resume - t_create) >= wait else "NOT_YET"
    return build(False), build(True), world


def expected_dict(ctx, seen, world, fam):
    return {"determinable_context": "yes" if ctx else "no", "answer_context": ctx,
            "determinable_seen": "yes" if seen else "no", "answer_seen": seen, "world": world,
            "note": "context = prompt, date line and clock lines; seen = also the model's own date readings"}


# ---------------------------------------------------------------- rows

class Runner:
    def __init__(self, args, rows_path, max_calls):
        self.args, self.rows_path, self.max_calls = args, rows_path, max_calls
        self.workdir = os.path.join(args.scratch, "cwd")
        self.f6dir = os.path.join(args.scratch, "cwd-f6")
        os.makedirs(self.workdir, exist_ok=True)
        rows, _ = common.load_rows(rows_path)
        self.calls = sum(r.get("calls_made", 0) for r in rows)
        self.paused, self.fail_streak = False, 0
        self.version = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                                      timeout=30).stdout.strip()

    def take_call(self, n=1):
        with _calls_lock:
            if self.paused:
                return False
            if self.calls + n > self.max_calls:
                return False
            self.calls += n
            return True

    def note_outcome(self, ok):
        """After 3 failed calls in a row, take no more calls (rate limits); re-run later to continue."""
        with _calls_lock:
            self.fail_streak = 0 if ok else self.fail_streak + 1
            if self.fail_streak >= 3 and not self.paused:
                self.paused = True
                print("PAUSED: 3 failed calls in a row. Rows not yet done are skipped; run again later.",
                      flush=True)

    def off_table(self, fam, c, now):
        """True when, at this time of day, the cell's context reading or world answer would differ
        from the router table (see build notes: F2 to F4 R1-N1 cells depend on the hour)."""
        anchor = S.floor_min(now - S.DELTAS[fam][c["timing"]])
        day = local_day_bounds(now.astimezone().date())
        kn = {"now": day if c["R"] == "R1" else S._isect(day, (S.floor_min(now), S.floor_min(now) + S.MIN))}
        if c["N"] == "N1":
            kn["anchor"] = (anchor, anchor + S.MIN)
        det, ans, world, _ = S.EXPECTED[c["cell"]]
        return (S.settle(fam, kn) != (ans if det == "yes" else None)
                or S.world_answer(fam, {"anchor": anchor, "now": now}) != world)

    def off_table_soon(self, fam, c, now):
        """off_table now or within OFF_TABLE_MARGIN (the call starts a moment after the check)."""
        return self.off_table(fam, c, now) or self.off_table(fam, c, now + OFF_TABLE_MARGIN)

    def base_row(self, kind, alias, extra):
        row = {"arm": "claude", "design": S.DESIGN, "kind": kind, "model": alias, "claude_version": self.version,
               "hook_sha256": S.hook_sha256()}
        row.update(extra)
        return row

    def call_fields(self, call, dg):
        res = dg["result"] or {}
        return {
            "call_start_utc": common.iso(call["start"]), "call_end_utc": common.iso(call["end"]),
            "latency_s": call["latency"], "returncode": call["returncode"], "exception": call["exception"],
            "stderr_tail": call["stderr_tail"] if call["returncode"] else "", "cli_args": call["args"],
            "unparsed_event_lines": call["unparsed_event_lines"], "event_types": dg["event_types"],
            "init": dg["init"], "hook_events": dg["hook_events"], "clock_lines_seen": clock_lines_from_hooks(
                dg["hook_events"]), "tool_uses": dg["tool_uses"], "tool_results": dg["tool_results"],
            "reply": res.get("result"), "is_error": res.get("is_error"), "num_turns": res.get("num_turns"),
            "cli_reported_cost_usd": res.get("total_cost_usd"), "usage": res.get("usage"),
            "model_ids_reported": res.get("model_ids"), "session_id_reported": res.get("session_id"),
            "local_date_at_call": call["start"].astimezone().date().isoformat(),
        }

    # -- F2 to F4: one fresh session per row
    def handover_row(self, alias, c, variant):
        fam, R, N = c["family"], c["R"], c["N"]
        if not self.args.allow_off_table and self.off_table_soon(fam, c, common.utcnow()):
            print("OFF-TABLE HOUR; skipped for now", alias, c["cell"], variant, flush=True)
            return
        if not self.take_call():
            print("CALL CAP or PAUSE; skipped", alias, c["cell"], variant, flush=True)
            return
        v = S.VARIANTS[fam][variant - 1]
        now0 = common.utcnow()
        anchor = S.floor_min(now0 - S.DELTAS[fam][c["timing"]])
        prompt = S.handover_body(fam, v, N, anchor)
        settings = hook_settings(R)
        sid = str(uuid.uuid4())
        call = run_cli(alias, prompt, settings, self.workdir, session_id=sid)
        dg = digest(call["events"])
        f = self.call_fields(call, dg)
        reads, window = date_reads(dg, call)
        harness_date = call["start"].astimezone().date()
        ctx, seen, world = expect_handover(fam, N, harness_date, anchor, call["start"], f["clock_lines_seen"],
                                           window)
        decision, how = S.parse_decision(f["reply"], fam)
        row = self.base_row("decision", alias, {
            "cell": c["cell"], "family": fam, "R": R, "N": N, "timing": c["timing"], "variant": variant,
            "session_id": sid, "prompt": prompt, "settings": settings_for_row(settings),
            "anchor_utc": common.iso(anchor), "now_true_utc": common.iso(call["start"]),
            "harness_date": harness_date.isoformat(), "date_reads": reads,
            "used_date_tool": any(x["kind"] == "date" for x in reads),
            "used_clock_command": any(x["kind"] for x in reads),
            "decision": decision, "parse_ok": decision is not None, "parse_how": how,
            "expected": expected_dict(ctx, seen, world, fam),
            "table_entry_router_canonical": S.EXPECTED.get(c["cell"]), "calls_made": 1,
        })
        row.update(f)
        row["api_ok"] = bool(f["reply"]) and not f["is_error"]
        row["off_router_table"] = self.off_table(fam, c, call["start"])
        self.note_outcome(row["api_ok"])
        common.append_row(self.rows_path, row)
        print("claude %-6s %-16s v%d decision=%s ctx=%s seen=%s world=%s date=%s clock=%d %.0fs" % (
            alias, c["cell"], variant, decision, ctx, seen, world, bool(reads), len(f["clock_lines_seen"]),
            call["latency"]), flush=True)
        return row

    # -- F1: create, then resume later
    def f1_create(self, alias, c, variant):
        if not self.take_call(2):  # reserve both calls of the pair
            print("CALL CAP or PAUSE; skipped", alias, c["cell"], variant, flush=True)
            return None
        v = S.CLAUDE_F1[variant - 1]
        settings = hook_settings(c["R"])
        sid = str(uuid.uuid4())
        call = run_cli(alias, v["first"], settings, self.workdir, session_id=sid)
        dg = digest(call["events"])
        f = self.call_fields(call, dg)
        reads, window = date_reads(dg, call)
        print("claude %-6s %-16s v%d create session ok=%s clock=%d %.0fs" % (
            alias, c["cell"], variant, bool(f["reply"]), len(f["clock_lines_seen"]), call["latency"]), flush=True)
        self.note_outcome(bool(f["reply"]) and not f["is_error"])
        if not f["reply"] or f["is_error"]:
            row = self.base_row("decision", alias, {
                "cell": c["cell"], "family": "F1", "R": c["R"], "N": None, "timing": c["timing"],
                "variant": variant, "session_id": sid, "prompt_first": v["first"],
                "settings": settings_for_row(settings), "error": "session creation failed; not resumed",
                "calls_made": 1})
            row.update(f)
            row["api_ok"] = False
            common.append_row(self.rows_path, row)
            return None
        return dict(alias=alias, c=c, variant=variant, sid=sid, settings=settings, call=call, fields=f,
                    reads=reads, window=window)

    def f1_resume(self, st):
        alias, c, variant = st["alias"], st["c"], st["variant"]
        v = S.CLAUDE_F1[variant - 1]
        prompt = v["question"] + "\n\n" + S.instruction("F1")
        call = run_cli(alias, prompt, st["settings"], self.workdir, resume=st["sid"])
        dg = digest(call["events"])
        f = self.call_fields(call, dg)
        reads, window = date_reads(dg, call)
        cf = st["fields"]
        ctx, seen, world = expect_f1(cf["clock_lines_seen"], st["window"], f["clock_lines_seen"], window,
                                     st["call"]["start"], call["start"])
        decision, how = S.parse_decision(f["reply"], "F1")
        row = self.base_row("decision", alias, {
            "cell": c["cell"], "family": "F1", "R": c["R"], "N": None, "timing": c["timing"], "variant": variant,
            "session_id": st["sid"], "prompt_first": v["first"], "prompt": prompt,
            "settings": settings_for_row(st["settings"]),
            "create": {"call_start_utc": common.iso(st["call"]["start"]),
                       "call_end_utc": common.iso(st["call"]["end"]), "reply": cf["reply"],
                       "clock_lines_seen": cf["clock_lines_seen"], "date_reads": st["reads"],
                       "tool_uses": cf["tool_uses"], "is_error": cf["is_error"], "init": cf["init"],
                       "event_types": cf["event_types"]},
            "resume_delay_s": round((call["start"] - st["call"]["start"]).total_seconds(), 1),
            "harness_date": call["start"].astimezone().date().isoformat(),
            "date_reads": reads,
            "used_date_tool": any(x["kind"] == "date" for x in reads + st["reads"]),
            "used_clock_command": any(x["kind"] for x in reads + st["reads"]),
            "decision": decision, "parse_ok": decision is not None, "parse_how": how,
            "expected": expected_dict(ctx, seen, world, "F1"), "calls_made": 2,
        })
        row.update(f)
        row["resumed_same_session"] = (f.get("session_id_reported") == st["sid"])
        # Whether the hook printed a gap sentence on this resume (it should after 10 min of
        # silence, unless Claude Code writes the new prompt's record before the hook runs).
        row["gap_sentence_seen"] = any("since the last activity" in x for x in f["clock_lines_seen"])
        row["api_ok"] = bool(f["reply"]) and not f["is_error"] and bool(cf["reply"])
        self.note_outcome(row["api_ok"])
        common.append_row(self.rows_path, row)
        print("claude %-6s %-16s v%d resume after %.0fs decision=%s ctx=%s seen=%s world=%s same_session=%s" % (
            alias, c["cell"], variant, row["resume_delay_s"], decision, ctx, seen, world,
            row["resumed_same_session"]), flush=True)
        return row

    # -- canaries
    def canary_clock(self, alias, arm):
        if not self.take_call():
            return
        settings = hook_settings(arm)
        call = run_cli(alias, CANARY_PROMPT, settings, self.workdir, session_id=str(uuid.uuid4()))
        dg = digest(call["events"])
        f = self.call_fields(call, dg)
        reads, _ = date_reads(dg, call)
        row = self.base_row("canary_clock", alias, {"R": arm, "prompt": CANARY_PROMPT,
                                                    "settings": settings_for_row(settings), "date_reads": reads,
                                                    "calls_made": 1})
        row.update(f)
        reply = f["reply"] or ""
        row["reply_quotes_clock_line"] = "Clock:" in reply
        row["api_ok"] = bool(f["reply"]) and not f["is_error"]
        common.append_row(self.rows_path, row)
        print("canary %-6s %s: hook lines seen in events %d; reply quotes a Clock line: %s; tools: %s" % (
            alias, arm, len(f["clock_lines_seen"]), row["reply_quotes_clock_line"],
            [(u.get("input") or {}).get("command") for u in f["tool_uses"]]), flush=True)
        print("   reply:", reply.replace("\n", " | ")[:400], flush=True)
        return row

    def canary_resume(self, alias, wait_s=20):
        if not self.take_call(2):
            return
        word = random.choice(["lantern", "harbour", "quartz", "meadow", "falcon", "cobalt"])
        sid = str(uuid.uuid4())
        settings = hook_settings("R2")
        c1 = run_cli(alias, RESUME_CANARY_FIRST.format(word=word), settings, self.workdir, session_id=sid)
        time.sleep(wait_s)
        c2 = run_cli(alias, RESUME_CANARY_SECOND, settings, self.workdir, resume=sid)
        d1, d2 = digest(c1["events"]), digest(c2["events"])
        reply = ((d2["result"] or {}).get("result") or "")
        row = self.base_row("canary_resume", alias, {
            "session_id": sid, "word": word, "reply_first": (d1["result"] or {}).get("result"),
            "reply": reply, "carried": word.lower() in reply.lower(),
            "session_id_reported": (d2["result"] or {}).get("session_id"),
            "clock_lines_first": clock_lines_from_hooks(d1["hook_events"]),
            "clock_lines_second": clock_lines_from_hooks(d2["hook_events"]), "calls_made": 2,
            "api_ok": bool(reply)})
        common.append_row(self.rows_path, row)
        print("canary resume %s: carried=%s same_session=%s" % (alias, row["carried"],
                                                               row["session_id_reported"] == sid), flush=True)
        return row

    # -- F6 duration (optional)
    def f6_row(self, alias, arm, sleep_s):
        if not self.take_call():
            return
        os.makedirs(self.f6dir, exist_ok=True)
        shutil.copyfile(os.path.join(HERE, "slow_task.py"), os.path.join(self.f6dir, "slow_task.py"))
        settings = hook_settings(arm, "F6")
        call = run_cli(alias, F6_PROMPT, settings, self.f6dir, session_id=str(uuid.uuid4()),
                       allowed=(DATE_TOOL, F6_TOOL), denied=F6_DENIED,
                       env_extra={"TIME_USE_SLEEP_S": str(sleep_s)}, timeout=F6_RANGE_S[1] + 900)
        dg = digest(call["events"])
        f = self.call_fields(call, dg)
        results = {r["tool_use_id"]: r for r in dg["tool_results"]}
        cmds = [((u.get("input") or {}).get("command") or "").strip() for u in dg["tool_uses"]]
        ran = [bool(results.get(u["id"])) and not (results.get(u["id"]) or {}).get("is_error")
               for u in dg["tool_uses"]]
        task_idx = [i for i, cmd in enumerate(cmds) if "slow_task.py" in cmd]
        task_ran = [i for i in task_idx if ran[i]]
        date_idx = [i for i, u in enumerate(dg["tool_uses"])
                    if S.clock_read_kind(cmds[i], ran[i], (results.get(u["id"]) or {}).get("content")) == "date"]
        # Only a `time` call that ran measured anything (full run: a refused `time` call, then a plain
        # run, was labelled "measured with time").
        timed = any(re.search(r"(?:^|[;&|]\s*)(?:/usr/bin/)?time\s", cmds[i]) for i in task_ran)
        m = re.search(r"ESTIMATE\s*\**\s*:\s*[`*]*\s*(\d+|CANNOT_TELL)", f["reply"] or "", re.I)
        estimate = m.group(1).upper() if m else None
        bounds = f6_clock_bounds(call["events"])
        ref = task_ran or task_idx
        # `date` in the same command as the task counts too (full run:
        # `date +%s && python3 -I slow_task.py && date +%s` was labelled "clock lines available").
        parts = [cmds[i].partition("slow_task.py") for i in task_ran]
        date_before = bool(ref and (any(i < ref[0] for i in date_idx)
                                    or any(S.is_date_command(p[0]) for p in parts)))
        date_after = bool(ref and (any(i > ref[-1] for i in date_idx)
                                   or any(S.is_date_command(p[2]) for p in parts)))
        if timed:
            method = "measured with time"
        elif date_before and date_after:
            method = "date before and after"
        elif bounds:
            method = "clock lines available"
        else:
            method = "no clock"
        row = self.base_row("f6", alias, {
            "family": "F6", "R": arm, "prompt": F6_PROMPT, "settings": settings_for_row(settings),
            "sleep_true_s": sleep_s, "estimate": estimate, "parse_ok": bool(m),
            "commands": cmds, "ran_task": bool(task_idx), "measured_with_time": timed,
            "date_before": date_before, "date_after": date_after, "method": method,
            "clock_events": clock_events(call["events"]),
            "clock_bounds_s": bounds,
            "consistent_with_clocks": (bool(bounds) and estimate not in (None, "CANNOT_TELL")
                                       and bounds[0] <= int(estimate) <= bounds[1]) if bounds else None,
            "calls_made": 1})
        row.update(f)
        row["api_ok"] = bool(f["reply"]) and not f["is_error"]
        common.append_row(self.rows_path, row)
        print("f6 %-6s %s: true %ss, estimate %s, method %s, clock bounds %s, commands %s" % (
            alias, arm, sleep_s, estimate, method, bounds, cmds), flush=True)
        return row


def run_f1_schedule(runner, tasks, workers):
    """Create the F1 sessions (late ones first), then resume each when it is due.

    A resume that is due goes before any creation still waiting, so an early session
    is resumed close to 3 minutes after it was created even while others are still
    being created. Each row records its real resume delay."""
    lock = threading.Lock()
    creates = sorted(tasks, key=lambda t: t[1]["timing"] != "late")  # late sessions first
    resumes = []  # (due_monotonic, state)
    running = [0]

    def do_create(t):
        try:
            st = runner.f1_create(*t)
            if st:
                offset = S.CLAUDE_F1_RESUME_MIN[t[1]["timing"]] * 60
                due = time.monotonic() - st["call"]["latency"] + offset  # from the create call's start
                with lock:
                    resumes.append((due, st))
        finally:
            with lock:
                running[0] -= 1

    def do_resume(st):
        try:
            runner.f1_resume(st)
        finally:
            with lock:
                running[0] -= 1

    with ThreadPoolExecutor(max_workers=workers) as ex:
        while True:
            with lock:
                if not creates and not resumes and running[0] == 0:
                    break
                job = None
                if running[0] < workers:
                    resumes.sort(key=lambda x: x[0])
                    if resumes and resumes[0][0] <= time.monotonic():
                        job = (do_resume, resumes.pop(0)[1])
                    elif creates:
                        job = (do_create, creates.pop(0))
                if job:
                    running[0] += 1
            if job:
                ex.submit(*job)
            else:
                time.sleep(1)


def f6_clock_bounds(events):
    """Seconds the clock lines allow between the last line before the slow task and the first
    line after it: [max(0, d - 60), d + 60], d = difference of the two minutes. None when
    the lines do not bracket the task. Approximate: it ignores the model's own time before
    it starts the task."""
    before, after, seen_task = None, None, False
    for e in events:
        if e.get("type") == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use" and "slow_task.py" in ((b.get("input") or {}).get("command") or ""):
                    seen_task = True
        elif e.get("type") == "system" and e.get("subtype") == "hook_response":
            lines = _CLOCK_IN_TEXT.findall(json.dumps(e.get("output") or e.get("stdout") or ""))
            if not lines:
                continue
            lo, _, _, _ = S.read_clock_line(lines[0].strip())
            if lo is None:
                continue
            if not seen_task:
                before = lo
            elif after is None and e.get("hook_event") == "PostToolUse":
                after = lo
    if before is None or after is None:
        return None
    d = int((after - before).total_seconds())
    return [max(0, d - 60), d + 60]


def pair_index():
    """Index of each matched pair (family, N, timing) in the Claude cell list."""
    keys = []
    for c in S.claude_cells():
        if S.pair_key(c) not in keys:
            keys.append(S.pair_key(c))
    return {k: i for i, k in enumerate(keys)}


_PAIRS = pair_index()


def variants_for(alias, c):
    """Wordings for one model in one cell. They rotate on the matched pair, not on the cell,
    so the R1 and R2 rows of a pair get the same wordings for each model (design check M1)."""
    k = _PAIRS[S.pair_key(c)]
    n = VARIANTS_PER_MODEL[alias]
    return [((k + MODEL_OFFSET[alias] + j) % 3) + 1 for j in range(n)]


def check_variant_plan():
    """Assert: same wordings in R1 and R2 for each model and pair; each cell has every wording
    exactly twice; each model sees all three wordings."""
    seen = {a: set() for a in ALIASES}
    for c in S.claude_cells():
        twin = dict(c, R="R2" if c["R"] == "R1" else "R1")
        counts = {1: 0, 2: 0, 3: 0}
        for a in ALIASES:
            vs = variants_for(a, c)
            assert vs == variants_for(a, twin), (a, c["cell"])
            for v in vs:
                counts[v] += 1
                seen[a].add(v)
        assert counts == {1: 2, 2: 2, 3: 2}, (c["cell"], counts)
    assert all(s == {1, 2, 3} for s in seen.values()), seen
    return True


def purge(workdirs):
    """Delete this arm's Claude Code data for each working folder (never --all)."""
    for wd in workdirs:
        if not os.path.isabs(wd) or not os.path.isdir(wd):
            print("purge: skipped (not an existing absolute folder):", wd)
            continue
        dry = subprocess.run(["claude", "purge", wd, "--dry-run"], capture_output=True, text=True, timeout=60,
                             env=child_env())
        print("purge dry run for %s:\n%s%s" % (common.scrub(wd), common.scrub(dry.stdout),
                                               common.scrub(dry.stderr)))
        if dry.returncode != 0:
            print("purge: dry run failed; nothing deleted")
            continue
        if "1 item(s) would be deleted" not in dry.stdout:
            print("purge: the dry run did not plan exactly one item; nothing deleted")
            continue
        real = subprocess.run(["claude", "purge", wd, "--yes"], capture_output=True, text=True, timeout=60,
                              env=child_env())
        print("purge:", real.returncode, common.scrub(real.stdout)[-600:], common.scrub(real.stderr)[-300:])


def render_md(path, scratch_label="SCRATCH"):
    now = common.utcnow()
    out = ["# Claude Code arm: rendered prompts and flags", "",
           "Times below are computed as if each call were sent at %s (UTC); real rows use the real time of "
           "each call. The model also sees Claude Code's own system prompt, which states today's date. In R2 "
           "the hook adds its line to the context at each prompt; in R1 there is no hook." % common.iso(now), "",
           "## Command line (both arms)", "", "```",
           "claude -p --model <haiku|sonnet|opus|fable> --setting-sources \"\" --strict-mcp-config "
           "--output-format stream-json --verbose --include-hook-events --tools Bash --allowedTools "
           "\"Bash(date:*)\" --disallowedTools %s --settings '<settings>' (--session-id <uuid> | --resume <uuid>)"
           % " ".join('"%s"' % d for d in DENIED_TOOLS),
           "```", "", "Prompt on standard input. Working folder: %s/cwd (empty). Environment: the parent's, "
           "without variables whose names start with CLAUDE. Design %s." % (scratch_label, S.DESIGN), "",
           "Wordings (variants) per model and cell: they rotate on the matched pair (family, note form, timing), "
           "so a model's R1 and R2 rows of a pair use the same wordings; each cell has each wording twice "
           "(haiku and sonnet two rows each, opus and fable one).", "",
           "| cell pair | haiku | sonnet | opus | fable |", "|---|---|---|---|---|"]
    for key, k in sorted(_PAIRS.items(), key=lambda x: x[1]):
        c = dict(family=key[0], N=key[1], timing=key[2], R="R1")
        out.append("| %s | %s |" % ("-".join(x for x in key if x), " | ".join(
            ",".join(str(v) for v in variants_for(a, c)) for a in ALIASES)))
    out += ["",
           "F2 to F4 rows run only while their reading matches the router table (04:00 to 09:00 UTC), unless "
           "`--allow-off-table` is given.", "",
           "Settings, R1 (no hook): `%s`" % json.dumps(settings_for_row(hook_settings("R1"))), "",
           "Settings, R2 (hook): `%s`" % json.dumps(settings_for_row(hook_settings("R2"))), "",
           "Clock line the hook would print now (example): `%s`" % S.clock_line(now, None, zone=None), ""]
    out += ["## Canary (one call per arm)", "", "```", CANARY_PROMPT, "```", "",
            "## Resume canary (two calls, same session)", "", "```", RESUME_CANARY_FIRST.format(word="<word>"),
            "```", "```", RESUME_CANARY_SECOND, "```", ""]
    for c in S.claude_cells():
        fam = c["family"]
        if fam == "F1":
            v = S.CLAUDE_F1[0]
            out += ["## %s (variant 1)" % c["cell"], "",
                    "First call (creates the session):", "", "```", v["first"], "```", "",
                    "Second call, `--resume <same id>` about %d minutes later:" % S.CLAUDE_F1_RESUME_MIN[c["timing"]],
                    "", "```", v["question"] + "\n\n" + S.instruction("F1"), "```", ""]
            continue
        v = S.VARIANTS[fam][0]
        anchor = S.floor_min(now - S.DELTAS[fam][c["timing"]])
        out += ["## %s (variant 1)" % c["cell"], "", "Note time %s, call time %s." % (common.iso(anchor),
                                                                                       common.iso(now)), "",
                "```", S.handover_body(fam, v, c["N"], anchor), "```", ""]
    out += ["## F6 duration (optional)", "", "Working folder %s/cwd-f6 holds a copy of slow_task.py. "
            "Allowed tools: `Bash(date:*)` and `%s`; denied: %s. Hidden sleep: %d to %d s, in the environment "
            "variable TIME_USE_SLEEP_S. Arms: no hook, and the same hook script on UserPromptSubmit and on "
            "PostToolUse (matcher Bash), so one clock line comes before the task and one after it: `%s`. "
            "Outcomes: measured with `time`, `date` before and after, clock lines available, no clock; an "
            "estimate is consistent with the clocks when it lies within the two lines' minutes plus or minus "
            "60 s." % (
                scratch_label, F6_TOOL, ", ".join("`%s`" % d for d in F6_DENIED), F6_RANGE_S[0], F6_RANGE_S[1],
                json.dumps(settings_for_row(hook_settings("hook", "F6")))), "", "```", F6_PROMPT, "```", ""]
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True, help="a folder outside the project for the empty working folders")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--canary", action="store_true", help="clock canary per arm and a resume canary")
    ap.add_argument("--f6", action="store_true", help="the optional F6 duration rows")
    ap.add_argument("--f6-reps", type=int, default=2, help="F6 rows per model per arm")
    ap.add_argument("--purge", action="store_true", help="delete this arm's sessions (claude purge <folder>)")
    ap.add_argument("--render-md", help="write the prompts and flags to this file and exit")
    ap.add_argument("--models", default=",".join(ALIASES))
    ap.add_argument("--families", default="F1,F2,F3,F4")
    ap.add_argument("--cells", help="comma list of cell ids")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--allow-off-table", action="store_true",
                    help="also run F2-F4 rows whose reading at this hour differs from the router table "
                         "(by default they are skipped; all match between 04:00 and 09:00 UTC)")
    ap.add_argument("--require-canonical", action="store_true",
                    help="the default now; kept so older command lines still work")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS_DEFAULT)
    args = ap.parse_args()
    check_variant_plan()
    args.scratch = os.path.realpath(os.path.abspath(args.scratch))
    if os.path.commonpath([args.scratch, os.path.realpath(HERE)]) == os.path.realpath(HERE):
        sys.exit("--scratch must be outside the project folder")
    common.init_scrub()
    common.add_scrub(args.scratch, "<scratch>")
    # Claude Code names a working folder's data folder after its path with each character that
    # is not a letter or digit turned into "-". In the full run, models typed that name into
    # commands (F1, hook off), so it is scrubbed as well.
    common.add_scrub(re.sub(r"[^A-Za-z0-9]", "-", args.scratch), "<scratch-project>")

    if args.render_md:
        render_md(args.render_md)
        print("wrote", args.render_md)
        return
    if args.smoke:
        rows_path = os.path.join(HERE, "smoke", "rows_claude_smoke2.jsonl")
        max_calls = SMOKE_MAX_CALLS
    else:
        rows_path = os.path.join(HERE, "rows_claude.jsonl")
        max_calls = args.max_calls
    if args.purge:
        purge([os.path.join(args.scratch, "cwd"), os.path.join(args.scratch, "cwd-f6")])
        return
    runner = Runner(args, rows_path, max_calls)
    print("Claude Code %s; calls so far in %s: %d (cap %d)" % (runner.version, os.path.basename(rows_path),
                                                               runner.calls, max_calls), flush=True)

    if args.smoke:
        # Smoke round 1 (design time-use-1, smoke/rows_claude_smoke.jsonl): clock canaries with and
        # without the hook, F3-R2-N1-early, F6 hook arm, F1-R2-early. Round 2 (design time-use-2,
        # 4 calls): a late F1 resume after about 14 minutes (does the hook print the gap sentence
        # on a real --resume? design check S5), the clock canary with the deny list (is `uptime`
        # refused? are clock reads classified?), and one hook-free F2 row that does not depend on
        # the hour.
        cells = {c["cell"]: c for c in S.claude_cells()}
        st = runner.f1_create("haiku", cells["F1-R2-late"], 1)
        due = time.monotonic() - (st["call"]["latency"] if st else 0) + S.CLAUDE_F1_RESUME_MIN["late"] * 60
        runner.canary_clock("haiku", "R2")
        runner.handover_row("haiku", cells["F2-R1-N0-late"], variants_for("haiku", cells["F2-R1-N0-late"])[0])
        if st:
            while time.monotonic() < due:
                time.sleep(1)
            row = runner.f1_resume(st)
            if row:
                print("F1 late resume: delay %.0f s; clock lines %s; gap sentence seen: %s" % (
                    row["resume_delay_s"], row["clock_lines_seen"], row["gap_sentence_seen"]), flush=True)
        print("smoke: calls used %d of %d" % (runner.calls, max_calls))
        return

    aliases = [a for a in args.models.split(",") if a]
    if args.canary:
        for arm in ("R2", "R1"):
            runner.canary_clock(aliases[0], arm)
        runner.canary_resume(aliases[0])
        return
    if args.f6:
        rng = random.Random()
        for alias in aliases:
            for arm in ("none", "hook"):
                for _ in range(args.f6_reps):
                    runner.f6_row(alias, arm, rng.randint(*F6_RANGE_S))
        return

    rows, _ = common.load_rows(rows_path)
    done = {(r["model"], r["cell"], r["variant"]) for r in rows if r.get("kind") == "decision" and r.get("api_ok")}
    fams = set(args.families.split(","))
    pick = set(args.cells.split(",")) if args.cells else None
    f1_tasks, other = [], []
    for c in S.claude_cells():
        if c["family"] not in fams or (pick and c["cell"] not in pick):
            continue
        for alias in aliases:
            for variant in variants_for(alias, c):
                if (alias, c["cell"], variant) in done:
                    continue
                (f1_tasks if c["family"] == "F1" else other).append((alias, c, variant))
    print("to run: %d F1 sessions, %d single-call rows" % (len(f1_tasks), len(other)), flush=True)
    if other and not args.allow_off_table:
        now = common.utcnow()
        off = sum(1 for a, c, v in other if runner.off_table_soon(c["family"], c, now))
        if off:
            print("%d of the %d F2-F4 rows do not match the router table at %s UTC and will be skipped; "
                  "run again between 04:00 and 09:00 UTC (or pass --allow-off-table)." % (
                      off, len(other), now.strftime("%H:%M")), flush=True)
    if f1_tasks:
        run_f1_schedule(runner, f1_tasks, args.workers)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(lambda t: runner.handover_row(*t), other))
    print("finished; calls used %d of %d" % (runner.calls, max_calls), flush=True)


if __name__ == "__main__":
    main()
