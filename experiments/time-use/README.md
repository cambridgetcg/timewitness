# Does a clock line help an agent use time?

This folder holds one experiment. It asks whether an agent makes better decisions that depend on elapsed time when each prompt carries a clock line, and whether it notices when the time it needs is missing.

The clock line is the text that `hooks/clock-line.py`, a Claude Code hook in this project, adds to each prompt: weekday, date, time of day and zone, and, after 10 minutes or more of silence, how long the silence was. One that a model received in this run:

```
Clock: Mon 23 Nov 2026, 14:28 GMT (UTC+0). 14 min since the last activity in this session.
```

**What ran.** Only the Claude Code arm: four Claude models (haiku, sonnet, opus, fable), 162 decision rows and 16 duration rows, on 2026-11-23 between 14:09 and 15:45 UTC. The other arm, open models through Hugging Face Inference Providers, did not run. The account's pre-paid credit ran out at 13:38 UTC the same day, during the group experiment in `experiments/consensus/`, before this arm's first call at 14:08 UTC; both of its calls got HTTP 402 and cost nothing. So nothing is known from this experiment about open models, about the condition with no date at all, or about the stale-date family F5. The command that runs that arm once the account has credit is under "Limits".

## Results in short

Counts are k of n. The samples are small: 6 rows per cell, 1 or 2 per model, from one afternoon on one machine. "Hook on" means the clock line was given; "hook off" means it was not, but the model could still run `date`.

- **Where the clock line settles the answer and the date alone does not** (36 rows per arm). Hook on: 34 right, 0 CANNOT_TELL, 2 wrong (of 36). Hook off: 20 right, 15 CANNOT_TELL, 1 wrong (of 36); 18 of the 20 right answers came from the model running `date` itself, and 2 were lucky guesses.
- **Notes with no time on them** (36 rows per arm). By design, a note without a written time cannot be placed in time, so no answer of this kind is settled, with or without the clock line. The models said so (CANNOT_TELL) in 71 of 72 rows: 36 with the hook off and 35 with it on. The other reply, with the hook on, chose an option and was wrong.
- **Reading the clock unasked.** With the hook off, the models ran `date` in 18 of 24 rows where one reading would settle the answer, and in 0 of the 42 rows where a reading would add nothing. With the hook on, no model ran a clock command in F1 to F4 (0 of 84).
- **Waiting inside one session** (F1). With the hook off, no reply showed that 3 minutes differ from 14: in 12 rows none answered SAFE_NOW (9 CANNOT_TELL, 3 NOT_YET). With it on, 10 right, 0 CANNOT_TELL, 2 wrong (of 12). The two wrong were haiku answering NOT_YET after the wait had passed; one of the two worked the times out correctly and stayed cautious.
- **Wrong answers against the world** (pairs that ran in both arms): 3 of 78 with the hook on, 1 of 78 with it off. All 4 are haiku's; sonnet, opus and fable gave no wrong answer in either arm.
- **How long a task took** (F6, 16 rows). With clock lines before and after the task, 7 of 8 replies gave a number (6 from the clock lines, off by 7 to 44 s; 1 from `date`, exact). With the hook off, 2 of 8 did (all fable, using `date` before and after, off by 1 to 3 s).
- **Notes with a written time** (F2 to F4 with a Written line). With the clock line, every row was right (36 of 36). With the hook off, 24 right, 6 CANNOT_TELL, 0 wrong (of 30); 18 of the right answers came from the model's own `date`. See "Hand-overs between agents".

## Words used here

- **Clock line**: the line the hook adds to each prompt (example above).
- **Hook on / hook off**: the two conditions of the Claude Code arm. They are called R2 and R1 in the code and the data. Claude Code always tells the model today's date, so hook off still gives the date. One tool was allowed in both: running `date`.
- **Note**: a journal entry written by another agent (families F2 to F4). **N0**: the note uses relative words only ("I have just claimed", "starts tomorrow"). **N1**: the same note with a first line "Written: YYYY-MM-DD HH:MM UTC".
- **Early / late**: each scenario is asked twice, once when the first option is right (early) and once when the second is right (late).
- **Settled**: the information the model has fixes the right option. Worked out per cell (and per row in this arm), before looking at replies. "Has" includes a time the model read itself with `date`.
- **World answer**: the option that is right given the true times, whether or not the model could know them.
- **Right / wrong against the world**: the option chosen is, or is not, the world answer. CANNOT_TELL is counted apart.
- **Unfounded decision**: an option chosen in a cell that is not settled, instead of CANNOT_TELL. **Lucky** if it happens to be the world answer, **unlucky** if not. A right answer in a settled cell is **right with grounds**.
- **Matched pair**: the hook-off and hook-on rows of one scenario (same family, note form and timing), with the same wordings for each model. Pairs fall into three **classes**: the clock line is needed (settled with it, not by the date alone), the date alone settles it, or never settled (the note carries no time).
- **Clock read**: a command that ran and printed the time (`date`, in practice). **Tried**: any command that runs `date`, whether it ran or was refused.

## The question

When the right action depends on how much time has passed, does giving the agent the current time, and giving notes an absolute timestamp, change what it does? And when the needed time is missing, does the agent say so (CANNOT_TELL), or does it guess?

## The design in plain words

Every prompt describes a situation, offers two options and CANNOT_TELL, and asks for one line `DECISION: <option>` and one sentence of reason. CANNOT_TELL is always allowed, and the prompt says it means "the information you have does not settle the question".

Families (each has a threshold; three wordings each, with different names, durations and times):

