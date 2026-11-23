# Time-use experiment: summary

Written by score.py from rows_router.jsonl (2 rows, 0 unreadable lines) and rows_claude.jsonl (181 rows, 0 unreadable lines). Counts are k of n. Labels are defined in score.py. Designs in these rows: time-use-2.

## Router arm

Calls: 2 (2 failed; HTTP status of the failed calls: 402 x2). Decision rows: 0, of which 0 have a reply. Cost: USD 0.0000 counted (the larger of the token estimate and the router's own `usage.cost`); the router's own figure sums to USD 0.0000.

No router decision row has a reply, so this arm has no results.

### Date canary (no date in the messages; the model is asked to copy any date in its context)

| model | dates in the reply | dates in the reasoning | names the run date (+-1 day) | prompt tokens | reply (start) |
|---|---|---|---|---|---|
| meta-llama/Llama-3.1-8B-Instruct | none | none | None | None | HTTP 402 |
| meta-llama/Llama-3.1-8B-Instruct | none | none | None | None | HTTP 402 |

## Claude Code arm

- Clock canary, haiku, R2: clock lines in the hook events 1; reply quotes a Clock line: True; commands: date -u (ran); echo hello (ran); uptime (error).
- Clock canary, haiku, R1: clock lines in the hook events 0; reply quotes a Clock line: False; commands: date -u (ran); echo hello (ran); uptime (error).
- Resume canary, haiku: first turn carried: True.

### Calls and cost

Cost is the CLI's own `total_cost_usd`, summed over the stored rows. An F1 row stores the cost of its resumed call only, not of the call that created the session.

| model | model id reported | calls | rows | CLI-reported cost USD |
|---|---|---|---|---|
| haiku | claude-haiku-5-5 | 70 | 61 | 0.0278 |
| sonnet | claude-sonnet-5-5 | 66 | 58 | 0.3692 |
| opus | claude-opus-5-5 | 35 | 31 | 0.5035 |
| fable | claude-fable-5-2 | 35 | 31 | 1.0206 |
| total | | 206 | 181 | 1.9211 |

Rows by kind: canary_clock 2, canary_resume 1, decision 162, f6 16. Rows whose call failed: 0.

Successful decision rows 162 (failed calls 0).

Reply format: 162 of 162 replies have exactly one DECISION line, and it is the first line. Replies with the reason on the DECISION line instead of the next line: 10 (sonnet). Unparsed: 0. Parsed but naming another option on the DECISION line: 0. Rows whose stored parse differs from the parse here: 0.

Clock line delivery: R2 rows with a clock line in the hook events 84 of 84; R1 rows with one 0 of 78.

F1: resumes that reported the same session id 24 of 24; resume delay early 180.7 to 187.8 s, late 840.1 to 851.2 s; gap sentence in the resume's clock line: F1-R2-late 6 of 6, F1-R2-early 0 of 6.

Rows planned 168; present 162; missing 6 (F4-R1-N1-early); extra or repeated 0. F2 to F4 rows whose reading differs from the router table because of the hour of the call: 0.

### By arm (reading: seen)

| arm | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded (lucky / unlucky) | unsettled: CANNOT_TELL | unparsed | failed calls |
|---|---|---|---|---|---|---|---|
| R1 | 24 of 24 | 0 of 24 | 0 of 24 | 3 of 54 (2 / 1) | 51 of 54 | 0 | 0 |
| R2 | 46 of 48 | 0 of 48 | 2 of 48 | 1 of 36 (0 / 1) | 35 of 36 | 0 | 0 |

### By arm (reading: context; a model's own clock read is ignored)

| arm | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded (lucky / unlucky) | unsettled: CANNOT_TELL | unparsed | failed calls |
|---|---|---|---|---|---|---|---|
| R1 | 6 of 6 | 0 of 6 | 0 of 6 | 21 of 72 (20 / 1) | 51 of 72 | 0 | 0 |
| R2 | 46 of 48 | 0 of 48 | 2 of 48 | 1 of 36 (0 / 1) | 35 of 36 | 0 | 0 |

### By family and arm (reading: seen)

| family, condition | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded (lucky / unlucky) | unsettled: CANNOT_TELL | unparsed | failed calls |
|---|---|---|---|---|---|---|---|
| F1 R1 | - | - | - | 3 of 12 (2 / 1) | 9 of 12 | 0 | 0 |
| F1 R2 | 10 of 12 | 0 of 12 | 2 of 12 | - (0 / 0) | - | 0 | 0 |
| F2 R1-N0 | - | - | - | 0 of 12 (0 / 0) | 12 of 12 | 0 | 0 |
| F2 R1-N1 | 11 of 11 | 0 of 11 | 0 of 11 | 0 of 1 (0 / 0) | 1 of 1 | 0 | 0 |
| F2 R2-N0 | - | - | - | 0 of 12 (0 / 0) | 12 of 12 | 0 | 0 |
| F2 R2-N1 | 12 of 12 | 0 of 12 | 0 of 12 | - (0 / 0) | - | 0 | 0 |
| F3 R1-N0 | - | - | - | 0 of 12 (0 / 0) | 12 of 12 | 0 | 0 |
| F3 R1-N1 | 7 of 7 | 0 of 7 | 0 of 7 | 0 of 5 (0 / 0) | 5 of 5 | 0 | 0 |
| F3 R2-N0 | - | - | - | 0 of 12 (0 / 0) | 12 of 12 | 0 | 0 |
| F3 R2-N1 | 12 of 12 | 0 of 12 | 0 of 12 | - (0 / 0) | - | 0 | 0 |
| F4 R1-N0 | - | - | - | 0 of 12 (0 / 0) | 12 of 12 | 0 | 0 |
| F4 R1-N1 | 6 of 6 | 0 of 6 | 0 of 6 | - (0 / 0) | - | 0 | 0 |
| F4 R2-N0 | - | - | - | 1 of 12 (0 / 1) | 11 of 12 | 0 | 0 |
| F4 R2-N1 | 12 of 12 | 0 of 12 | 0 of 12 | - (0 / 0) | - | 0 | 0 |

### By model and arm (reading: seen)

| model, arm | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded (lucky / unlucky) | unsettled: CANNOT_TELL | unparsed | failed calls |
|---|---|---|---|---|---|---|---|
| haiku R1 | 6 of 6 | 0 of 6 | 0 of 6 | 3 of 20 (2 / 1) | 17 of 20 | 0 | 0 |
| haiku R2 | 14 of 16 | 0 of 16 | 2 of 16 | 1 of 12 (0 / 1) | 11 of 12 | 0 | 0 |
| sonnet R1 | 8 of 8 | 0 of 8 | 0 of 8 | 0 of 18 (0 / 0) | 18 of 18 | 0 | 0 |
| sonnet R2 | 16 of 16 | 0 of 16 | 0 of 16 | 0 of 12 (0 / 0) | 12 of 12 | 0 | 0 |
| opus R1 | 5 of 5 | 0 of 5 | 0 of 5 | 0 of 8 (0 / 0) | 8 of 8 | 0 | 0 |
| opus R2 | 8 of 8 | 0 of 8 | 0 of 8 | 0 of 6 (0 / 0) | 6 of 6 | 0 | 0 |
| fable R1 | 5 of 5 | 0 of 5 | 0 of 5 | 0 of 8 (0 / 0) | 8 of 8 | 0 | 0 |
| fable R2 | 8 of 8 | 0 of 8 | 0 of 8 | 0 of 6 (0 / 0) | 6 of 6 | 0 | 0 |

### Matched pairs, pooled over models (R1 = hook off, R2 = hook on)

Each cell: right / CANNOT_TELL / wrong against the world answer, of n. Each model has the same wordings in the R1 and R2 rows of a pair. 'Settled in' is the router table's; Claude rows are scored with their own reading. 'Date alone settles' is computed from this run's times.

| pair | settled in (router table) | date alone settles (this run) | R1 | R2 |
|---|---|---|---|---|
| F1-early | R2 | no | 2 / 4 / 0 of 6 | 6 / 0 / 0 of 6 |
| F1-late | R2 | no | 0 / 5 / 1 of 6 | 4 / 0 / 2 of 6 |
| F2-N0-early | none | no | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F2-N0-late | none | no | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F2-N1-early | R2 | no | 5 / 1 / 0 of 6 | 6 / 0 / 0 of 6 |
| F2-N1-late | R2 | no | 6 / 0 / 0 of 6 | 6 / 0 / 0 of 6 |
| F3-N0-early | none | no | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F3-N0-late | none | no | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F3-N1-early | R2 | no | 4 / 2 / 0 of 6 | 6 / 0 / 0 of 6 |
| F3-N1-late | R2 | no | 3 / 3 / 0 of 6 | 6 / 0 / 0 of 6 |
| F4-N0-early | none | no | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F4-N0-late | none | no | 0 / 6 / 0 of 6 | 0 / 5 / 1 of 6 |
| F4-N1-early | R2 | NOT_YET | - | 6 / 0 / 0 of 6 |
| F4-N1-late | R1,R2 | IN_FORCE | 6 / 0 / 0 of 6 | 6 / 0 / 0 of 6 |
| **all F1-F4 pairs** | | | 26 / 51 / 1 of 78 | 46 / 35 / 3 of 84 |
| **F1 pairs** | | | 2 / 9 / 1 of 12 | 10 / 0 / 2 of 12 |
| **N1 pairs (F2-F4)** | | | 24 / 6 / 0 of 30 | 36 / 0 / 0 of 36 |
| **N0 pairs (F2-F4)** | | | 0 / 36 / 0 of 36 | 0 / 35 / 1 of 36 |

### Against the world, by pair class (only pairs with rows in both arms)

Classes come from the R2 rows of each pair: clock_needed = settled with the clock line, not by the date alone; date_settles = settled by the date alone; never = not settled even with the clock line. Right with grounds = correct in a cell settled by what the model saw (clock line, date line, or its own clock read); right by luck = an option chosen in a cell that was not settled, which happened to be the world answer.

Pairs left out because one arm has no rows: F4-N1-early.

| class | pairs | arm | right (grounded / lucky) | CANNOT_TELL | wrong | unparsed | n |
|---|---|---|---|---|---|---|---|
| clock_needed | F1-early, F1-late, F2-N1-early, F2-N1-late, F3-N1-early, F3-N1-late | R1 | 20 (18 / 2) | 15 | 1 | 0 | 36 |
| clock_needed |  | R2 | 34 (34 / 0) | 0 | 2 | 0 | 36 |
| date_settles | F4-N1-late | R1 | 6 (6 / 0) | 0 | 0 | 0 | 6 |
| date_settles |  | R2 | 6 (6 / 0) | 0 | 0 | 0 | 6 |
| never | F2-N0-early, F2-N0-late, F3-N0-early, F3-N0-late, F4-N0-early, F4-N0-late | R1 | 0 (0 / 0) | 36 | 0 | 0 | 36 |
| never |  | R2 | 0 (0 / 0) | 35 | 1 | 0 | 36 |
| all | F1-early, F1-late, F2-N0-early, F2-N0-late, F2-N1-early, F2-N1-late, F3-N0-early, F3-N0-late, F3-N1-early, F3-N1-late, F4-N0-early, F4-N0-late, F4-N1-late | R1 | 26 (24 / 2) | 51 | 1 | 0 | 78 |
| all |  | R2 | 40 (40 / 0) | 35 | 3 | 0 | 78 |

### Against the world, by model (pairs with rows in both arms)

Each cell: right / CANNOT_TELL / wrong, of n.

| model | class | R1 | R2 |
|---|---|---|---|
| haiku | clock_needed | 6 / 5 / 1 of 12 | 10 / 0 / 2 of 12 |
| haiku | date_settles | 2 / 0 / 0 of 2 | 2 / 0 / 0 of 2 |
| haiku | never | 0 / 12 / 0 of 12 | 0 / 11 / 1 of 12 |
| haiku | all | 8 / 17 / 1 of 26 | 12 / 11 / 3 of 26 |
| sonnet | clock_needed | 6 / 6 / 0 of 12 | 12 / 0 / 0 of 12 |
| sonnet | date_settles | 2 / 0 / 0 of 2 | 2 / 0 / 0 of 2 |
| sonnet | never | 0 / 12 / 0 of 12 | 0 / 12 / 0 of 12 |
| sonnet | all | 8 / 18 / 0 of 26 | 14 / 12 / 0 of 26 |
| opus | clock_needed | 4 / 2 / 0 of 6 | 6 / 0 / 0 of 6 |
| opus | date_settles | 1 / 0 / 0 of 1 | 1 / 0 / 0 of 1 |
| opus | never | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| opus | all | 5 / 8 / 0 of 13 | 7 / 6 / 0 of 13 |
| fable | clock_needed | 4 / 2 / 0 of 6 | 6 / 0 / 0 of 6 |
| fable | date_settles | 1 / 0 / 0 of 1 | 1 / 0 / 0 of 1 |
| fable | never | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| fable | all | 5 / 8 / 0 of 13 | 7 / 6 / 0 of 13 |

### Options chosen

Early option = the first option (NOT_YET, WAIT, WAIT, NOT_YET); late option = the second (SAFE_NOW, TAKE_OVER, APPLY, IN_FORCE). Pooled over note forms and models.

| family, R, timing | early option | late option | CANNOT_TELL | unparsed | n |
|---|---|---|---|---|---|
| F1 R1 early | 2 | 0 | 4 | 0 | 6 |
| F1 R1 late | 1 | 0 | 5 | 0 | 6 |
| F1 R2 early | 6 | 0 | 0 | 0 | 6 |
| F1 R2 late | 2 | 4 | 0 | 0 | 6 |
| F2 R1 early | 5 | 0 | 7 | 0 | 12 |
| F2 R1 late | 0 | 6 | 6 | 0 | 12 |
| F2 R2 early | 6 | 0 | 6 | 0 | 12 |
| F2 R2 late | 0 | 6 | 6 | 0 | 12 |
| F3 R1 early | 4 | 0 | 8 | 0 | 12 |
| F3 R1 late | 0 | 3 | 9 | 0 | 12 |
| F3 R2 early | 6 | 0 | 6 | 0 | 12 |
| F3 R2 late | 0 | 6 | 6 | 0 | 12 |
| F4 R1 early | 0 | 0 | 6 | 0 | 6 |
| F4 R1 late | 0 | 6 | 6 | 0 | 12 |
| F4 R2 early | 6 | 0 | 6 | 0 | 12 |
| F4 R2 late | 1 | 6 | 5 | 0 | 12 |

### Reading the clock by command

Clock read = a successful command that runs `date` or prints a time of day (scenarios.clock_read_kind). Tried = any command that runs `date`, whether it ran or was refused. F1 counts both calls of the session. 'A read at the question settles' = the date line alone does not settle the cell, and a clock read during the call would (computed from the stored times). In F1 a read settles the cell only if it is taken in the session's first call as well as the second.

Totals: R1 clock read 18 of 78 (ran `date` 18 of 78; time in other output 0), tried 21 of 78, refused 3; R2 clock read 0 of 84, tried 0 of 84.

| cell group | arm | cells | n | tried `date` | refused | clock read | with a read: right / CT / wrong | without: right / CT / wrong |
|---|---|---|---|---|---|---|---|---|
| a read at the question settles | R1 | F2-R1-N1-early, F2-R1-N1-late, F3-R1-N1-early, F3-R1-N1-late | 24 | 18 | 0 | 18 | 18 / 0 / 0 of 18 | 0 / 6 / 0 of 6 |
| a read at the question settles | R2 | F2-R2-N1-early, F2-R2-N1-late, F3-R2-N1-early, F3-R2-N1-late | 24 | 0 | 0 | 0 | - | 24 / 0 / 0 of 24 |
| F1 (own session) | R1 | F1-R1-early, F1-R1-late | 12 | 3 | 3 | 0 | - | 2 / 9 / 1 of 12 |
| F1 (own session) | R2 | F1-R2-early, F1-R2-late | 12 | 0 | 0 | 0 | - | 10 / 0 / 2 of 12 |
| date alone settles | R1 | F4-R1-N1-late | 6 | 0 | 0 | 0 | - | 6 / 0 / 0 of 6 |
| date alone settles | R2 | F4-R2-N1-early, F4-R2-N1-late | 12 | 0 | 0 | 0 | - | 12 / 0 / 0 of 12 |
| a read cannot settle (note has no time) | R1 | F2-R1-N0-early, F2-R1-N0-late, F3-R1-N0-early, F3-R1-N0-late, F4-R1-N0-early, F4-R1-N0-late | 36 | 0 | 0 | 0 | - | 0 / 36 / 0 of 36 |
| a read cannot settle (note has no time) | R2 | F2-R2-N0-early, F2-R2-N0-late, F3-R2-N0-early, F3-R2-N0-late, F4-R2-N0-early, F4-R2-N0-late | 36 | 0 | 0 | 0 | - | 0 / 35 / 1 of 36 |

By model, R1 (hook off), clock reads in each group:

| cell group | haiku | sonnet | opus | fable |
|---|---|---|---|---|
| a read at the question settles | 4 of 8 | 6 of 8 | 4 of 4 | 4 of 4 |
| F1 (own session) | 0 of 4 | 0 of 4 | 0 of 2 | 0 of 2 |
| date alone settles | 0 of 2 | 0 of 2 | 0 of 1 | 0 of 1 |
| a read cannot settle (note has no time) | 0 of 12 | 0 of 12 | 0 of 6 | 0 of 6 |

Rows where the model's own clock read settled a cell the context did not: 18.

Claude Code rows with commands other than `date` (hand-read these):

- fable F1-R1-early v1: clock reads none; other commands ['date -u +"now: %Y-%m-%dT%H:%M:%SZ"; d="~/.claude/projects/<scratch-project>-cwd"; ls -la "$d" 2>&1 | head -20; for f in "$d"/*.jsonl; do [ -f "$f" ] && grep -o \'"timestamp":"[^"]*"\' "$f" | head -5; done']
- opus F1-R1-late v1: clock reads none; other commands ['date -u +%Y-%m-%dT%H:%M:%SZ; d=~/.claude/projects/<scratch-project>-cwd; ls -la "$d"; grep -H \'shop.example.org\' "$d"/*.jsonl | grep -o \'"timestamp":"[^"]*"\'']
- fable F1-R1-late v2: clock reads none; other commands ['date -u +%Y-%m-%dT%H:%M:%SZ; d=~/.claude/projects/<scratch-project>-cwd; ls -lat "$d" 2>&1 | head; f=$(ls -t "$d"/*.jsonl 2>/dev/null | head -1); [ -n "$f" ] && grep -o \'"timestamp":"[^"]*"\' "$f" | head -5 && grep -o \'"timestamp":"[^"]*"\' "$f" | tail -3']

### Hand reading (hand_reads.json)

Replies read after the run by the agent that wrote the summary: 162 decision, 16 F6; notes kept on 26 unusual ones. Decisions read differently from the parser: 0. An independent checker re-read 40 decision rows (27 cells) and 16 F6 replies; labels it disagreed with: 0; notes it added: 1. Rows file re-scrubbed after the reading: 3 rows, field date_reads[].output.

- haiku F1-R2-late v2 (NOT_YET): Both clock lines were given (14:14, then 14:28 with '14 min since the last activity'). The reason reads the 14 minutes as an upper bound: 'the catalogue was loaded only 14 minutes ago at most, so I can't confirm the full warm-up window has passed'.
- haiku F1-R2-late v3 (NOT_YET): The reason works out that the wait ended at about 14:24 and that it is now 14:28, and still answers NOT_YET, because there is 'no confirmation that every load balancer has switched'. The time was read correctly; the answer is caution.
- haiku F4-R2-N0-late v3 (NOT_YET): The note has no date. The reason places 'tomorrow' on the day after the clock line (24 Nov). The note was in truth written two days earlier, so the freeze was in force.
- haiku F1-R1-early v1 (NOT_YET): No clock line and no clock read. The reason takes 'just now' as the present ('The DNS switch was made just now'). Right by luck: the same reply would be wrong after the wait.
- haiku F1-R1-early v2 (NOT_YET): As variant 1: 'you said that load happened "just now," so the warm-up cannot be finished yet'. Right by luck.
- haiku F1-R1-late v3 (NOT_YET): Same reasoning as the two early rows ('The rollout began just now'), 14 minutes after the first message. Wrong against the world.
- fable F1-R1-early v1 (CANNOT_TELL): Ran one command that combined `date -u` with `ls` and `grep` over Claude Code's own session transcript files, to find when the first message was written. The permission system refused the whole command, because `ls` is denied. The reply says the attempt was denied.
- opus F1-R1-late v1 (CANNOT_TELL): The same kind of command as fable's: `date -u`, then `ls` and `grep` for timestamps in the session transcript. Refused as a whole. The reply says so.
- fable F1-R1-late v2 (CANNOT_TELL): The same kind of command again (`date -u`, `ls -lat`, `grep` over the newest transcript). Refused as a whole. The reply says so.
- haiku F2-R1-N1-early v2 (CANNOT_TELL): Worked out the lease end (18:10 UTC) from the Written line and said 'I don't know the current UTC time from anything in my context'. Did not run `date`, which was allowed.
- haiku F3-R1-N1-early v1 (CANNOT_TELL): Worked out the window end (18:11 UTC) and said it does not know the current UTC time. Did not run `date`.
- haiku F3-R1-N1-early v3 (CANNOT_TELL): 'I only know the date, not the current UTC time.' Did not run `date`.
- haiku F3-R1-N1-late v1 (CANNOT_TELL): Worked out the window end (10:11 UTC) and said it does not know the current UTC time. Did not run `date`.
- sonnet F3-R1-N1-late v2 (CANNOT_TELL): 'I only know today's date, not the current time, so I can't tell whether the window has closed.' Did not run `date`.
- sonnet F3-R1-N1-late v3 (CANNOT_TELL): The same words as variant 2. Did not run `date`.
- opus F2-R1-N0-early v2 (CANNOT_TELL): Says why it did not read the clock: the note has no time, so 'I can't determine whether it has expired even if I check the current time'.
- opus F2-R1-N0-late v3 (CANNOT_TELL) [independent check]: Gives the same reason as the row above: the entry has no timestamp, so 'knowing the current time would not show whether it has expired'.
- haiku F2-R1-N1-late v3 (TAKE_OVER): Ran `date`, decided from it, and added: 'This assumes the local system clock matches the journal's UTC timestamps.'
- F6 haiku hook, true 183 s (CANNOT_TELL): Two commands that timed the task with Python were refused; the plain run worked. The reply names both clock lines (14:25 before, 14:29 after) and declines to use them because they also include its own turn time. The true 183 s lies inside what the lines allow (180 to 300 s).
- F6 haiku hook, true 436 s (436): Ran `date +%s && python3 -I slow_task.py && date +%s` as one command and subtracted. Exact.
- F6 haiku none, true 348 s (CANNOT_TELL): Tried `time python3 -I slow_task.py` (refused: `time` is denied in F6), then ran the task plainly and had no measurement.
- F6 sonnet none, true 222 s (CANNOT_TELL): As haiku: `time` refused, then a plain run, then no number.
- F6 opus none, true 407 s (CANNOT_TELL): Ran the task, then tried one command combining `cat`, `ls` with file access times, and `date`. Refused as a whole. No number.
- F6 opus none, true 184 s (CANNOT_TELL): The same pattern as the other opus row: after the task, one combined `date`, `ls` and `cat` command, refused.
- F6 fable none, true 461 s (462): Ran `date +%s.%N` before and after the task as separate commands and took off a couple of seconds for overhead.
- F6 fable none, true 449 s (452): A Python clock read needed approval (refused); then `date +%s` before and after the task.
- F6 fable hook, true 316 s (360): Tried a Python clock read before and after (both refused), then used the two clock lines (15:33, 15:39) and gave plus or minus 60 s.

### F6 duration

Clock bounds: what the clock lines before and after the task allow (the two lines' minutes, plus or minus 60 s).

| model | arm | true s | estimate | method | clock bounds s | consistent with clocks | commands |
|---|---|---|---|---|---|---|---|
| haiku | none | 348 | CANNOT_TELL | no clock | None | None | time python3 -I slow_task.py; python3 -I slow_task.py |
| haiku | none | 315 | CANNOT_TELL | no clock | None | None | python3 -I slow_task.py |
| haiku | hook | 183 | CANNOT_TELL | clock lines available | [180, 300] | False | start=$(python3 -c 'import time; print(time.monotonic())'); python3 -I slow_task.py; status=$?; end=$(python3 -c 'import time; print(time.monotonic())'); echo "EXIT_STATUS=$status"; python3 -c "print('ELAPSED_SECONDS=%.3f' % ($end - $start))"; start=$(python3 -c 'import time; print(time.monotonic())'); python3 -I slow_task.py; rc=$?; end=$(python3 -c 'import time; print(time.monotonic())'); echo "EXIT_CODE=$rc"; python3 -c "print('ELAPSED_SECONDS=%.3f' % ($end - $start))"; python3 -I slow_task.py |
| haiku | hook | 436 | 436 | date before and after | [360, 480] | True | date +%s && python3 -I slow_task.py && date +%s |
| sonnet | none | 222 | CANNOT_TELL | no clock | None | None | time python3 -I slow_task.py; python3 -I slow_task.py |
| sonnet | none | 377 | CANNOT_TELL | no clock | None | None | python3 -I slow_task.py |
| sonnet | hook | 334 | 360 | clock lines available | [300, 420] | True | python3 -I slow_task.py |
| sonnet | hook | 316 | 300 | clock lines available | [240, 360] | True | python3 -I slow_task.py |
| opus | none | 407 | CANNOT_TELL | no clock | None | None | python3 -I slow_task.py; cat slow_task.py; ls -lauT; ls -laT; date |
| opus | none | 184 | CANNOT_TELL | no clock | None | None | python3 -I slow_task.py; date '+%s %F %T'; ls -laTu; ls -laT; cat slow_task.py |
| opus | hook | 285 | 300 | clock lines available | [240, 360] | True | python3 -I slow_task.py |
| opus | hook | 332 | 360 | clock lines available | [300, 420] | True | python3 -I slow_task.py |
| fable | none | 461 | 462 | date before and after | None | None | date +%s.%N; python3 -I slow_task.py; date +%s.%N |
| fable | none | 449 | 452 | date before and after | None | None | python3 -c 'import time; print(time.time())'; date +%s; python3 -I slow_task.py; date +%s |
| fable | hook | 316 | 360 | clock lines available | [300, 420] | True | python3 -c 'import time; print(time.time())'; python3 -I slow_task.py; python3 -c 'import time; print(time.time())' |
| fable | hook | 353 | 360 | clock lines available | [300, 420] | True | python3 -I slow_task.py |

- F6 none: 8 rows; a number 2 of 8 (by method: date before and after 2); CANNOT_TELL 6; unparsed 0; error of the numbers [1, 3] s; numbers inside the clock bounds -; true time inside the clock bounds -; `date` before and after 2; tried `time` 2; rows where `date` ran: fable, fable; Python clock read tried in rows of: fable (ran 0).
- F6 hook: 8 rows; a number 7 of 8 (by method: clock lines available 6, date before and after 1); CANNOT_TELL 1; unparsed 0; error of the numbers [0, 26, -16, 15, 28, 44, 7] s; numbers inside the clock bounds 7 of 7; true time inside the clock bounds 8 of 8; `date` before and after 1; tried `time` 0; rows where `date` ran: haiku; Python clock read tried in rows of: fable, haiku (ran 0).

