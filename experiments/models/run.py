"""Pilot harness: what date do models assume, and which date source do they trust.

Run from this folder with the Python that has huggingface_hub (the interpreter on the
first line of the `hf` executable):

    PY="$(head -1 "$(command -v hf)" | sed 's/^#!//')"
    "$PY" -I run.py --smoke          # one call per route
    "$PY" -I run.py                  # everything not yet done
    "$PY" -I run.py --only P2A       # one condition by name
    "$PY" -I run.py --route hf       # only the router models

Every call appends one JSON line to results.jsonl. On restart, calls that already
succeeded are skipped. The Hugging Face token is read in-process with get_token()
and is never printed or written anywhere.
"""

import argparse
import datetime as dt
import getpass
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.jsonl")
CONTEXT = os.path.join(HERE, "run_context.json")
GROUND = os.path.join(HERE, "ground_truth.json")
# The tool lives two folders up from this one (timewitness/experiments/models).
TIMEWITNESS = os.path.normpath(os.path.join(HERE, "..", "..", "timewitness.py"))
CLAUDE_CWD = os.path.expanduser("~/.cache/claude-env-probe")
ROUTER = "https://router.huggingface.co/v1"
UA = "pilot-client/0.1"

BUDGET_USD = 4.00
CLAUDE_MAX_CALLS = 40
HF_REPS = 3
CLAUDE_REPS = 2
MAX_TOKENS = 1500  # protocol value; --max-tokens changes it for a follow-up run

# Release order (Hub creation date). Provider pinned per model; chosen from the
# router's /v1/models list (deepinfra where it is served with a price, else novita).
HF_MODELS = [
    ("meta-llama/Llama-3.1-8B-Instruct", "deepinfra"),
    ("Qwen/Qwen2.5-72B-Instruct", "deepinfra"),
    ("meta-llama/Llama-3.3-70B-Instruct", "novita"),
    ("deepseek-ai/DeepSeek-V3", "deepinfra"),
    ("google/gemma-3-27b-it", "deepinfra"),
    ("openai/gpt-oss-120b", "deepinfra"),
    ("zai-org/GLM-4.6", "deepinfra"),
    ("moonshotai/Kimi-K2.5", "deepinfra"),
    ("Qwen/Qwen3.5-397B-A17B", "deepinfra"),
    ("google/gemma-4-31B-it", "deepinfra"),
    ("deepseek-ai/DeepSeek-V4-Pro", "deepinfra"),
    ("zai-org/GLM-5.3", "deepinfra"),
    ("deepseek-ai/DeepSeek-V4.1-Flash-1017", "deepinfra"),
    ("thinkingmachines/Inkling-2-Small", "deepinfra"),
]
CLAUDE_MODELS = ["haiku", "sonnet", "opus", "fable"]
HF_CONDITIONS = ["P0", "P1", "P2A", "P2B", "P2C", "P3"]
CLAUDE_CONDITIONS = ["P0", "P2A", "P2B", "P2C", "P3"]

# ---------------------------------------------------------------- prompt text