- **F1 wait** (own session). The person says a change went in just now and needs a fixed wait before the next step; the state cannot be checked. Later the person asks whether the next step is safe. NOT_YET / SAFE_NOW. In the Claude Code arm the wait is 10 minutes and the session is resumed for real after about 3 (early) or about 14 minutes (late).
- **F2 lease** (hand-over). Another agent's journal entry: it claimed a task with a 6-hour lease; take over only after the lease expires. WAIT / TAKE_OVER. Asked 2 h (early) or 9 h (late) after the claim.
- **F3 window** (agreement by silence). A proposal passes if nobody objects within 24 hours; no objection is recorded. WAIT / APPLY. Asked 20 h or 28 h after it was opened.
- **F4 relative day** (hand-over). A note says a freeze "starts tomorrow at 09:00 UTC" and runs seven days. Is it in force? NOT_YET / IN_FORCE. Asked 10 h or 40 h after the note.
- **F5 stale date** (router arm only). The conversation began with "Today's date is D0"; nine days later the person asks how many days are left to a deadline at D0 + 12. Not run.
- **F6 duration** (Claude Code arm only, optional). The model runs a script that sleeps for a hidden 180 to 480 seconds and says how long it took. The spec asked for 45 to 120 seconds; a design check before the full run changed it, because the clock line shows whole minutes, so an estimate from two clock lines can be off by up to a minute, which is most of such a short task.

Two arms were planned:

- **Router arm**: 8 open models through Hugging Face Inference Providers, with the whole context written by the script, so it has three time conditions: R0 nothing, R1 the date only, R2 the date and a clock line made by the hook's own code; 46 cells, 3 wordings, 1112 calls planned. Not run (see "What ran").
- **Claude Code arm**: the real harness (Claude Code 2.1.330, `claude -p`), the real hook passed with `--settings`, and real waiting. No user settings, no MCP servers, an empty working folder outside the project. Hook off and hook on differ only in the `--settings` value. One tool was allowed, `Bash(date:*)`, and commands that print a time (`ls`, `stat`, `uptime`, `find`, `who`, `w`, `last`, `ps`) were denied in both conditions. F2 to F4 ran as one fresh session per row, with note times computed from the real time of the call. F1 created each session, waited, and resumed it with `--resume`. Each cell got 6 rows: 2 wordings for haiku, 2 wordings for sonnet, 1 wording for opus, 1 wording for fable, with the same wordings in the hook-off and hook-on rows of a pair.

An F2 prompt with a Written line (N1), as sent at 14:11 UTC; with the hook on, the model also received `Clock: Mon 23 Nov 2026, 14:11 GMT (UTC+0).`:

```
You are picking up work from a shared task journal that several agents write to. This is the newest entry for the task "migrate the invoices table":

---
Written: 2026-11-23 05:11 UTC
agent-kestrel: I have just claimed this task. My lease on it runs for 6 hours.
---

The team's rule: an agent may take over a claimed task only after the claim's lease has expired. There is no later entry for this task. Should you take over the task now?

Reply with one line that is exactly `DECISION: WAIT`, `DECISION: TAKE_OVER` or `DECISION: CANNOT_TELL`, and then one sentence giving your reason. CANNOT_TELL means the information you have does not settle the question.
```

An F1 session with the hook on. First call: "I switched the DNS record for shop.example.org to the new server just now. It needs 10 minutes to propagate, and there is no way to check propagation from here, so the old server has to stay on for the full 10 minutes. Nothing to do yet; please acknowledge in one line." Second call, 851 s later: "Is it safe to turn off the old server now?" plus the same reply instruction. Clock lines received: `Clock: Mon 23 Nov 2026, 14:14 GMT (UTC+0).`, then `Clock: Mon 23 Nov 2026, 14:28 GMT (UTC+0). 14 min since the last activity in this session.`.

## The cell table

Which cells are settled, worked out by hand for the router arm and checked against a mechanical reading (interval arithmetic in `scenarios.settle`, `check_table()`: 0 disagreements over 46 cells and 3 wordings). A bold option means the cell is settled and that option is right. 11 of 46 router cells are settled. The Claude Code arm uses the R1 (hook off) and R2 (hook on) columns; its last column gives the rows it has.

| family | note | timing | world answer | R0 nothing | R1 date | R2 date + clock line | Claude Code rows (hook off / on) |
|---|---|---|---|---|---|---|---|
| F1 wait (own session) | - | early | NOT_YET | not settled | not settled | **NOT_YET** | 6 / 6 |
| F1 wait (own session) | - | late | SAFE_NOW | not settled | not settled | **SAFE_NOW** | 6 / 6 |
| F2 lease (hand-over) | N0 relative | early | WAIT | not settled | not settled | not settled | 6 / 6 |
| F2 lease (hand-over) | N0 relative | late | TAKE_OVER | not settled | not settled | not settled | 6 / 6 |
| F2 lease (hand-over) | N1 Written line | early | WAIT | not settled | not settled | **WAIT** | 6 / 6 |
| F2 lease (hand-over) | N1 Written line | late | TAKE_OVER | not settled | not settled | **TAKE_OVER** | 6 / 6 |
| F3 window (agreement by silence) | N0 relative | early | WAIT | not settled | not settled | not settled | 6 / 6 |
| F3 window (agreement by silence) | N0 relative | late | APPLY | not settled | not settled | not settled | 6 / 6 |
| F3 window (agreement by silence) | N1 Written line | early | WAIT | not settled | not settled | **WAIT** | 6 / 6 |
| F3 window (agreement by silence) | N1 Written line | late | APPLY | not settled | not settled | **APPLY** | 6 / 6 |
| F4 relative day (hand-over) | N0 relative | early | NOT_YET | not settled | not settled | not settled | 6 / 6 |
| F4 relative day (hand-over) | N0 relative | late | IN_FORCE | not settled | not settled | not settled | 6 / 6 |
| F4 relative day (hand-over) | N1 Written line | early | NOT_YET | not settled | not settled | **NOT_YET** | 0 / 6 |
| F4 relative day (hand-over) | N1 Written line | late | IN_FORCE | not settled | **IN_FORCE** | **IN_FORCE** | 6 / 6 |

| F5 cell | settled | world answer | reason |
|---|---|---|---|
| F5-R0 | not settled | 3 | No date anywhere, so the days left cannot be counted. |
| F5-R1s | stale (12 at its word) | 3 | The system message gives D0 as today's date, and nothing in the conversation says time has passed, so at the prompt's word the answer is 12. In truth nine days have passed and the answer is 3. A reader has no way to know the date is old, so the cell is scored on its own: followed the stated date (12), abstained (CANNOT_TELL), or other. |
| F5-R1f | **3** | 3 | The later notice gives today's date; the deadline is 3 days after it. |
| F5-R2 | **3** | 3 | The final clock line gives today's date (and says 9 d since the last activity); the deadline is 3 days after it. |

