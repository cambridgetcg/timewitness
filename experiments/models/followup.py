"""Follow-up under a changed limit: re-send every router call that was cut off.

The original protocol used max_tokens 1500. 50 of 252 router calls ended with
finish_reason "length". This script sends those 50 calls again with max_tokens
8000 and writes the replies to results_followup.jsonl. results.jsonl is only read.

    PY="$(head -1 "$(command -v hf)" | sed 's/^#!//')"   # the Python that has huggingface_hub
    "$PY" -I followup.py --dry-run     # list the calls and the worst-case cost, send nothing
    "$PY" -I followup.py               # send them (skips any already in results_followup.jsonl)

Messages are built at call time by run.py's own build_messages, as in the
original run. P0, P1 and P3 are fixed text, so they are the same messages as the
original call (the script checks this). P2A gets a fresh timewitness.py capture and
P2B a fresh `date -u` reading, because those tool blocks are built from the clock at
call time; a stored 2026-11-13 reading re-sent on a later day would no longer be true.
If timewitness.py is not runnable, P2A calls are skipped and the reason is printed.

Every stored row has "max_tokens_raised": true, "max_tokens": 8000 and
"original_max_tokens": 1500, so it can never be mistaken for a protocol row.
"""

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # leave no __pycache__ in the study folder
import run  # noqa: E402

FOLLOWUP = os.path.join(HERE, "results_followup.jsonl")
NEW_MAX_TOKENS = 8000
CAP_USD = 3.00
# The provider answered every Kimi-K2.5 request with the id moonshotai/Kimi-K2.6,
# which the router lists at a higher price. Reserve and estimate at the higher one.
PRICE_OVERRIDE = {"moonshotai/Kimi-K2.5": "moonshotai/Kimi-K2.6"}


def file_sha256(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()

    run._init_scrub()
    ctx = json.loads(json.dumps(run.load_or_build_context()))
    rows = run.load_rows()
    cut = [r for r in rows if r.get("route") == "hf-router" and r.get("finish_reason") == "length"]
    done = set()
    if os.path.exists(FOLLOWUP):
        with open(FOLLOWUP) as f:
            for line in f:
                if line.strip():
                    x = json.loads(line)
                    if x.get("api_ok"):
                        done.add((x["model"], x["condition"], x["repetition"]))
    todo = [r for r in cut if (r["model"], r["condition"], r["repetition"]) not in done]

    # Router list price for the id the provider answered with, when it is dearer.
    price_note = {}
    try:
        body, _ = run.http_get(run.ROUTER + "/models")
        by_id = {m["id"]: m for m in json.loads(body)["data"]}
        for asked, served in PRICE_OVERRIDE.items():
            prov = ctx["models"][asked]["provider"]
            for p in (by_id.get(served) or {}).get("providers", []):
                if p.get("provider") == prov and p.get("pricing"):
                    old = ctx["models"][asked].get("pricing") or {}
                    new = p["pricing"]
                    if (new.get("output") or 0) > (old.get("output") or 0):
                        ctx["models"][asked]["pricing"] = new
                        price_note[asked] = "priced at the %s list price %s (higher than the %s list price %s)" % (
                            served, new, asked, old)
    except Exception as e:
        print("price list not fetched (%s); using stored prices" % type(e).__name__, flush=True)

    worst_total = 0.0
    for r in todo:
        pr = ctx["models"][r["model"]].get("pricing") or {}
        n = sum(len(m["content"]) for m in r["messages"])
        worst_total += ((n / 2.5 + 300) * pr.get("input", 0) + NEW_MAX_TOKENS * pr.get("output", 0)) / 1e6
    print("cut-off router calls in results.jsonl: %d; already in follow-up file: %d; to send: %d" % (
        len(cut), len(done), len(todo)), flush=True)
    print("worst-case cost if every call used all %d tokens: USD %.4f (cap USD %.2f)" % (
        NEW_MAX_TOKENS, worst_total, CAP_USD), flush=True)

    tw_path = run.TIMEWITNESS
    tw_ok, tw_err = None, None
    if any(r["condition"] == "P2A" for r in todo):
        out, tw_err = run.timewitness_output()
        tw_ok = tw_err is None
        print("timewitness.py check: %s" % ("runnable, first line: " + out.splitlines()[0] if tw_ok else
                                           "NOT runnable: " + tw_err), flush=True)
    if a.dry_run:
        for r in todo:
            print("  would send", r["model"], r["condition"], r["repetition"])
        return
    if tw_ok is False:
        todo = [r for r in todo if r["condition"] != "P2A"]
        print("P2A re-runs skipped: timewitness.py was not runnable at run time.", flush=True)

    tw_sha = file_sha256(tw_path)
    originals = {(r["model"], r["condition"], r["repetition"]): r for r in todo}
    orig_append = run.append_row

    def append_followup(row):
        key = (row["model"], row["condition"], row["repetition"])
        o = originals.get(key) or {}
        row["max_tokens_raised"] = True
        row["original_max_tokens"] = o.get("max_tokens", 1500)
        row["original_finish_reason"] = o.get("finish_reason")
        row["original_call_time_utc"] = o.get("call_time_utc")
        row["same_messages_as_original"] = row.get("messages") == o.get("messages")
        if row["condition"] in ("P2A", "P2B", "P2C"):
            row["messages_note"] = "tool block (and P2C system time) rebuilt from the clock at call time, as in the original protocol"
        if row["condition"] == "P2A":
            row["timewitness_sha256_at_call"] = tw_sha
        if row["model"] in price_note:
            row["pricing_note"] = price_note[row["model"]]
        orig_append(row)

    run.append_row = append_followup
    run.RESULTS = FOLLOWUP
    run.MAX_TOKENS = NEW_MAX_TOKENS
    run.BUDGET_USD = CAP_USD
    budget = run.Budget(0.0)
    refused = set()

    from huggingface_hub import get_token
    token = get_token()
    if not token:
        print("no Hugging Face token stored; nothing sent", flush=True)
        return

    by_model = {}
    for r in todo:
        by_model.setdefault(r["model"], []).append(r)

    def run_model(rs):
        for r in rs:
            if budget.stopped:
                return
            run.router_call(token, r["model"], r["provider"], r["condition"], r["repetition"], ctx, budget, refused)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for f in [ex.submit(run_model, rs) for rs in by_model.values()]:
            f.result()
    print("finished. follow-up spend estimate USD %.4f (cap USD %.2f, stopped=%s)" % (
        budget.spent, CAP_USD, budget.stopped), flush=True)


if __name__ == "__main__":
    main()