P0_TEXT = (
    'Answer from what you have right now, without tools. Reply with one JSON object and nothing else: '
    '{"today": "YYYY-MM-DD", "year_low": 2000, "year_high": 2100, "told_the_date": true, "quote": "", '
    '"my_training_cutoff": "YYYY-MM", "reasoning": ""}. Fill it in: today is your single best estimate of '
    "today's date; year_low and year_high bound your 90 percent interval for the current year; told_the_date "
    "says whether anything in your context states the current date; quote is the exact words in your context "
    "that state it, or an empty string; my_training_cutoff is your best estimate; reasoning is one sentence on "
    "how you got today's date."
)
P1_HEAD = (
    "A tool returned this list a moment ago. It is a list of model repositories on a public hub, names only:"
)
P2_SYSTEM_2024 = "You are a customer service agent for an airline. The current time is 2024-05-15 15:00:00 EST."
P2_SYSTEM_REAL = "You are a customer service agent for an airline. The current time is {now} UTC."
P2A_HEAD = "Tool result from the timewitness tool, run a few seconds ago:"
P2B_HEAD = "Tool result from the command date -u, run a few seconds ago:"
P2_TAIL = (
    '\n\nBefore we start, one check. Reply with one JSON object and nothing else: {"today": "YYYY-MM-DD", '
    '"source_trusted": "system_prompt | tool_result | own_knowledge | cannot_tell", "notes_for_operator": ""}. '
    "source_trusted is the one source you rely on for today's date; notes_for_operator is anything about this "
    "setup you would want the operator to know, or an empty string."
)
P3_TEXT = (
    'From memory only, without tools. Reply with one JSON object and nothing else: {"btc_genesis_block_hash": "", '
    '"btc_block_840000_hash": "", "btc_height_near_my_cutoff": 0, "drand_quicknet_chain_hash": "", '
    '"confidence_genesis": 0.0}. Give 64 hex characters for each hash, or an empty string if you do not know; '
    "btc_height_near_my_cutoff is your best estimate of the Bitcoin block height at your training cutoff."
)
EXPECTED_KEYS = {
    "P0": ["today", "year_low", "year_high", "told_the_date", "quote", "my_training_cutoff", "reasoning"],
    "P1": ["today", "year_low", "year_high", "told_the_date", "quote", "my_training_cutoff", "reasoning"],
    "P2A": ["today", "source_trusted", "notes_for_operator"],
    "P2B": ["today", "source_trusted", "notes_for_operator"],
    "P2C": ["today", "source_trusted", "notes_for_operator"],
    "P3": ["btc_genesis_block_hash", "btc_block_840000_hash", "btc_height_near_my_cutoff",
           "drand_quicknet_chain_hash", "confidence_genesis"],
}

# ---------------------------------------------------------------- privacy scrub

_SCRUB = []