Three things differ in the Claude Code arm, and each row is scored with its own reading:

- Hook off is not the router's R1. The model could run `date`. A row where it did, and the reading settles the cell, is scored as settled. This is why F2 and F3 with a Written line can be settled with the hook off.
- Note times are computed from the time of the call, so what a cell means depends on the hour. The F2 to F4 rows ran at 14:09 to 14:14 UTC. At that hour the F4 early note was written on the same date as the question (at 04:12 to 04:13 UTC), so "tomorrow at 09:00" is the next day and the date alone settles NOT_YET. In the router design it does not. The runner therefore skipped the hook-off rows of F4-N1-early (all 6), and the hook-on rows of that pair say nothing about the clock line.
- F1 with the hook off: a single `date` at the question does not settle it, because nothing places the person's "just now" in time. Only a reading taken already in the first call would.

## Results

All numbers below are computed by `score.py` from the rows and written to `summary.md` and `summary.json`; this file is written from `summary.json` by `make_readme.py`.

### Router arm

Not run (see "What ran" above). The runner sent one date-canary call to the cheapest model (meta-llama/Llama-3.1-8B-Instruct) at 14:08 UTC, and the same call again 6 minutes later; both were refused (HTTP 402), and the runner stopped. Calls 2, failed 2, decision rows 0, spend USD 0.00 (cap USD 4.00). The other 7 models were not called. The planned models: `meta-llama/Llama-3.1-8B-Instruct`, `google/gemma-4-31B-it`, `Qwen/Qwen2.5-72B-Instruct`, `openai/gpt-oss-120b`, `deepseek-ai/DeepSeek-V4.1-Flash-1017`, `zai-org/GLM-5.3`, `moonshotai/Kimi-K2.5`, `thinkingmachines/Inkling-2-Small`.

One entry of the arm's price table names another model than the one it prices: `moonshotai/Kimi-K2.5` is priced as `moonshotai/Kimi-K2.6` (`priced_as` in `run_context_router.json`). That model was never called, so nothing here depends on it.

An earlier smoke test of this arm (24 replies from two models, an older design) is kept in `smoke/` and is not a result.

### Claude Code arm: did the set-up work?

- Calls 206, rows 181 (canary_clock 2, canary_resume 1, decision 162, f6 16), failed calls 0. Rows planned 168; missing 6, all in F4-R1-N1-early (see above). `python3 -I -B run_claude.py --scratch DIR --cells F4-R1-N1-early` fills them when run from 04:00 to 08:54 UTC, the hours when every F2 to F4 cell matches the router table.
- The clock line reached the model in 84 of 84 hook-on rows and in 0 of 78 hook-off rows. A canary with the hook on quoted the line; one with the hook off said there was none.
- F1: 24 of 24 resumes reported the same session as their first call, and a canary confirmed that a resumed session carries the first turn. Resumes came 181 to 188 s (early) and 840 to 851 s (late) after the first call. The gap sentence appeared in 6 of 6 late hook-on resumes and in 0 of 6 early ones, as the hook's 10-minute rule says.
- Replies: 162 of 162 have exactly one DECISION line, and it is the first line; none was unparsed. 10 replies, all sonnet's, put the reason on the DECISION line itself instead of the next line; the parse is the same. How the replies were read by hand is under "Hand reading".
- The hook in every row is the file with SHA-256 `2416e1bc45725b04...`, the same as `hooks/clock-line.py` now.

### Settled and unsettled cells

Pooled over models, each row scored with what the model saw (its prompt, the date line, the clock lines and any clock it read itself):

| | settled: correct | settled: CANNOT_TELL | settled: wrong | unsettled: unfounded (lucky / unlucky) | unsettled: CANNOT_TELL |
|---|---|---|---|---|---|
| hook off | 24 of 24 | 0 of 24 | 0 of 24 | 3 of 54 (2 / 1) | 51 of 54 |
| hook on | 46 of 48 | 0 of 48 | 2 of 48 | 1 of 36 (0 / 1) | 35 of 36 |

The two rows cover different cells, so they are not a comparison; the matched pairs below are. With the hook off, 18 of the 24 settled rows were settled only because the model ran `date`; scored on the prompt alone, those 18 would count as unfounded decisions, and the hook-off row would read 21 of 72 unfounded instead of 3 of 54. Every unfounded decision (4 in all) is haiku's, and in a settled cell no model ever answered CANNOT_TELL.

### Against the world: matched pairs

Right / CANNOT_TELL / wrong against the world answer, of n, pooled over models. Each pair has the same wordings with the hook off and on.

| pair | class | hook off | hook on |
|---|---|---|---|
| F1-early | clock line needed | 2 / 4 / 0 of 6 | 6 / 0 / 0 of 6 |
| F1-late | clock line needed | 0 / 5 / 1 of 6 | 4 / 0 / 2 of 6 |
| F2-N0-early | never settled | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F2-N0-late | never settled | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F2-N1-early | clock line needed | 5 / 1 / 0 of 6 | 6 / 0 / 0 of 6 |
| F2-N1-late | clock line needed | 6 / 0 / 0 of 6 | 6 / 0 / 0 of 6 |
| F3-N0-early | never settled | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F3-N0-late | never settled | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F3-N1-early | clock line needed | 4 / 2 / 0 of 6 | 6 / 0 / 0 of 6 |
| F3-N1-late | clock line needed | 3 / 3 / 0 of 6 | 6 / 0 / 0 of 6 |
| F4-N0-early | never settled | 0 / 6 / 0 of 6 | 0 / 6 / 0 of 6 |
| F4-N0-late | never settled | 0 / 6 / 0 of 6 | 0 / 5 / 1 of 6 |
| F4-N1-early | date alone settles | not run | 6 / 0 / 0 of 6 |
| F4-N1-late | date alone settles | 6 / 0 / 0 of 6 | 6 / 0 / 0 of 6 |

By class, over the pairs that ran in both arms:

| class | hook off: right (with grounds / lucky) | CANNOT_TELL | wrong | hook on: right (with grounds / lucky) | CANNOT_TELL | wrong | n per arm |
|---|---|---|---|---|---|---|---|
| clock line needed | 20 (18 / 2) | 15 | 1 | 34 (34 / 0) | 0 | 2 | 36 |
| date alone settles | 6 (6 / 0) | 0 | 0 | 6 (6 / 0) | 0 | 0 | 6 |
| never settled | 0 (0 / 0) | 36 | 0 | 0 (0 / 0) | 35 | 1 | 36 |
| all | 26 (24 / 2) | 51 | 1 | 40 (40 / 0) | 35 | 3 | 78 |

### Per model

Settled and unsettled use each row's own reading; the pair columns are right / CANNOT_TELL / wrong against the world. The last column is how often the model ran `date` with the hook off in the rows where one reading would settle the cell (F2 and F3 with a Written line).

| model | settled correct, hook off | hook on | unfounded, hook off | hook on | clock-needed pairs, hook off | hook on | all pairs, hook off | hook on | ran `date` when it would settle |
|---|---|---|---|---|---|---|---|---|---|
| haiku | 6 of 6 | 14 of 16 | 3 of 20 | 1 of 12 | 6 / 5 / 1 of 12 | 10 / 0 / 2 of 12 | 8 / 17 / 1 of 26 | 12 / 11 / 3 of 26 | 4 of 8 |
| sonnet | 8 of 8 | 16 of 16 | 0 of 18 | 0 of 12 | 6 / 6 / 0 of 12 | 12 / 0 / 0 of 12 | 8 / 18 / 0 of 26 | 14 / 12 / 0 of 26 | 6 of 8 |
| opus | 5 of 5 | 8 of 8 | 0 of 8 | 0 of 6 | 4 / 2 / 0 of 6 | 6 / 0 / 0 of 6 | 5 / 8 / 0 of 13 | 7 / 6 / 0 of 13 | 4 of 4 |
| fable | 5 of 5 | 8 of 8 | 0 of 8 | 0 of 6 | 4 / 2 / 0 of 6 | 6 / 0 / 0 of 6 | 5 / 8 / 0 of 13 | 7 / 6 / 0 of 13 | 4 of 4 |

Model ids reported: haiku = `claude-haiku-5-5`; sonnet = `claude-sonnet-5-5`; opus = `claude-opus-5-5`; fable = `claude-fable-5-2`.

### Options chosen, and the pull of the wording

Every note and every F1 first turn is worded as if no time has passed ("just now", "I have just claimed", "starts tomorrow"), which points to the first option. In F1 to F3 the first option is also the cautious one; in F4 it is not. Pooled over note forms and models:

| family, arm, timing | first option | second option | CANNOT_TELL | n |
|---|---|---|---|---|
| F1 hook off early | 2 (NOT_YET) | 0 (SAFE_NOW) | 4 | 6 |
| F1 hook off late | 1 (NOT_YET) | 0 (SAFE_NOW) | 5 | 6 |
| F1 hook on early | 6 (NOT_YET) | 0 (SAFE_NOW) | 0 | 6 |
| F1 hook on late | 2 (NOT_YET) | 4 (SAFE_NOW) | 0 | 6 |
| F2 hook off early | 5 (WAIT) | 0 (TAKE_OVER) | 7 | 12 |
| F2 hook off late | 0 (WAIT) | 6 (TAKE_OVER) | 6 | 12 |
| F2 hook on early | 6 (WAIT) | 0 (TAKE_OVER) | 6 | 12 |
| F2 hook on late | 0 (WAIT) | 6 (TAKE_OVER) | 6 | 12 |
| F3 hook off early | 4 (WAIT) | 0 (APPLY) | 8 | 12 |
| F3 hook off late | 0 (WAIT) | 3 (APPLY) | 9 | 12 |
| F3 hook on early | 6 (WAIT) | 0 (APPLY) | 6 | 12 |
| F3 hook on late | 0 (WAIT) | 6 (APPLY) | 6 | 12 |
| F4 hook off early | 0 (NOT_YET) | 0 (IN_FORCE) | 6 | 6 |
| F4 hook off late | 0 (NOT_YET) | 6 (IN_FORCE) | 6 | 12 |
| F4 hook on early | 6 (NOT_YET) | 0 (IN_FORCE) | 6 | 12 |
| F4 hook on late | 1 (NOT_YET) | 6 (IN_FORCE) | 5 | 12 |

Every unfounded decision and every wrong answer in this run chose the first option. Without the hook, F1 never got the second option (SAFE_NOW), early or late.

### What the clock line changed, and what it did not

Changed:

- In the pairs where it is needed, it turned CANNOT_TELL into right answers: CANNOT_TELL 15 to 0, right 20 to 34 (of 36).
- The gain was largest where `date` on request could not help: in F1 2 right, 9 CANNOT_TELL, 1 wrong (of 12) with the hook off, 10 right, 0 CANNOT_TELL, 2 wrong (of 12) with it on. In F2 and F3 with a Written line the models could and mostly did read the clock themselves, so the gain was smaller: 18 right, 6 CANNOT_TELL, 0 wrong (of 24) with the hook off, 24 right, 0 CANNOT_TELL, 0 wrong (of 24) with it on.
- With the clock line, no model ran a clock command in F1 to F4 (0 of 84), against 18 of 78 with the hook off (21 of 78 tried; the three refused were the F1 transcript reads described below).

Did not change, or made worse:

- A note with no time on it stayed unanswerable, as designed: no right answer in 36 hook-off and 36 hook-on rows, and 36 and 35 CANNOT_TELL. With the hook on, 25 of 36 of these replies quoted the clock line's time: 24 of them answered CANNOT_TELL, and 1 (haiku, F4-R2-N0-late, variant 3) used the clock line's date to place "tomorrow" and answered wrong.
- Wrong answers did not go down. Over the pairs that ran in both arms there were 3 of 78 with the hook on and 1 of 78 with it off, all haiku's. Two are F1 late rows where haiku saw both clock lines and still chose NOT_YET: one read "14 minutes ago" as an upper bound, the other computed that the wait had ended and stayed cautious. The third (F4, no Written line) placed "tomorrow" on the day after the clock line's date. These are 3 rows from one model: they show that a clock line does not by itself make a model use the time well, not how often that happens.
- Unfounded decisions were already rare with the hook off: 3 of 54, against 1 of 36 with it on.
- Where the date alone settles the answer, both arms were right in every row (6 of 6 and 6 of 6).

