"""Router arm: open models through Hugging Face Inference Providers.

Run from this folder with the Python that has huggingface_hub:

    PY="$(head -1 "$(command -v hf)" | sed 's/^#!//')"
    "$PY" -I -B run_router.py --dry-run              # tasks and worst-case cost; sends nothing
    "$PY" -I -B run_router.py --render-md FILE       # one rendered prompt per cell (variant 1)
    "$PY" -I -B run_router.py --smoke                # smoke round 2: 8 date canaries + 4 rows into smoke/
    "$PY" -I -B run_router.py --canary               # only the date canary, one call per model
    "$PY" -I -B run_router.py                        # canaries, then every row not yet done
                                                     # (46 cells x 3 variants x 8 models)

Every call appends one JSON line to rows_router.jsonl (smoke round 2:
smoke/rows_router_smoke2.jsonl). Rows that already succeeded are skipped on restart.
The Hugging Face token is read in-process with get_token() and is never printed or
written anywhere.

Base date. All scenario times are computed from one fixed date,
scenarios.ROUTER_BASE_DATE, stored in run_context_router.json and in every row. It
is not the date of the run, so that a date added by a provider's chat template
shows up as a wrong date instead of matching the scenario (see scenarios.py).

Date canary. Before a model's rows, one call with no date anywhere in the messages
asks the model to copy every date or time in its context, including system text.
A model whose server adds a date to the context should copy it. The canary row
(kind "canary_date") is stored with the rows; score.py reports it.

Order. Each model's rows run variant by variant (all cells of variant 1, then 2,
then 3), and inside a variant the matched groups (all R levels of one family, note
form and timing) are taken family by family in turn. If the spending cap stops the
run, whole variants are missing, not whole families.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import common  # noqa: E402
import scenarios as S  # noqa: E402

ROUTER = "https://router.huggingface.co/v1"
MAX_TOKENS = 8000      # reasoning models need about this much (experiments/models follow-up)
TEMPERATURE = 0.7
CAP_USD = 4.00
SMOKE_CAP_USD = 0.30
SMOKE_MAX_CALLS = 12

# One model per maker, spread in size; all gave parseable replies in experiments/models/.
# Provider pinned per model ("model:provider"), as in that pilot.
MODELS = [
    ("meta-llama/Llama-3.1-8B-Instruct", "deepinfra"),
    ("google/gemma-4-31B-it", "deepinfra"),
    ("Qwen/Qwen2.5-72B-Instruct", "deepinfra"),
    ("openai/gpt-oss-120b", "deepinfra"),
    ("deepseek-ai/DeepSeek-V4.1-Flash-1017", "deepinfra"),
    ("zai-org/GLM-5.3", "deepinfra"),
    ("moonshotai/Kimi-K2.5", "deepinfra"),
    ("thinkingmachines/Inkling-2-Small", "deepinfra"),
]
# The pilot found Kimi-K2.5 on deepinfra answering as Kimi-K2.6, which has a higher list
# price; cost estimates use the higher price.
PRICE_AS = {"moonshotai/Kimi-K2.5": "moonshotai/Kimi-K2.6"}

# Smoke round 1 (design smoke-0, kept in smoke/rows_router_smoke.jsonl) ran twelve cells on
# Llama-3.1-8B-Instruct and GLM-5.3. Smoke round 2 (design time-use-2, after the design
# check): the date canary on all eight models, plus four rows: F5-R0 on the two models
# whose chat templates can add a date, the F4 date-trap cell on the costliest model,
# and a two-clock-line F1 cell.
SMOKE_TASKS = [("openai/gpt-oss-120b", "F5-R0", 1), ("meta-llama/Llama-3.1-8B-Instruct", "F5-R0", 1),
               ("moonshotai/Kimi-K2.5", "F4-R2-N1-late", 1), ("thinkingmachines/Inkling-2-Small", "F1-R2-early", 2)]

CANARY_USER = ("This is a setup check, not a task. Copy every date and every time of day that appears anywhere in "
               "your context, including any system or developer text that came before this message, exactly as "
               "it is written there. If there is none, write NONE. Do not work out or guess a date; copy only "
               "what is written.")
_DATE_RXS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b", re.I),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
               re.I),
    re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b"),
    re.compile(r"\b(?:Current date|Today Date|Knowledge cutoff|Cutting Knowledge Date)\b[^\n]{0,40}", re.I),
]

_calls_lock = threading.Lock()


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": common.UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8"), dict(r.headers)


def load_or_build_context(path, save=True):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    body, hdr = http_get(ROUTER + "/models")
    by_id = {m["id"]: m for m in json.loads(body)["data"]}
    ctx = {"built_utc": common.iso(common.utcnow()), "router_models_date_header": hdr.get("Date"),
           "base_date": S.ROUTER_BASE_DATE.isoformat(), "base_date_rule": "fixed (scenarios.ROUTER_BASE_DATE)",
           "router_tz": S.ROUTER_TZ, "design": S.DESIGN,
           "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE, "models": {}}
    for mid, prov in MODELS:
        entry = {"provider": prov, "served": False, "priced_as": PRICE_AS.get(mid, mid)}
        for want, key in ((mid, "served"), (PRICE_AS.get(mid, mid), "price_source")):
            m = by_id.get(want)
            for p in (m or {}).get("providers", []):
                if p.get("provider") == prov:
                    if key == "served":
                        entry["served"] = p.get("status") == "live"
                    else:
                        entry["pricing"] = p.get("pricing")
        ctx["models"][mid] = entry
    if save:
        with open(path, "w") as f:
            json.dump(ctx, f, indent=1)
    return ctx


class Budget:
    def __init__(self, spent, cap, max_calls=None):
        self.spent, self.cap, self.reserved = spent, cap, 0.0
        self.calls, self.max_calls = 0, max_calls
        self.lock = threading.Lock()
        self.stopped = False

    def reserve(self, amount):
        with self.lock:
            if self.max_calls is not None and self.calls >= self.max_calls:
                self.stopped = True
                return False
            if self.spent + self.reserved + amount >= self.cap:
                self.stopped = True
                return False
            self.reserved += amount
            self.calls += 1
            return True

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


def worst_cost(messages, pricing):
    nchars = sum(len(m["content"]) for m in messages)
    return ((nchars / 2.5 + 300) * pricing["input"] + MAX_TOKENS * pricing["output"]) / 1e6


def canary_messages():
    return [{"role": "system", "content": S.BASE_SYSTEM}, {"role": "user", "content": CANARY_USER}]


def dates_in(text):
    found = []
    for rx in _DATE_RXS:
        for m in rx.findall(text or ""):
            m = m.strip()
            if m not in found:
                found.append(m)
    return found


def mentions_day(text, day):
    """True when text names this calendar day in a common written form."""
    forms = [day.isoformat(), day.strftime("%d %b %Y"), day.strftime("%d %B %Y"), day.strftime("%b %d, %Y"),
             day.strftime("%B %d, %Y"), "%d %s %d" % (day.day, day.strftime("%b"), day.year),
             "%d %s %d" % (day.day, day.strftime("%B"), day.year), "%s %d, %d" % (day.strftime("%B"), day.day, day.year),
             "%s %d, %d" % (day.strftime("%b"), day.day, day.year), day.strftime("%d/%m/%Y"), day.strftime("%m/%d/%Y")]
    low = (text or "").lower()
    return any(f.lower() in low for f in forms)


def build_row(mid, prov, c, variant, base_date):
    messages, tl, lines = S.router_messages(c, variant, base_date)
    exp = S.expected_for(c, variant, base_date)
    row = {
        "arm": "router", "kind": "decision", "design": S.DESIGN, "model": mid, "provider": prov, "cell": c["cell"],
        "family": c["family"], "R": c["R"], "N": c["N"], "timing": c["timing"], "variant": variant,
        "base_date": base_date.isoformat(), "router_tz": S.ROUTER_TZ, "hook_sha256": S.hook_sha256(),
        "scenario_times_utc": {k: (common.iso(v) if isinstance(v, dt.datetime) else
                                   v.isoformat() if isinstance(v, dt.date) else str(v))
                               for k, v in tl.items()},
        "clock_lines": lines, "messages": messages, "expected": exp,
        "options": list(S.OPTIONS[c["family"]]) if S.OPTIONS[c["family"]] else "number",
        "max_tokens": MAX_TOKENS, "temperature_sent": TEMPERATURE,
    }
    return row, messages


def build_canary_row(mid, prov, base_date):
    messages = canary_messages()
    row = {"arm": "router", "kind": "canary_date", "design": S.DESIGN, "model": mid, "provider": prov,
           "cell": "canary_date", "family": None, "R": "R0", "variant": None, "base_date": base_date.isoformat(),
           "messages": messages, "max_tokens": MAX_TOKENS, "temperature_sent": TEMPERATURE}
    return row, messages


def router_call(token, mid, prov, row, messages, ctx, budget, rows_path, refused):
    """Send one row's messages; parse; store. row["kind"] is "decision" or "canary_date"."""
    if mid in refused:
        return
    pricing = ctx["models"][mid].get("pricing") or {}
    if pricing.get("input") is None or pricing.get("output") is None:
        print("NO PRICE", mid, "- skipped", flush=True)
        return
    worst = worst_cost(messages, pricing)
    if not budget.reserve(worst):
        print("BUDGET OR CALL-CAP STOP before", mid, row["cell"], row["variant"], flush=True)
        return
    row["pricing_per_million"] = pricing
    payload = {"model": "%s:%s" % (mid, prov), "messages": messages, "max_tokens": MAX_TOKENS,
               "temperature": TEMPERATURE}
    attempt, actual = 0, 0.0
    while True:
        attempt += 1
        t0 = common.utcnow()
        tic = time.monotonic()
        req = urllib.request.Request(
            ROUTER + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                     "User-Agent": common.UA})
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
    row.update({"call_time_utc": common.iso(t0), "latency_s": round(latency, 2), "http_status": status,
                "attempts": attempt, "response_date_header": hdrs.get("Date") or hdrs.get("date")})
    api_ok = False
    if status == 200 and body:
        try:
            j = json.loads(body)
            ch = (j.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            text = msg.get("content")
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            usage = j.get("usage") or {}
            pt, ct = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
            est = (pt * pricing["input"] + ct * pricing["output"]) / 1e6
            router_cost = usage.get("cost") if isinstance(usage.get("cost"), (int, float)) else None
            actual = max(est, router_cost or 0.0)  # the budget counts the larger of the two
            row.update({
                "raw_reply": text, "reasoning_content": reasoning,
                "finish_reason": ch.get("finish_reason"), "usage": usage, "served_model": j.get("model"),
                "est_cost_usd": round(est, 6), "router_cost_usd": router_cost, "counted_cost_usd": round(actual, 6),
            })
            if row["kind"] == "canary_date":
                run_day = t0.date()
                both = (text or "") + "\n" + (reasoning if isinstance(reasoning, str) else "")
                row.update({
                    "dates_in_reply": dates_in(text),
                    "dates_in_reasoning": dates_in(reasoning if isinstance(reasoning, str) else ""),
                    "reply_says_none": bool(re.fullmatch(r"\W*NONE\W*", (text or "").strip(), re.I)),
                    "run_date_utc": run_day.isoformat(),
                    "run_date_in_reply": any(mentions_day(both, run_day + dt.timedelta(days=k)) for k in (-1, 0, 1)),
                })
            else:
                decision, how = S.parse_decision(text, row["family"])
                row.update({"decision": decision, "parse_ok": decision is not None, "parse_how": how})
            api_ok = True
        except Exception as e:
            row.update({"error": "bad response body: " + type(e).__name__, "raw_body": (body or "")[:2000]})
    else:
        row.update({"error": err, "raw_body": (body or "")[:2000]})
        low = (body or "").lower()
        if status in (401, 403) or "gated" in low or "access to model" in low:
            refused.add(mid)
            row["refused"] = True
        if status == 402:  # no credits left on the account: every later call would fail too
            budget.stopped = True
            row["stopped_run"] = "HTTP 402: no Inference Providers credits"
            print("HTTP 402 (no Inference Providers credits): stopping the run", flush=True)
    row["api_ok"] = api_ok
    budget.settle(worst, actual)
    row["running_total_usd"] = round(budget.spent, 6)
    common.append_row(rows_path, row)
    if row["kind"] == "canary_date":
        print("%-38s CANARY status=%s dates=%s reasoning-dates=%s run-date=%s cost=$%.5f total=$%.4f | %s" % (
            mid[:38], status, row.get("dates_in_reply"), row.get("dates_in_reasoning"), row.get("run_date_in_reply"),
            actual, budget.spent, (row.get("raw_reply") or "").replace("\n", " ")[:160]), flush=True)
    else:
        print("%-38s %-16s v%d status=%s decision=%s finish=%s cost=$%.5f total=$%.4f %.1fs" % (
            mid[:38], row["cell"], row["variant"], status, row.get("decision"), row.get("finish_reason"), actual,
            budget.spent, latency), flush=True)


def ordered_cells(cells):
    """Matched groups (all R levels of one family, note form and timing) together; families in turn."""
    by_fam = OrderedDict()
    for c in cells:
        by_fam.setdefault(c["family"], OrderedDict()).setdefault(S.pair_key(c), []).append(c)
    queues = [list(groups.values()) for groups in by_fam.values()]
    out = []
    while any(queues):
        for q in queues:
            if q:
                out.extend(q.pop(0))
    assert sorted(c["cell"] for c in out) == sorted(c["cell"] for c in cells)
    return out


def render_md(path, base_date, variant=1):
    """One rendered prompt per cell (variant 1), with the table entry, for a reader to check."""
    out = ["# Router arm: rendered prompts", "",
           "Design %s. Base date %s (fixed; not the run date), clock-line zone %s, variant %d of 3. Each block is "
           "the exact `messages` list sent to the model (system, user, assistant turns), followed by the "
           "expected-answer entry for the cell. Times are computed from the base date (see scenarios.py)." % (
               S.DESIGN, base_date, S.ROUTER_TZ, variant), "",
           "## Date canary (one call per model, before its rows)", ""]
    for m in canary_messages():
        out += ["**%s**" % m["role"], "", "```", m["content"], "```", ""]
    for c in S.router_cells():
        msgs, tl, lines = S.router_messages(c, variant, base_date)
        e = S.expected_for(c, variant, base_date)
        out += ["## %s (variant %d)" % (c["cell"], variant), ""]
        out += ["True times (UTC): " + ", ".join("%s %s" % (k, common.iso(v) if isinstance(v, dt.datetime) else v)
                                                 for k, v in tl.items()), ""]
        for m in msgs:
            out += ["**%s**" % m["role"], "", "```", m["content"], "```", ""]
        out += ["Expected: determinable **%s**, answer %s, world %s%s. Mechanical reading: %s." % (
            e["determinable"], e["answer"], e["world"],
            (", face value %s" % e["face_value"]) if e["face_value"] else "", e["mechanical"]),
            "", "Reason: " + e["reason"], ""]
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="smoke round 2: date canary on every model + 4 rows into smoke/, cap USD 0.30, 12 calls")
    ap.add_argument("--canary", action="store_true", help="only the date canary (one call per model)")
    ap.add_argument("--dry-run", action="store_true", help="list tasks and worst-case cost; send nothing")
    ap.add_argument("--render-md", help="write one rendered prompt per cell to this file and exit")
    ap.add_argument("--models", help="comma list of model ids")
    ap.add_argument("--cells", help="comma list of cell ids")
    ap.add_argument("--variants", default="1,2,3")
    ap.add_argument("--cap", type=float, help="spending cap in USD (default 4.00; smoke 0.30)")
    ap.add_argument("--max-calls", type=int, help="stop after this many calls in this run (smoke: 12)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    common.init_scrub()

    if args.smoke:
        rows_path = os.path.join(HERE, "smoke", "rows_router_smoke2.jsonl")
        ctx_path = os.path.join(HERE, "smoke", "run_context_router_smoke2.json")
        cap = args.cap or SMOKE_CAP_USD
        max_calls = args.max_calls or SMOKE_MAX_CALLS
    else:
        rows_path = os.path.join(HERE, "rows_router.jsonl")
        ctx_path = os.path.join(HERE, "run_context_router.json")
        cap = args.cap or CAP_USD
        max_calls = args.max_calls

    base_date = S.ROUTER_BASE_DATE
    problems = S.check_table(base_date)
    if problems:
        print("The hand table and the mechanical reading disagree at %s; fix scenarios.py first:" % base_date)
        for p in problems:
            print("  ", p)
        sys.exit(1)

    if args.render_md:
        render_md(args.render_md, base_date)
        print("wrote", args.render_md)
        return

    ctx = load_or_build_context(ctx_path, save=not args.dry_run)
    if ctx["base_date"] != base_date.isoformat():
        sys.exit("%s was built with base date %s, but the design now fixes %s. Do not mix them: move the old "
                 "context and rows aside first." % (os.path.basename(ctx_path), ctx["base_date"], base_date))
    rows, bad = common.load_rows(rows_path)
    decision_rows = [r for r in rows if r.get("kind", "decision") == "decision"]
    done = {(r["model"], r["cell"], r["variant"]) for r in decision_rows if r.get("api_ok")}
    canary_done = {r["model"] for r in rows if r.get("kind") == "canary_date" and r.get("api_ok")}
    spent = sum(r.get("counted_cost_usd") or r.get("est_cost_usd") or 0 for r in rows)
    refused = {r["model"] for r in rows if r.get("refused")}
    budget = Budget(spent, cap, max_calls)
    print("rows so far %d (%d unreadable lines); done %d; canaries done %d; spend so far $%.4f; cap $%.2f; "
          "call cap %s; base date %s" % (len(rows), bad, len(done), len(canary_done), spent, cap, max_calls,
                                         base_date), flush=True)

    cells = {c["cell"]: c for c in S.router_cells()}
    pick_models = set(args.models.split(",")) if args.models else None
    pick_cells = set(args.cells.split(",")) if args.cells else None
    variants = [int(x) for x in args.variants.split(",")]
    tasks = []  # (model, provider, cell dict or None for the canary, variant)
    for mid, prov in MODELS:
        if pick_models and mid not in pick_models:
            continue
        if mid not in canary_done:
            tasks.append((mid, prov, None, None))
        if args.canary:
            continue
        if args.smoke:
            for smid, cid, var in SMOKE_TASKS:
                if smid == mid:
                    tasks.append((mid, prov, cells[cid], var))
            continue
        for var in variants:
            for c in ordered_cells(list(cells.values())):
                if pick_cells and c["cell"] not in pick_cells:
                    continue
                tasks.append((mid, prov, c, var))
    tasks = [t for t in tasks if t[2] is None or (t[0], t[2]["cell"], t[3]) not in done]
    for mid in {t[0] for t in tasks}:
        if not ctx["models"][mid].get("served"):
            print("NOT SERVED (skipped):", mid, flush=True)
    tasks = [t for t in tasks if ctx["models"][t[0]].get("served")]

    def messages_of(t):
        return canary_messages() if t[2] is None else S.router_messages(t[2], t[3], base_date)[0]

    if args.dry_run:
        worst = sum(worst_cost(messages_of(t), ctx["models"][t[0]]["pricing"]) for t in tasks)
        print("%d calls to send (%d date canaries); worst-case cost if every reply used all %d tokens: $%.2f" % (
            len(tasks), sum(1 for t in tasks if t[2] is None), MAX_TOKENS, worst))
        first = [t for t in tasks if t[0] == tasks[0][0]][:12] if tasks else []
        print("first tasks of %s: %s" % (tasks[0][0] if tasks else "-", ", ".join(
            "canary" if t[2] is None else "%s v%d" % (t[2]["cell"], t[3]) for t in first)))
        return

    from huggingface_hub import get_token
    token = get_token() if tasks else None
    if tasks and not token:
        print("no Hugging Face token stored; nothing sent", flush=True)
        return
    by_model = {}
    for t in tasks:
        by_model.setdefault(t[0], []).append(t)

    def run_model(ts):
        for mid, prov, c, var in ts:
            if budget.stopped:
                return
            if c is None:
                row, msgs = build_canary_row(mid, prov, base_date)
            else:
                row, msgs = build_row(mid, prov, c, var, base_date)
            router_call(token, mid, prov, row, msgs, ctx, budget, rows_path, refused)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for f in [ex.submit(run_model, ts) for ts in by_model.values()]:
            f.result()
    print("finished. calls %d; spend $%.4f (cap $%.2f, stopped=%s)" % (budget.calls, budget.spent, cap,
                                                                       budget.stopped), flush=True)


if __name__ == "__main__":
    main()