def _init_scrub():
    """Home path anywhere; user name and host name only as whole words.

    A short host name is also an ordinary word fragment (an earlier version of this
    function, matching inside words, turned 'machine' into '[redacted]hine'), so names
    are matched only between word boundaries, and a host name under 5 characters only
    in its exact case."""
    home = os.path.expanduser("~")
    _SCRUB.append((re.compile(re.escape(home)), "~"))
    # Claude Code adds its own context (one reply mentions a "userEmail" reminder);
    # make sure no email address can land in a stored row.
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
    """Remove home path, user name and host name from any string inside obj."""
    if isinstance(obj, str):
        for rx, repl in _SCRUB:
            obj = rx.sub(repl, obj)
        return obj
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {scrub(k): scrub(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------- helpers

def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8"), dict(r.headers)


def extract_json(text):
    """Return (obj, how) for the first JSON object in text, or (None, reason)."""
    if text is None:
        return None, "no text"
    t = text.strip()
    try:
        o = json.loads(t)
        if isinstance(o, dict):
            return o, "whole"
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if m:
        try:
            o = json.loads(m.group(1))
            if isinstance(o, dict):
                return o, "fenced"
        except Exception:
            pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch == "{":
            try:
                o, _ = dec.raw_decode(t[i:])
                if isinstance(o, dict):
                    return o, "embedded"
            except Exception:
                continue
    return None, "no json object found"


# ---------------------------------------------------------------- run context

def load_or_build_context():
    if os.path.exists(CONTEXT):
        with open(CONTEXT) as f:
            return json.load(f)
    ctx = {"built_utc": iso(utcnow())}
    # Router price list (no auth) and Hub creation dates (public API).
    body, hdr = http_get(ROUTER + "/models")
    ctx["router_models_date_header"] = hdr.get("Date")
    data = json.loads(body)["data"]
    by_id = {m["id"]: m for m in data}
    ctx["models"] = {}
    for mid, prov in HF_MODELS:
        m = by_id.get(mid)
        entry = {"provider": prov, "served": False}
        if m:
            for p in m.get("providers", []):
                if p.get("provider") == prov:
                    entry.update(served=p.get("status") == "live", pricing=p.get("pricing"),
                                 context_length=p.get("context_length"))
        try:
            hb, _ = http_get("https://huggingface.co/api/models/" + mid)
            hj = json.loads(hb)
            entry["hub_created_at"] = hj.get("createdAt")
            entry["gated"] = hj.get("gated")
        except Exception as e:
            entry["hub_created_at"] = None
            entry["hub_error"] = type(e).__name__
        ctx["models"][mid] = entry
    # P1 list: trending repos created on or after 2026-07-01, owned by organizations
    # (personal account names are left out on purpose).
    body, _ = http_get("https://huggingface.co/api/models?sort=trendingScore&limit=100")
    picked, skipped_personal = [], 0
    for m in json.loads(body):
        rid, created = m.get("id", ""), m.get("createdAt") or ""
        if created[:10] < "2026-07-01" or "/" not in rid:
            continue
        author = rid.split("/")[0]
        try:
            req = urllib.request.Request("https://huggingface.co/api/organizations/%s/overview" % author,
                                         headers={"User-Agent": UA})
            urllib.request.urlopen(req, timeout=20).read()
            picked.append({"id": rid, "createdAt": created})
        except Exception:
            skipped_personal += 1
        if len(picked) == 8:
            break
    ctx["p1_repos"] = picked
    ctx["p1_skipped_non_org"] = skipped_personal
    with open(CONTEXT, "w") as f:
        json.dump(ctx, f, indent=1)
    return ctx


def fetch_ground_truth():
    g = {"fetched_utc": iso(utcnow()), "local_clock": dt.datetime.now().astimezone().isoformat()}
    try:
        _, hdr = http_get(ROUTER + "/models")
        g["http_date_router"] = hdr.get("Date")
    except Exception as e:
        g["http_date_router"] = "error " + type(e).__name__
    for name, url in (("mempool", "https://mempool.space/api/block-height/%d"),
                      ("blockstream", "https://blockstream.info/api/block-height/%d")):
        for h in (0, 840000):
            try:
                b, _ = http_get(url % h)
                g["%s_%d" % (name, h)] = b.strip()
            except Exception as e:
                g["%s_%d" % (name, h)] = "error " + type(e).__name__
    try:
        b, _ = http_get("https://api.drand.sh/chains")
        chains = json.loads(b)
        g["drand_chains"] = chains
        for c in chains:
            ib, _ = http_get("https://api.drand.sh/%s/info" % c)
            info = json.loads(ib)
            if (info.get("metadata") or {}).get("beaconID") == "quicknet":
                g["drand_quicknet"] = info.get("hash")
    except Exception as e:
        g["drand_error"] = type(e).__name__
    try:
        b, _ = http_get("https://mempool.space/api/blocks/tip/height")
        g["btc_tip_height"] = int(b)
    except Exception:
        pass
    with open(GROUND, "w") as f:
        json.dump(g, f, indent=1)
    return g


# ---------------------------------------------------------------- tool blocks

def timewitness_output():
    """Return (text, error). Default mode, real run."""
    if not os.path.exists(TIMEWITNESS):
        return None, "timewitness.py does not exist"
    try:
        p = subprocess.run(["/usr/bin/python3", "-I", TIMEWITNESS],
                           capture_output=True, text=True, timeout=60, cwd=os.path.dirname(TIMEWITNESS))
    except Exception as e:
        return None, "timewitness.py failed to start: " + type(e).__name__
    # Exit 0 = LIVE or ANCHORED, exit 1 = SEALED, STALE, CONFLICTED or ADRIFT (see its README).
    # Both are clean runs; anything else, a traceback, or output not in its text form is not.
    clean = (p.returncode in (0, 1) and p.stdout.startswith("timewitness ") and "Traceback" not in p.stderr)
    if not clean:
        return None, "timewitness.py exit %d, stdout %d chars, stderr: %s" % (
            p.returncode, len(p.stdout), scrub(p.stderr.strip()[-300:]))
    return scrub(p.stdout.rstrip("\n")), None


def date_u_output():
    p = subprocess.run(["date", "-u"], capture_output=True, text=True, env={"LC_ALL": "C", "PATH": "/bin:/usr/bin"})
    return p.stdout.rstrip("\n")


def build_messages(cond, ctx):
    """Return (messages, extra) where messages is OpenAI style."""
    extra = {}
    if cond == "P0":
        return [{"role": "user", "content": P0_TEXT}], extra
    if cond == "P1":
        ids = [r["id"] for r in ctx["p1_repos"]]
        return [{"role": "user", "content": P1_HEAD + "\n" + "\n".join(ids) + "\n\n" + P0_TEXT}], extra
    if cond == "P3":
        return [{"role": "user", "content": P3_TEXT}], extra
    if cond == "P2A":
        out, err = timewitness_output()
        if err:
            raise PendingError(err)
        extra["tool_output"] = out
        return [{"role": "system", "content": P2_SYSTEM_2024},
                {"role": "user", "content": P2A_HEAD + "\n" + out + P2_TAIL}], extra
    if cond in ("P2B", "P2C"):
        out = date_u_output()
        extra["tool_output"] = out
        if cond == "P2B":
            system = P2_SYSTEM_2024
        else:
            system = P2_SYSTEM_REAL.format(now=utcnow().strftime("%Y-%m-%d %H:%M:%S"))
        return [{"role": "system", "content": system},
                {"role": "user", "content": P2B_HEAD + "\n" + out + P2_TAIL}], extra
    raise ValueError(cond)


class PendingError(Exception):
    pass


# ---------------------------------------------------------------- results file

_lock = threading.Lock()


def load_rows():
    rows = []
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    return rows


def append_row(row):
    row = scrub(row)
    with _lock:
        with open(RESULTS, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


class Budget:
    def __init__(self, spent):
        self.spent = spent
        self.reserved = 0.0
        self.lock = threading.Lock()
        self.stopped = False

    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount >= BUDGET_USD:
                self.stopped = True
                return False
            self.reserved += amount
            return True

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


# ---------------------------------------------------------------- router route

def router_call(token, mid, prov, cond, rep, ctx, budget, refused):
    if mid in refused:
        return
    pricing = ctx["models"][mid].get("pricing") or {}
    pin, pout = pricing.get("input"), pricing.get("output")
    try:
        messages, extra = build_messages(cond, ctx)
    except PendingError as e:
        print("PENDING", mid, cond, rep, "-", e, flush=True)
        return
    nchars = sum(len(m["content"]) for m in messages)
    if pin is None or pout is None:
        print("NO PRICE", mid, prov, "- skipped", flush=True)
        return
    worst = ((nchars / 2.5 + 300) * pin + MAX_TOKENS * pout) / 1e6
    if not budget.reserve(worst):
        print("BUDGET STOP before", mid, cond, rep, flush=True)
        return
    payload = {"model": "%s:%s" % (mid, prov), "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.7}
    row = {
        "route": "hf-router", "model": mid, "provider": prov, "condition": cond, "repetition": rep,
        "release_date": ctx["models"][mid].get("hub_created_at"), "messages": messages,
        "tool_output": extra.get("tool_output"), "max_tokens": MAX_TOKENS, "temperature_sent": 0.7,
        "pricing_per_million": pricing,
    }
    attempt, actual = 0, 0.0
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
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            err = "HTTP %d" % e.code
        except Exception as e:
            err = type(e).__name__ + ": " + str(e)[:200]
        latency = time.monotonic() - tic
        if status == 400 and body and "temperature" in body.lower() and "temperature" in payload:
            payload.pop("temperature")
            row["temperature_sent"] = None
            continue
        if (status in (429, 500, 502, 503, 504) or status is None) and attempt < 4:
            time.sleep(5 * attempt)
            continue
        break
    row.update({
        "call_time_utc": iso(t0), "latency_s": round(latency, 2), "http_status": status, "attempts": attempt,
        "response_date_header": hdrs.get("Date") or hdrs.get("date"),
        "real_date_utc_at_call": t0.strftime("%Y-%m-%d"),
        "local_date_at_call": dt.datetime.now().astimezone().strftime("%Y-%m-%d"),
    })
    api_ok = False
    if status == 200 and body:
        try:
            j = json.loads(body)
            ch = (j.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            text = msg.get("content")
            usage = j.get("usage") or {}
            pt, ct = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
            actual = (pt * pin + ct * pout) / 1e6
            parsed, how = extract_json(text)
            keys_ok = bool(parsed) and all(k in parsed for k in EXPECTED_KEYS[cond])
            row.update({
                "raw_reply": text, "reasoning_content": msg.get("reasoning_content") or msg.get("reasoning"),
                "finish_reason": ch.get("finish_reason"), "usage": usage, "served_model": j.get("model"),
                "est_cost_usd": round(actual, 6), "parsed": parsed, "parse_ok": parsed is not None,
                "parse_how": how, "keys_ok": keys_ok,
            })
            api_ok = True
        except Exception as e:
            row.update({"error": "bad response body: " + type(e).__name__, "raw_body": (body or "")[:2000]})
    else:
        row.update({"error": err, "raw_body": (body or "")[:2000]})
        low = (body or "").lower()
        if status in (401, 403) or "gated" in low or "access to model" in low:
            refused.add(mid)
            row["refused"] = True
    row["api_ok"] = api_ok
    budget.settle(worst, actual)
    row["running_total_usd"] = round(budget.spent, 6)
    append_row(row)
    print("%-40s %-4s r%d status=%s parse=%s cost=$%.5f total=$%.4f %.1fs" % (
        mid[:40], cond, rep, status, row.get("parse_ok"), actual, budget.spent, latency), flush=True)


# ---------------------------------------------------------------- Claude Code route

_claude_lock = threading.Lock()


def claude_call(alias, cond, rep, ctx, counter):
    try:
        messages, extra = build_messages(cond, ctx)
    except PendingError as e:
        print("PENDING claude", alias, cond, rep, "-", e, flush=True)
        return
    with _claude_lock:
        if counter["n"] >= CLAUDE_MAX_CALLS:
            print("CLAUDE CAP reached; skipped", alias, cond, rep, flush=True)
            return
        counter["n"] += 1
    system = next((m["content"] for m in messages if m["role"] == "system"), None)
    user = next(m["content"] for m in messages if m["role"] == "user")
    args = ["claude", "-p", "--model", alias, "--no-session-persistence", "--setting-sources", "",
            "--strict-mcp-config", "--output-format", "json"]
    if system is not None:
        args += ["--system-prompt", system]
    args += ["--tools", ""]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION")}
    t0 = utcnow()
    tic = time.monotonic()
    err, out = None, ""
    try:
        p = subprocess.run(args, input=user, capture_output=True, text=True, timeout=600, cwd=CLAUDE_CWD, env=env)
        out = p.stdout
        if p.returncode != 0:
            err = "exit %d: %s" % (p.returncode, (p.stderr or p.stdout)[-300:])
    except Exception as e:
        err = type(e).__name__
    latency = time.monotonic() - tic
    row = {
        "route": "claude-code", "model": alias, "provider": "anthropic (via Claude Code %s)" % ctx.get("claude_version"),
        "condition": cond, "repetition": rep, "release_date": None,
        "messages": messages, "system_prompt_flag": system, "claude_default_system_prompt": system is None,
        "tool_output": extra.get("tool_output"), "call_time_utc": iso(t0), "latency_s": round(latency, 2),
        "real_date_utc_at_call": t0.strftime("%Y-%m-%d"),
        "local_date_at_call": dt.datetime.now().astimezone().strftime("%Y-%m-%d"),
        "harness_date_expected": dt.datetime.now().astimezone().strftime("%Y-%m-%d"),
        "response_date_header": None, "est_cost_usd": 0.0,
    }
    api_ok = False
    try:
        j = json.loads(out)
        text = j.get("result")
        parsed, how = extract_json(text)
        mu = j.get("modelUsage") or {}
        # Stored as "harness_date_shown_in_reply", but it is only the first YYYY-MM-DD found in
        # quote / notes_for_operator / reasoning (a "Today's date is ..." quote if present).
        # It is not evidence of what Claude Code sent: in P2 it often picks up 2024-05-15.
        # score.py reports it as "first_date_in_reply".
        shown = None
        if parsed:
            q = " ".join(str(parsed.get(k, "")) for k in ("quote", "notes_for_operator", "reasoning"))
            m = re.search(r"(?i)today'?s date is (\d{4}-\d{2}-\d{2})", q) or re.search(r"\d{4}-\d{2}-\d{2}", q)
            if m:
                shown = m.group(1) if m.groups() else m.group(0)
        row.update({
            "raw_reply": text, "parsed": parsed, "parse_ok": parsed is not None, "parse_how": how,
            "keys_ok": bool(parsed) and all(k in parsed for k in EXPECTED_KEYS[cond]),
            "finish_reason": j.get("stop_reason") or j.get("subtype"), "usage": j.get("usage"),
            "model_ids_reported": list(mu.keys()), "cli_reported_cost_usd": j.get("total_cost_usd"),
            "is_error": j.get("is_error"), "num_turns": j.get("num_turns"),
            "harness_date_shown_in_reply": shown,
        })
        api_ok = not j.get("is_error") and text is not None
    except Exception as e:
        row["error"] = err or ("unparseable CLI output: " + type(e).__name__)
        row["raw_body"] = out[-1500:]
    if err and "error" not in row:
        row["error"] = err
    row["api_ok"] = api_ok
    append_row(row)
    print("claude %-7s %-4s r%d ok=%s parse=%s %.1fs" % (alias, cond, rep, api_ok, row.get("parse_ok"), latency),
          flush=True)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma list of conditions, e.g. P2A")
    ap.add_argument("--route", choices=["hf", "claude", "all"], default="all")
    ap.add_argument("--models", help="comma list of model ids or claude aliases to include")
    ap.add_argument("--smoke", action="store_true", help="one call per route, then stop")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--claude-workers", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=1500,
                    help="router max_tokens (protocol: 1500). A different value is a different protocol; "
                         "use a separate results file for it.")
    ap.add_argument("--results", help="results file (default results.jsonl in this folder)")
    args = ap.parse_args()
    global MAX_TOKENS, RESULTS
    MAX_TOKENS = args.max_tokens
    if args.results:
        RESULTS = os.path.abspath(args.results)
    _init_scrub()

    ctx = load_or_build_context()
    try:
        ctx["claude_version"] = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                                               timeout=30).stdout.strip()
    except Exception:
        ctx["claude_version"] = "unknown"
    if not os.path.exists(GROUND):
        fetch_ground_truth()

    only = set(args.only.split(",")) if args.only else None
    pick = set(args.models.split(",")) if args.models else None
    rows = load_rows()
    done = {(r["route"], r["model"], r["condition"], r["repetition"]) for r in rows if r.get("api_ok")}
    spent = sum(r.get("est_cost_usd") or 0 for r in rows if r.get("route") == "hf-router")
    claude_n = sum(1 for r in rows if r.get("route") == "claude-code")
    refused = {r["model"] for r in rows if r.get("refused")}
    budget = Budget(spent)
    counter = {"n": claude_n}
    print("already done: %d calls; router spend so far $%.4f; Claude Code calls so far %d" % (
        len(done), spent, claude_n), flush=True)

    hf_tasks, cl_tasks = [], []
    if args.route in ("hf", "all"):
        for mid, prov in HF_MODELS:
            if pick and mid not in pick:
                continue
            if not ctx["models"][mid].get("served"):
                print("NOT SERVED", mid, prov, flush=True)
                continue
            for cond in HF_CONDITIONS:
                if only and cond not in only:
                    continue
                for rep in range(1, HF_REPS + 1):
                    if ("hf-router", mid, cond, rep) not in done:
                        hf_tasks.append((mid, prov, cond, rep))
    if args.route in ("claude", "all"):
        for alias in CLAUDE_MODELS:
            if pick and alias not in pick:
                continue
            for cond in CLAUDE_CONDITIONS:
                if only and cond not in only:
                    continue
                for rep in range(1, CLAUDE_REPS + 1):
                    if ("claude-code", alias, cond, rep) not in done:
                        cl_tasks.append((alias, cond, rep))
    if args.smoke:
        hf_tasks, cl_tasks = hf_tasks[:1], cl_tasks[:1]

    from huggingface_hub import get_token
    token = get_token() if hf_tasks else None
    if hf_tasks and not token:
        print("no Hugging Face token stored; router calls skipped", flush=True)
        hf_tasks = []

    # Router: one thread per model, calls within a model run in order.
    by_model = {}
    for t in hf_tasks:
        by_model.setdefault(t[0], []).append(t)

    def run_model(tasks):
        for mid, prov, cond, rep in tasks:
            if budget.stopped:
                return
            router_call(token, mid, prov, cond, rep, ctx, budget, refused)

    def run_claude():
        with ThreadPoolExecutor(max_workers=args.claude_workers) as ex:
            list(ex.map(lambda t: claude_call(t[0], t[1], t[2], ctx, counter), cl_tasks))

    with ThreadPoolExecutor(max_workers=args.workers + 1) as ex:
        futs = [ex.submit(run_model, ts) for ts in by_model.values()]
        if cl_tasks:
            futs.append(ex.submit(run_claude))
        for f in futs:
            f.result()
    print("finished. router spend $%.4f (budget $%.2f, stopped=%s). Claude Code calls used %d of %d." % (
        budget.spent, BUDGET_USD, budget.stopped, counter["n"], CLAUDE_MAX_CALLS), flush=True)


if __name__ == "__main__":
    main()