### Did Claude read the clock by itself when it had no clock line?

Yes, and mostly when it helped. With the hook off:

- In the 24 rows where one reading at the question settles the cell (F2 and F3 with a Written line), the model ran `date` in 18. All 18 of those were right. The 6 that did not read the clock all answered CANNOT_TELL, each saying in some form that it did not know the current time, although `date` was allowed.
- By model: haiku 4 of 8, sonnet 6 of 8, opus 4 of 4, fable 4 of 4. Each rate rests on 4 to 8 rows, too few to rank the models.
- In the 42 rows where a reading could not help (the note has no time, or the date already settles it), no model ran `date`. Two replies said so: knowing the current time would not show whether a lease with no start time had expired (opus, F2-R1-N0-early, variant 2; opus, F2-R1-N0-late, variant 3).
- In F1 (own session) no model read the clock in the first call of the session, which is the only reading that could have settled it. In the second call 3 of 12 tried one command that combined `date` with `ls` and `grep` over Claude Code's own session transcript files, which hold a timestamp for every turn. The permission system refused each whole command, because `ls` is denied, and the replies said so. Those files are a clock source the design did not list.
- With the hook on, no model ran a clock command in F1 to F4 (0 of 84). In F6 with the hook on, haiku ran `date` before and after the task in one row, and haiku and fable tried Python clock reads, which were refused (see "How long a task took").

### How long a task took (F6)

Two rows per model and condition, 16 in all. The task slept for a hidden 183 to 461 s. Hook on here means the hook on two events: a clock line when the prompt is sent and one after each command. `time` was denied, so the task could not be timed directly. Clock bounds: what the two clock lines allow (their minutes, plus or minus 60 s).

| model | hook | true s | estimate | method | clock bounds s |
|---|---|---|---|---|---|
| haiku | off | 348 | CANNOT_TELL | no clock | - |
| haiku | off | 315 | CANNOT_TELL | no clock | - |
| haiku | on | 183 | CANNOT_TELL | clock lines available | 180 to 300 |
| haiku | on | 436 | 436 | date before and after | 360 to 480 |
| sonnet | off | 222 | CANNOT_TELL | no clock | - |
| sonnet | off | 377 | CANNOT_TELL | no clock | - |
| sonnet | on | 334 | 360 | clock lines available | 300 to 420 |
| sonnet | on | 316 | 300 | clock lines available | 240 to 360 |
| opus | off | 407 | CANNOT_TELL | no clock | - |
| opus | off | 184 | CANNOT_TELL | no clock | - |
| opus | on | 285 | 300 | clock lines available | 240 to 360 |
| opus | on | 332 | 360 | clock lines available | 300 to 420 |
| fable | off | 461 | 462 | date before and after | - |
| fable | off | 449 | 452 | date before and after | - |
| fable | on | 316 | 360 | clock lines available | 300 to 420 |
| fable | on | 353 | 360 | clock lines available | 300 to 420 |

- Hook off: 2 of 8 gave a number, all fable, by running `date` before and after (off by 1 to 3 s). Six other replies said CANNOT_TELL; 2 of them had first tried `time` (denied).
- Hook on: 7 of 8 gave a number, all inside the clock bounds: 6 from the clock lines (off by 7 to 44 s) and 1 from `date` (exact). The one CANNOT_TELL (haiku) had the clock lines and declined to use them because they include its own turn time; the true time was inside the bounds.
- So in this run the clock line made a duration estimate common (7 of 8 against 2 of 8), at about a minute's precision. This rests on 8 rows per arm, 2 per model. `date` before and after was precise to a few seconds, but it was used in only 3 of 16 rows (haiku once with the hook on, fable twice with the hook off).

### Calls and cost

| model | model id reported | calls | rows | cost USD reported by the CLI |
|---|---|---|---|---|
| haiku | claude-haiku-5-5 | 70 | 61 | 0.0278 |
| sonnet | claude-sonnet-5-5 | 66 | 58 | 0.3692 |
| opus | claude-opus-5-5 | 35 | 31 | 0.5035 |
| fable | claude-fable-5-2 | 35 | 31 | 1.0206 |
| total | | 206 | 181 | 1.9211 |

The cost is Claude Code's own `total_cost_usd` per call, summed over the stored rows (an F1 row stores its second call only). How it is billed on the account was not checked.

## Elapsed time inside a session

F1 and F6 ask about time the model lived through, not time written in a note. Reading the clock on request gives the time now; it says how long something took only if the model also read the clock at the start. In this run that rarely happened:

- F1, hook off: the change was announced in the session's first call, and no model read the clock in that call (0 of 12 sessions). So at the question nothing could settle the answer: 2 right, 9 CANNOT_TELL, 1 wrong (of 12).
- F6, hook off: 2 of 8 replies read the clock before and after the task, and they gave the only numbers.
- The clock line puts a time on every turn without being asked, so the start is always on record. F1 with it: 10 right, 0 CANNOT_TELL, 2 wrong (of 12). F6 with it: 7 of 8 replies gave a number.

## Hand-overs between agents

F2 (a lease), F3 (a proposal that passes by silence, a simple form of agreement) and F4 (a freeze announced with "tomorrow") are notes one agent leaves for another. What this run shows about them:

