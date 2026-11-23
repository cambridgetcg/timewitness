# Smoke test rows (not results)

These rows were written on 2026-11-23 to check the harness before the full runs:
that prompts are built as intended, that the clock line reaches the model only in
the clock arm, that the allowed tool and `--resume` work, and that replies parse.
They are kept so that nothing seen before the full run is hidden. They are not
pooled with the main rows.

## Round 1 (before the design check)

- `rows_router_smoke.jsonl`: two router models, twelve cells each. These rows have
  no `design` field; `score.py` calls them design `smoke-0`. Two things changed
  after them. The F1 wording: in these rows the assistant's earlier turn says
  "Done. The DNS change went in just now", although the system message says the
  assistant has no tools; one reply pointed out the contradiction, so in the
  current design the person makes the change ("I just switched ...") and the
  assistant only says it went in just now. The parser: one reply put its reason on
  the DECISION line, which the first parser did not accept; `score.py` parses
  every reply again with the current parser. Their base date is the run date,
  2026-11-23; from design `time-use-2` on, the router base date is fixed at
  2027-01-19.
- `rows_claude_smoke.jsonl` (design `time-use-1`): Claude Code (haiku): a clock
  canary with the hook and one without, one F3 row, one F6 row (hook arm), and one
  F1 session created and resumed about 3 minutes later (two calls, one row).
- `run_context_router_smoke.json`: the router price list and base date used.

## Round 2 (design `time-use-2`, after the design check)

- `rows_router_smoke2.jsonl`: twelve calls, the date canary on all eight router
  models and four decision rows. Every call was refused with HTTP 402 ("Purchase
  pre-paid credits to continue using Inference Providers."), so these rows hold no
  replies. Cost: zero. They are kept as the record of the attempt.
- `run_context_router_smoke2.json`: the router price list and the fixed base date.
- `rows_claude_smoke2.jsonl`: Claude Code (haiku), four calls: the clock canary with
  the hook and the new deny list (it also asks the model to run `uptime`), one
  hook-free F2 row, and one F1 session created and resumed about 14 minutes later
  (two calls, one row), to see whether the hook prints a gap sentence on a real
  resume.

To score them: `python3 -I -B score.py --smoke 1 --out-dir <folder>` (round 1) or
`python3 -I -B score.py --smoke --out-dir <folder>` (round 2).