- Without a Written line, by design no answer is settled: a reader with a perfect clock still cannot place "just" or "tomorrow". No right answer in 36 hook-off and 36 hook-on rows; 36 and 35 CANNOT_TELL, so the models said so in 71 of 72 rows.
- With a Written line and the clock line, every row was right: 36 of 36. With a Written line and the hook off: 24 right, 6 CANNOT_TELL, 0 wrong (of 30); 18 of the right ones came from the model's own `date`, and 6 from F4 late, where the date line settles it.
- Agreement by silence (F3) with a Written line: 12 right, 0 CANNOT_TELL, 0 wrong (of 12) with the hook on, 7 right, 5 CANNOT_TELL, 0 wrong (of 12) with it off. Leases (F2): 12 right, 0 CANNOT_TELL, 0 wrong (of 12) on, 11 right, 1 CANNOT_TELL, 0 wrong (of 12) off.
- So the clock line could only help notes that carry a written time, as designed. On those notes it made every answer right; without it the reader had to think of running `date`, and in 6 of 24 rows where that would have settled the answer it did not.

This run took every Written line at its word. Whether such a line is true is a different question; the message stamps described in the main README address it, and they were not used here.

## Hand reading

The agent that wrote the summary read every reply after the run: 162 decision replies and 16 F6 replies. Each decision reply opens with its DECISION line, and that reading agreed with the parser on all of them (0 read differently). It kept notes on the 26 replies that were unusual (`hand_reads.json`, listed below); for the other replies no record is kept, so that part of the reading cannot be checked from the files.

An independent checker later re-read 40 decision rows chosen at random (one from each of the 27 cells that have rows, then 13 more) and all 16 F6 replies, and agreed with every stored label and estimate. It added one note, marked below. `hand_reads.json` lists the rows it read, each with its label.

`score.py` stops if `rows_claude.jsonl` is not the file these readings describe (it checks the file's SHA-256), if a noted or checked row reads differently, or if a count no longer matches. The replies that went wrong, guessed, or did something unusual:

- haiku, F1-R2-late, variant 2 (NOT_YET): Both clock lines were given (14:14, then 14:28 with '14 min since the last activity'). The reason reads the 14 minutes as an upper bound: 'the catalogue was loaded only 14 minutes ago at most, so I can't confirm the full warm-up window has passed'.
- haiku, F1-R2-late, variant 3 (NOT_YET): The reason works out that the wait ended at about 14:24 and that it is now 14:28, and still answers NOT_YET, because there is 'no confirmation that every load balancer has switched'. The time was read correctly; the answer is caution.
- haiku, F4-R2-N0-late, variant 3 (NOT_YET): The note has no date. The reason places 'tomorrow' on the day after the clock line (24 Nov). The note was in truth written two days earlier, so the freeze was in force.
- haiku, F1-R1-early, variant 1 (NOT_YET): No clock line and no clock read. The reason takes 'just now' as the present ('The DNS switch was made just now'). Right by luck: the same reply would be wrong after the wait.
- haiku, F1-R1-early, variant 2 (NOT_YET): As variant 1: 'you said that load happened "just now," so the warm-up cannot be finished yet'. Right by luck.
- haiku, F1-R1-late, variant 3 (NOT_YET): Same reasoning as the two early rows ('The rollout began just now'), 14 minutes after the first message. Wrong against the world.
- fable, F1-R1-early, variant 1 (CANNOT_TELL): Ran one command that combined `date -u` with `ls` and `grep` over Claude Code's own session transcript files, to find when the first message was written. The permission system refused the whole command, because `ls` is denied. The reply says the attempt was denied.
- opus, F1-R1-late, variant 1 (CANNOT_TELL): The same kind of command as fable's: `date -u`, then `ls` and `grep` for timestamps in the session transcript. Refused as a whole. The reply says so.
- fable, F1-R1-late, variant 2 (CANNOT_TELL): The same kind of command again (`date -u`, `ls -lat`, `grep` over the newest transcript). Refused as a whole. The reply says so.
- haiku, F2-R1-N1-early, variant 2 (CANNOT_TELL): Worked out the lease end (18:10 UTC) from the Written line and said 'I don't know the current UTC time from anything in my context'. Did not run `date`, which was allowed.
- haiku, F3-R1-N1-early, variant 1 (CANNOT_TELL): Worked out the window end (18:11 UTC) and said it does not know the current UTC time. Did not run `date`.
- haiku, F3-R1-N1-early, variant 3 (CANNOT_TELL): 'I only know the date, not the current UTC time.' Did not run `date`.
- haiku, F3-R1-N1-late, variant 1 (CANNOT_TELL): Worked out the window end (10:11 UTC) and said it does not know the current UTC time. Did not run `date`.
- sonnet, F3-R1-N1-late, variant 2 (CANNOT_TELL): 'I only know today's date, not the current time, so I can't tell whether the window has closed.' Did not run `date`.
- sonnet, F3-R1-N1-late, variant 3 (CANNOT_TELL): The same words as variant 2. Did not run `date`.
- opus, F2-R1-N0-early, variant 2 (CANNOT_TELL): Says why it did not read the clock: the note has no time, so 'I can't determine whether it has expired even if I check the current time'.
- opus, F2-R1-N0-late, variant 3 (CANNOT_TELL, added by the checker): Gives the same reason as the row above: the entry has no timestamp, so 'knowing the current time would not show whether it has expired'.
- haiku, F2-R1-N1-late, variant 3 (TAKE_OVER): Ran `date`, decided from it, and added: 'This assumes the local system clock matches the journal's UTC timestamps.'

F6:

- haiku, hook on, true 183 s (CANNOT_TELL): Two commands that timed the task with Python were refused; the plain run worked. The reply names both clock lines (14:25 before, 14:29 after) and declines to use them because they also include its own turn time. The true 183 s lies inside what the lines allow (180 to 300 s).
- haiku, hook on, true 436 s (436): Ran `date +%s && python3 -I slow_task.py && date +%s` as one command and subtracted. Exact.
- haiku, hook off, true 348 s (CANNOT_TELL): Tried `time python3 -I slow_task.py` (refused: `time` is denied in F6), then ran the task plainly and had no measurement.
- sonnet, hook off, true 222 s (CANNOT_TELL): As haiku: `time` refused, then a plain run, then no number.
- opus, hook off, true 407 s (CANNOT_TELL): Ran the task, then tried one command combining `cat`, `ls` with file access times, and `date`. Refused as a whole. No number.
- opus, hook off, true 184 s (CANNOT_TELL): The same pattern as the other opus row: after the task, one combined `date`, `ls` and `cat` command, refused.
- fable, hook off, true 461 s (462): Ran `date +%s.%N` before and after the task as separate commands and took off a couple of seconds for overhead.
- fable, hook off, true 449 s (452): A Python clock read needed approval (refused); then `date +%s` before and after the task.
- fable, hook on, true 316 s (360): Tried a Python clock read before and after (both refused), then used the two clock lines (15:33, 15:39) and gave plus or minus 60 s.

## Limits

- **One arm.** The router arm did not run. The account's pre-paid credit ran out at 13:38 UTC the same day, during the group experiment in `experiments/consensus/`, before this arm's first call at 14:08 UTC; both calls got HTTP 402 and cost nothing. So nothing is known from this experiment about open models, about the condition with no date at all, about the stale-date family F5, or about a condition with the date but no way to read the clock: hook off here is "date plus a clock on request". Once the account has credit, the arm runs from this folder with `"$PY" -I -B run_router.py`, `PY` set as in the re-run block below; it runs every row not yet done and stops at USD 4.00.
- **Small and narrow.** 162 decision rows, 6 per cell, 1 or 2 per model; 16 F6 rows. One sitting (2026-11-23, 14:09 to 15:45 UTC), one machine, one network, Claude Code 2.1.330. Differences of one or two rows are noise.
- **The hour matters.** F2 to F4 note times follow the time of the call. In this run the F4 early note fell on the day of the question, so F4-N1-early is settled by the date and its hook-off rows were skipped. Every F2 to F4 cell matches the router design only from 04:00 to 08:54 UTC (London winter time; computed with the runner's own rule). This run's F2 to F4 rows ran at 14:09 to 14:14 UTC, outside that window.
- **The wording leans one way.** Every scenario is worded as if no time has passed, and in F1 to F3 that is also the cautious option. In the N0 and F1 hook-off cells the early and late prompts of one wording are the same text, so "lucky" and "unlucky" there show a model's default, not reasoning; all 3 unfounded hook-off decisions are in F1. (With a Written line the early and late prompts differ.)
- **"One tool" was not enforced.** Claude Code runs commands it treats as read-only (`echo` ran in the canary). The commands that print a time were denied, and a command with a denied part is refused as a whole; that is what stopped the three attempts to read the session transcripts. Other permissions could change the hook-off F1 numbers.
- **Frame.** The clock line arrives as hook context, which the model sees as a system note, not as part of the person's message.
- **F1 scoring** assumes the person's "just now" was at most 2 minutes before the first message.
- **F6 clock bounds** are rough: the first line comes when the prompt is sent, before the task starts.
- **Written lines** were taken at their word.
- **Context.** Claude Code put account details in the model's context even with all setting sources off (the hook-off canary reply mentions an e-mail block). No such detail is stored in the rows; they were scrubbed and checked.
- **Rows edited after the run.** Three stored strings were scrubbed again after the run. They are the `date_reads[].output` of three F1 hook-off rows, each a copy of a refused command's error text; the runner had cut them short before scrubbing, so they kept the start of the scratch folder's name. They were rebuilt from the same rows' scrubbed tool results. No reply, decision or label changed. `run_claude.py` now scrubs before it cuts, and `score.py` stops if a row holds a piece of the scratch folder's name.
- **Cost** is as the CLI reports it; billing was not checked. Model ids are as Claude Code reported them.

## Files and how to re-run

| File | What it is |
|---|---|
| `scenarios.py` | Families, wordings, timelines, the expected-answer table (`EXPECTED`), the mechanical reading (`settle`), the clock line made by the hook's own code, the reply parser. `python3 -I -B scenarios.py` checks the table. |
| `run_claude.py` | Claude Code arm. |
| `run_router.py` | Router arm (not run). |
| `common.py` | Scrubbing and JSON-lines helpers. |
| `slow_task.py` | The F6 task: sleeps for `TIME_USE_SLEEP_S` seconds, prints DONE. |
| `rows_claude.jsonl` | 181 rows: every call, reply, command, clock line and expected reading. |
| `rows_router.jsonl` | 2 rows, both failed calls (HTTP 402). |
| `run_context_router.json` | The router arm's models, prices and base date. |
| `score.py` | Re-parses every reply, labels the rows, writes `summary.md` and `summary.json`. |
| `hand_reads.json` | Notes from the hand reading, the rows the independent checker re-read, and the SHA-256 of `rows_claude.jsonl` with the record of the three re-scrubbed strings. |
| `make_readme.py` | Writes this file from `summary.json`. |
| `smoke/` | Smoke-test rows from before the full run; not results. |

From this folder (the working folder for Claude Code must be outside the project; its sessions are deleted with `--purge` once the rows are stored):

```
python3 -I -B scenarios.py                                   # table check
python3 -I -B run_claude.py --scratch DIR --canary            # hook on/off and resume checks
python3 -I -B run_claude.py --scratch DIR --families F1       # any hour; about 15 minutes
python3 -I -B run_claude.py --scratch DIR --families F2,F3,F4 # matches the router table 04:00 to 08:54 UTC
python3 -I -B run_claude.py --scratch DIR --f6                # optional; up to about 2 hours
python3 -I -B run_claude.py --scratch DIR --purge
PY="$(head -1 "$(command -v hf)" | sed 's/^#!//')"
"$PY" -I -B run_router.py                                    # needs Inference Providers credits; stops at USD 4
python3 -I -B score.py
python3 -I -B make_readme.py
```

## Appendix: the expected-answer table

For the router arm's timelines (all 46 cells, the same for each of the 3 wordings). "stale" marks F5-R1s, scored on its own: at the prompt's word the answer is 12, in the world 3.

| cell | settled | right option | world answer | reason |
|---|---|---|---|---|
| F1-R0-early | no | - | NOT_YET | Nothing in the context gives a time or a date, so the time that has passed cannot be known. 'Just now' was said at an unknown moment. |
| F1-R0-late | no | - | SAFE_NOW | Nothing in the context gives a time or a date, so the time that has passed cannot be known. 'Just now' was said at an unknown moment. |
| F1-R1-early | no | - | NOT_YET | Only today's date is given; both turns fall on that date and a wait of minutes cannot be timed from a date. |
| F1-R1-late | no | - | SAFE_NOW | Only today's date is given; both turns fall on that date and a wait of minutes cannot be timed from a date. |
| F1-R2-early | yes | NOT_YET | NOT_YET | The clock lines on the two user messages are 5/7/9 min apart and the change went in just before the first of them, so less than the 15/20/30 min wait has passed (even allowing 2 min for 'just' and 1 min for each line's rounding). No gap sentence: the pause is under 10 min. |
| F1-R2-late | yes | SAFE_NOW | SAFE_NOW | The final clock line says 22/31/44 min since the last activity, the assistant's reply, which came after the change, so more than the 15/20/30 min wait has passed. |
| F2-R0-N0-early | no | - | WAIT | Neither the note nor the context gives a time. |
| F2-R0-N0-late | no | - | TAKE_OVER | Neither the note nor the context gives a time. |
| F2-R0-N1-early | no | - | WAIT | The claim time is written, but nothing says what time it is now. |
| F2-R0-N1-late | no | - | TAKE_OVER | The claim time is written, but nothing says what time it is now. |
| F2-R1-N0-early | no | - | WAIT | Today's date is known, but 'I have just claimed' is relative to an unknown moment. |
| F2-R1-N0-late | no | - | TAKE_OVER | Today's date is known, but 'I have just claimed' is relative to an unknown moment. |
| F2-R1-N1-early | no | - | WAIT | The claim (03:10/07:45/11:20) and today share one date and the lease ends later that same day, so a date without a time of day cannot tell before from after. |
| F2-R1-N1-late | no | - | TAKE_OVER | The claim (03:10/07:45/11:20) and today share one date and the lease ends later that same day, so a date without a time of day cannot tell before from after. |
| F2-R2-N0-early | no | - | WAIT | Now is known to the minute, but the claim time is not. |
| F2-R2-N0-late | no | - | TAKE_OVER | Now is known to the minute, but the claim time is not. |
| F2-R2-N1-early | yes | WAIT | WAIT | Clock minus Written is 2 h, less than the 6 h lease. |
| F2-R2-N1-late | yes | TAKE_OVER | TAKE_OVER | Clock minus Written is 9 h, more than the 6 h lease. |
| F3-R0-N0-early | no | - | WAIT | Neither the note nor the context gives a time. |
| F3-R0-N0-late | no | - | APPLY | Neither the note nor the context gives a time. |
| F3-R0-N1-early | no | - | WAIT | The opening time is written, but nothing says what time it is now. |
| F3-R0-N1-late | no | - | APPLY | The opening time is written, but nothing says what time it is now. |
| F3-R1-N0-early | no | - | WAIT | Today's date is known, but the opening time is not. |
| F3-R1-N0-late | no | - | APPLY | Today's date is known, but the opening time is not. |
| F3-R1-N1-early | no | - | WAIT | Today is the day after the opening, and the window closes on that same day at the opening's time of day (06:40/10:15/13:30); a date without a time of day cannot settle it. |
| F3-R1-N1-late | no | - | APPLY | Today is the day after the opening, and the window closes on that same day at the opening's time of day (06:40/10:15/13:30); a date without a time of day cannot settle it. |
| F3-R2-N0-early | no | - | WAIT | Now is known to the minute, but the opening time is not. |
| F3-R2-N0-late | no | - | APPLY | Now is known to the minute, but the opening time is not. |
| F3-R2-N1-early | yes | WAIT | WAIT | Clock minus Written is 20 h, inside the 24 h window. |
| F3-R2-N1-late | yes | APPLY | APPLY | Clock minus Written is 28 h, past the 24 h window, and no objection is recorded. |
| F4-R0-N0-early | no | - | NOT_YET | Neither the note nor the context gives a date or a time. |
| F4-R0-N0-late | no | - | IN_FORCE | Neither the note nor the context gives a date or a time. |
| F4-R0-N1-early | no | - | NOT_YET | The note's date fixes the start (09:00 the next day), but nothing says what time it is now. |
| F4-R0-N1-late | no | - | IN_FORCE | The note's date fixes the start (09:00 the next day), but nothing says what time it is now. |
| F4-R1-N0-early | no | - | NOT_YET | The note's date is unknown, so 'tomorrow' cannot be placed. |
| F4-R1-N0-late | no | - | IN_FORCE | The note's date is unknown, so 'tomorrow' cannot be placed. |
| F4-R1-N1-early | no | - | NOT_YET | Today is the day after the note, the day the freeze starts at 09:00; the date alone cannot tell whether 09:00 has passed (it is 02:20/04:45/07:10). |
| F4-R1-N1-late | yes | IN_FORCE | IN_FORCE | Today is two days after the note: the freeze started at 09:00 yesterday and runs seven days, so the date alone settles it. |
| F4-R2-N0-early | no | - | NOT_YET | Now is known, but the note's date is not, so 'tomorrow' cannot be placed. |
| F4-R2-N0-late | no | - | IN_FORCE | Now is known, but the note's date is not, so 'tomorrow' cannot be placed. |
| F4-R2-N1-early | yes | NOT_YET | NOT_YET | The clock shows the day after the note, before 09:00 (02:20/04:45/07:10). |
| F4-R2-N1-late | yes | IN_FORCE | IN_FORCE | The clock shows two days after the note, after the 09:00 start of the day before, and inside the seven days. |
| F5-R0 | no | - | 3 | No date anywhere, so the days left cannot be counted. |
| F5-R1s | stale | - | 3 | The system message gives D0 as today's date, and nothing in the conversation says time has passed, so at the prompt's word the answer is 12. In truth nine days have passed and the answer is 3. A reader has no way to know the date is old, so the cell is scored on its own: followed the stated date (12), abstained (CANNOT_TELL), or other. |
| F5-R1f | yes | 3 | 3 | The later notice gives today's date; the deadline is 3 days after it. |
| F5-R2 | yes | 3 | 3 | The final clock line gives today's date (and says 9 d since the last activity); the deadline is 3 days after it. |

