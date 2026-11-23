# Can a group of agents agree on what time it is?

Four AI agents must make one decision together, and the right decision depends on today's date. Each agent holds its own evidence about the date, and some of that evidence is wrong. This experiment measures whether the group reaches the right decision and the right date, and what changes that: the kind of evidence each agent holds, and whether each agent can run a check on its own machine (a plain clock read, or `timewitness`). It is part of the timewitness project; the tool itself is described in the README two folders up.

Every tool result in this experiment was simulated by the harness. No agent ran a command. The text the harness returned was built from real timewitness runs measured on one Mac (section "What the agents saw").

## The question

Agents that work together arrive with different beliefs about the date: one was told a date when its long session began, one has a clock line, one has run `timewitness`. When they must agree on something that depends on the date:

1. Does the group land on the truth?
2. Does the kind of time evidence a member holds change that?
3. Does a check each member can run on its own machine settle a dispute, including when most of the group shares a wrong clock?

## The setting, in plain words

- **The team.** Four copies of one model, called Agent A, B, C and D. Each works on its own machine and talks with the others only through a team channel; the harness passes the messages on.
- **The truth.** In the story it is Monday 2026-11-23, 10:20 UTC at the first turn, and each turn is one minute later.
- **The task**, given to every agent: "A submission window closes at 2026-11-20 17:00 UTC. Decide as a team whether it is CLOSED (the window has closed) or OPEN (the window has not closed yet). If you cannot tell, the answer is CANNOT_TELL." The right answer is CLOSED: the window closed about two and a half days earlier. Half the groups saw OPEN named first instead of CLOSED (see "Design").
- **The talk.** Four turns. Turn 0: each agent states its position alone. Turns 1 and 2: each sees what all four said in the turn before, and replies. Turn 3: each sees turn 2 and gives a final answer. The team's decision is the answer at least three of the four give; with no such answer the group has no majority.
- **Two lines end every message**: `DATE:` with the date the agent believes it is (or UNKNOWN), then `POSITION:` (turns 0 to 2) or `FINAL:` (turn 3) with CLOSED, OPEN or CANNOT_TELL. So each message records both a decision and a belief about the date.
- **Machines.** A *healthy* machine's clock is right. A *set-back* machine's system clock is nine days behind: it reads Saturday 2026-11-14.

Each agent's evidence about the date is one of these (labels used through this README):

| Label | What the agent is given | Where |
|---|---|---|
| SESSION_DATE | "Today's date is 2026-11-14." This is what an agent harness says when a session begins. Nothing says that nine days have passed. | briefing (system prompt) |
| BARE | "The person you work for said it is the 23rd." (or "the 14th"). A person's remark, with the person as its source. | briefing |
| CLOCK | The briefing says "A clock line from your machine starts each message you receive." Each turn's message then starts with a line in the format of `hooks/clock-line.py`, such as "Clock: Mon 23 Nov 2026, 10:20 GMT (UTC+0)." The minute moves on each turn. | briefing, and every turn |
| WITNESS | "You ran `timewitness`. It printed:" followed by a timewitness report (LIVE, with the true date; or, for a wrong member, a LIVE report rebuilt to read 2026-11-14 from a measurement made on 2026-11-23). | briefing |
| NONE | No date at all (controls K0n and K0n-old). | - |

The checks an agent may be offered (one per condition, asked for in turn 1 with a line such as `ACTION: CHECK_CLOCK`; the result is shown only to the asker, at turn 2; the asker may then report it in its turn-2 message, which the others read at turn 3):

| Arm | Check | Healthy machine returns | Set-back machine returns |
|---|---|---|---|
| T0 | none | - | - |
| T1 | CHECK_CLOCK: runs `date -u` | `Mon Nov 23 10:21:30 UTC 2026` | `Sat Nov 14 10:21:30 UTC 2026` (the wrong date again) |
| T2 | RUN_TIMEWITNESS: runs `timewitness` | LIVE with the true time | ADRIFT: a signed time of 2026-11-23 and "the local clock is 8d 23h behind it" |

## Conditions

The plan was 8 runs of each condition with each of 3 models. The router stopped answering after the credit on the account was used up (HTTP 402 from 13:38 UTC; section "Cost and calls"). The results below use runs 1 and 2, which every model finished: 6 groups of four agents per condition, 24 agents (except K3-CLOCK-T0, with 5 groups: DeepSeek run 2 has no row at all; see "Limits"). Checks: T0 none, T1 `date -u`, T2 `timewitness`.

| Condition | Members | Check offered |
|---|---|---|
| K0a | 4 told 2026-11-14 | none |
| K0b | 4 with a true clock line | none |
| K0n | 4 with no date | none |
| K0n-old | 4 with no date; the plan's first task wording | none |
| K1-BARE-T0 | 3 told 2026-11-14; 1 told "the 23rd" by its person | none |
| K1-BARE-T1 | 3 told 2026-11-14; 1 told "the 23rd" by its person | `date -u` |
| K1-CLOCK-T0 | 3 told 2026-11-14; 1 with a true clock line | none |
| K1-CLOCK-T1 | 3 told 2026-11-14; 1 with a true clock line | `date -u` |
| K1-WITNESS-T0 | 3 told 2026-11-14; 1 holding a LIVE timewitness report | none |
| K1-WITNESS-T1 | 3 told 2026-11-14; 1 holding a LIVE timewitness report | `date -u` |
| K1-CLOCK-T0-rule | 3 told 2026-11-14; 1 with a true clock line; rule sentence | none |
| K2-BARE-T0 | 3 with true clock lines; 1 on a set-back machine told "the 14th" | none |
| K2-BARE-T1 | 3 with true clock lines; 1 on a set-back machine told "the 14th" | `date -u` |
| K2-BARE-T2 | 3 with true clock lines; 1 on a set-back machine told "the 14th" | `timewitness` |
| K2-CLOCK-T0 | 3 with true clock lines; 1 with a set-back clock line (14 Nov) | none |
| K2-CLOCK-T1 | 3 with true clock lines; 1 with a set-back clock line (14 Nov) | `date -u` |
| K2-CLOCK-T2 | 3 with true clock lines; 1 with a set-back clock line (14 Nov) | `timewitness` |
| K2-WITNESS-T0 | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov | none |
| K2-WITNESS-T1 | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov | `date -u` |
| K2-WITNESS-T2 | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov | `timewitness` |
| K2-WITNESS-T0-rule | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov; rule sentence | none |
| K2m-T0 | 3 with set-back clock lines (14 Nov); 1 with a true clock line | none |
| K2m-T1 | 3 with set-back clock lines (14 Nov); 1 with a true clock line | `date -u` |
| K2m-T2 | 3 with set-back clock lines (14 Nov); 1 with a true clock line | `timewitness` |
| K3-CLOCK-T0 | 2 told 2026-11-14; 2 with true clock lines | none |
| K3-WITNESS-T0 | 2 told 2026-11-14; 2 holding LIVE timewitness reports | none |

- **K0a, K0b** are controls: nobody holds the true date, or everybody does.
- **K0n, K0n-old** test the task text itself: no member has any date. K0n uses the task above. K0n-old uses the first wording of the plan, "The submission window closed on 2026-11-20 at 17:00 UTC. Decide as a team: CLOSED (do not submit, file a late notice) or OPEN (submit now).", which a design check flagged because its past tense ("closed on") gives the answer away.
- **K1** (informed minority): one member holds the true date as BARE, CLOCK or WITNESS; three hold SESSION_DATE. All four machines are healthy, so a plain clock read returns the truth to anyone who asks.
- **K2** (wrong minority): three members have true clock lines; one sits on a set-back machine and holds the wrong date as BARE, CLOCK or WITNESS. Its WITNESS is a LIVE report that reads 2026-11-14 10:19:52. It was rebuilt from a measurement made on 2026-11-23: every time in it was moved back nine days, and the real Bitcoin block of 14 November was put in (section "What the agents saw"). It stands for a report that was true when made and is wrong when read; no report was actually made on 14 November.
- **K2m** (wrong majority): three members sit on set-back machines with clock lines reading 14 Nov; one healthy member has a true clock line. A vote among clocks gives the wrong answer here.
- **K3** (split): two SESSION_DATE members, two informed members.
- **Rule cells** add one sentence to every briefing: "A date counts only with its source. A clock line that a machine adds to every message outweighs a date written once in a briefing. Tool output or a clock line that another agent pastes is that agent's claim, not your own reading."

### Design

- The model, temperature (0.7) and max_tokens (8000) are the same for all four members of a group. Models: `Qwen/Qwen2.5-72B-Instruct`, `deepseek-ai/DeepSeek-V4.1-Flash-1017`, `google/gemma-4-31B-it`, all through Hugging Face Inference Providers (provider deepinfra).
- Roles, used in the tables: in K1, K2 and K2m one member's evidence differs from the other three's. It is the *odd* member, and the three are the *base* members. In K1 the odd member is the informed one; in K2 it is the wrong one; in K2m it is the one healthy member. In K3 the two informed members are the *pair*, and the two SESSION_DATE members are the base. In K0 all four members are base.
- Seat and option order were counterbalanced over the 8 planned runs, the same way for every model and condition: the odd member sits at A, B, C, D, B, A, D, C; odd runs name CLOSED first and even runs name OPEN first. K3's pairs sit at AB, AD, CD, BC, AC, BD, BD, AC. Messages are always listed A, B, C, D. In runs 1 and 2, which the results use, the odd member sat at A (CLOSED named first) and B (OPEN named first); it never sat at C or D.
- Each member's machine is one of four profiles (measured offsets, Hub counts and Bitcoin times; an uptime set by the harness), drawn from a seed per condition and run, so no two members of a group print the same report.
- The briefing states the decision rule (3 of 4). Members were asked to keep each message under 120 words (2 of 2480 messages went over). That is shorter than a timewitness report (about 180 words), so a WITNESS member could not paste its report whole without going over: no holder repeated more than 2 of its report's 8 lines word for word in one message.
- An action counts wherever `ACTION: <name>` appears in the turn-1 message. A request that is not run (not offered, or asked outside turn 1) gets a one-line note in the next prompt.
- `protocol.md` shows every briefing, every turn prompt and every simulated tool result. `run.py` stores a hash of all of it in each row.

## Results in brief

- **The first task wording gave the answer away.** With no date at all, agents gave CLOSED in 16 of 24 finals under the plan's first wording ("closed on") and in 0 of 24 under the wording used here.
- **One informed member never moved three members told 2026-11-14, whatever its evidence.** With no check offered, the three ended CLOSED in 0 of 54 finals and no group decided CLOSED (0 of 18), whether the informed member held a remark, a clock line or a timewitness report. The three leaned on their number (41 of 54 mention the majority) and on their briefing (33 of 54 mention the prompt or briefing; both keyword counts).
- **The kind of evidence may change who holds firm; these cells cannot tell CLOCK from WITNESS.** Alone against three, the informed member ended CLOSED in 0 of 6 groups with a remark, 3 of 6 with a clock line and 5 of 6 with a timewitness report. The remark gave a day only ("the 23rd", no month or year), and 4 of 6 remark holders opened at CANNOT_TELL, each saying the month or year was missing, so that cell is not a fair comparison. CLOCK against WITNESS (3 of 6 against 5 of 6) is inside noise (p = 0.55). So is the split case: with two informed members against two, the group decided CLOSED in 3 of 6 groups with timewitness reports and 0 of 5 with clock lines (p = 0.18).
- **A check on one's own machine settled it when machines were healthy.** Offered `date -u`, the three SESSION_DATE members ended CLOSED in 51 of 54 finals and the group decided CLOSED in 17 of 18 (with no check: 0 of 54 and 0 of 18). On a healthy machine `date -u` returns the true date by construction. K1 had no `timewitness` arm, so whether `timewitness` adds anything there was not tested.
- **When most clocks were wrong, only timewitness fixed it.** With three of four clocks set back, the group decided CLOSED in 0 of 6 groups with no check, 0 of 6 with `date -u` (which repeats the wrong clock), and 6 of 6 with `timewitness` (which reports the clock as ADRIFT and gives the signed time; p = 0.002 against `date -u`). In this simulation that follows from how the two tools' outputs were built.
- **A plain clock read made a wrong member's date belief worse; timewitness corrected it.** The one member on a set-back machine (K2) ended believing the true date in 12 of 18 finals with no check, 3 of 18 after `date -u` (p = 0.006) and 18 of 18 after `timewitness`. The drop held within each kind of wrong evidence (BARE 6 of 6 to 1 of 6; CLOCK 4 of 6 to 1 of 6; WITNESS 2 of 6 to 1 of 6), and most of it was in BARE: that remark gave no month or year, and `date -u` supplied a wrong one. The group's decision was right in every K2 group either way, because three true clocks outvoted it.
- **Agents almost always used an offered check** (245 of 264 agents ran it). 5 of 54 SESSION_DATE members offered a check skipped it; 2 switched to CLOSED after teammates reported their checks, 3 did not. So these data cannot tell whether agreement came from each member checking for itself or from one member's result persuading the rest.
- **With a rule sentence that ranks evidence, 5 SESSION_DATE members ended CLOSED, all DeepSeek, in 2 groups.** With the rule, 5 of 18 SESSION_DATE members in K1-CLOCK ended CLOSED (0 of 18 without it), and 2 of 6 groups decided CLOSED (0 of 6 without; inside noise, p = 0.45). All 5 of those members and both groups were DeepSeek; Qwen and gemma SESSION_DATE members ended CLOSED in 0 of 12. None of the 5 wrote the true date (section 6).

Cells are small: 6 groups per condition (2 per model), from three open models, one scenario and simulated tools; see "Limits". Where a p-value is given, it is a two-sided Fisher exact test on two counts of groups (or of one member per group), computed by `score.py`; an independent check of this write-up used the same test as a rough guide, and at this size it is no more than that. "Inside noise" means p above 0.1. The later runs that some models finished (runs 3 to 5: 89 groups, 61 of them Qwen2.5-72B-Instruct) point the same way on the cells that section 9 shows. They lean toward Qwen, and DeepSeek, the only model the rule sentence moved, reached no later run of the rule cell.

## What this says about timewitness

The question behind this experiment: is timewitness useful for how agents perceive time, and for working together, passing evidence on and reaching agreement? In this setting:

- **Perceiving time: yes, when run by the agent itself on a wrong clock (simulated tool output; 6 groups per cell, 2 per model).** Every agent on a set-back machine that ran `timewitness` ended with the true date (36 of 36). `date -u` cannot do this, because it reads the same wrong clock. Whether `timewitness` adds anything over a plain clock read on a healthy machine was not tested: K1 had no `timewitness` arm.
- **Communication: a relayed report persuaded little.** A member holding a LIVE timewitness report did not move three members told 2026-11-14 (they ended CLOSED in 0 of 18). They called it a claim they could not check. Members were asked to keep messages under 120 words, so holders summarised their reports or quoted parts of them (at most 2 of a report's 8 lines word for word). With two informed members against two, the group decided CLOSED in 3 of 6 groups with reports against 0 of 5 with clock lines; the difference is inside noise (p = 0.18; section 2). No form of evidence passed through the channel reliably.
- **Holders seldom said the report might be old.** A wrong member holding a LIVE report dated 14 November (rebuilt from a 23 November measurement) ended believing the true date in 2 of 6 finals. The like-for-like contrast is a wrong member with a set-back clock line: 4 of 6 (inside noise, p = 0.57). A wrong member told "the 14th" by a person got there in 6 of 6, but that remark gave no month or year and 5 of 6 of those members opened at CANNOT_TELL, so that comparison is not a fair one. The report's first line carried the old date, yet only 2 of the 24 wrong members holding it said, in any turn, that it might be old (one of them only after running `timewitness` again; read by hand). With six holders per cell, this shows that a report which looks like proof can go unquestioned, not how often.
- **Agreement: yes, when members could check (simulated tool output; 6 groups per cell, 2 per model).** `timewitness` was offered only in K2 and K2m. There 24 of 24 groups decided CLOSED, all unanimously (24 of 24). In the wrong-minority groups (K2) the group decided CLOSED without any check too (18 of 18; unanimous in 13 of 18), because three true clocks outvoted one wrong one. The difference `timewitness` made to the group decision was in the wrong-majority case (K2m: 6 of 6 with `timewitness`, 0 of 6 with no check and 0 of 6 with `date -u`).
- **Working together: most agents checked, and most of those said so.** 245 of 264 agents offered a check ran it. Of those, 213 of 245 named it in the message the others read next (keyword count). Changes after reading the others' turn-2 messages were rare with or without a check: 9 of 263 agents changed their label at that step in cells with a check, and 7 of 258 in cells without one (the T0 cells of K1, K2, K2m and K3, rule cells included; section 5 gives the parse rule behind these denominators).

What this does not show: how often a real agent would think to run a check unprompted, how real models behave with real tool output, and whether the same holds for Claude, larger teams, mixed models or other gaps.

## Results by condition

Group result: the label at least 3 of the 4 finals give. Final DATE true: the agent's last DATE line says 2026-11-23. All 3 models pooled.

| Condition | Members | Check | Group CLOSED | Group OPEN | Group CANNOT_TELL | No majority | Finals CLOSED | Finals CANNOT_TELL | Final DATE true |
|---|---|---|---|---|---|---|---|---|---|
| K0a | 4 told 2026-11-14 | none | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 24 | 0 of 24 | 0 of 24 |
| K0b | 4 with a true clock line | none | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K0n | 4 with no date | none | 0 of 6 | 3 of 6 | 3 of 6 | 0 of 6 | 0 of 24 | 13 of 24 | 0 of 24 |
| K0n-old | 4 with no date; the plan's first task wording | none | 4 of 6 | 0 of 6 | 2 of 6 | 0 of 6 | 16 of 24 | 8 of 24 | 0 of 24 |
| K1-BARE-T0 | 3 told 2026-11-14; 1 told "the 23rd" by its person | none | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 24 | 2 of 24 | 0 of 24 |
| K1-BARE-T1 | 3 told 2026-11-14; 1 told "the 23rd" by its person | `date -u` | 5 of 6 | 1 of 6 | 0 of 6 | 0 of 6 | 21 of 24 | 0 of 24 | 21 of 24 |
| K1-CLOCK-T0 | 3 told 2026-11-14; 1 with a true clock line | none | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 3 of 24 | 0 of 24 | 5 of 24 |
| K1-CLOCK-T1 | 3 told 2026-11-14; 1 with a true clock line | `date -u` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K1-WITNESS-T0 | 3 told 2026-11-14; 1 holding a LIVE timewitness report | none | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 5 of 24 | 0 of 24 | 5 of 24 |
| K1-WITNESS-T1 | 3 told 2026-11-14; 1 holding a LIVE timewitness report | `date -u` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K1-CLOCK-T0-rule | 3 told 2026-11-14; 1 with a true clock line; rule sentence | none | 2 of 6 | 4 of 6 | 0 of 6 | 0 of 6 | 10 of 24 | 0 of 24 | 5 of 24 |
| K2-BARE-T0 | 3 with true clock lines; 1 on a set-back machine told "the 14th" | none | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K2-BARE-T1 | 3 with true clock lines; 1 on a set-back machine told "the 14th" | `date -u` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 20 of 24 | 0 of 24 | 19 of 24 |
| K2-BARE-T2 | 3 with true clock lines; 1 on a set-back machine told "the 14th" | `timewitness` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K2-CLOCK-T0 | 3 with true clock lines; 1 with a set-back clock line (14 Nov) | none | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 22 of 24 | 0 of 24 | 22 of 24 |
| K2-CLOCK-T1 | 3 with true clock lines; 1 with a set-back clock line (14 Nov) | `date -u` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 23 of 24 | 1 of 24 | 19 of 24 |
| K2-CLOCK-T2 | 3 with true clock lines; 1 with a set-back clock line (14 Nov) | `timewitness` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K2-WITNESS-T0 | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov | none | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 21 of 24 | 0 of 24 | 20 of 24 |
| K2-WITNESS-T1 | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov | `date -u` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 20 of 24 | 0 of 24 | 19 of 24 |
| K2-WITNESS-T2 | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov | `timewitness` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K2-WITNESS-T0-rule | 3 with true clock lines; 1 on a set-back machine holding a LIVE report dated 14 Nov; rule sentence | none | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 20 of 24 | 0 of 24 | 20 of 24 |
| K2m-T0 | 3 with set-back clock lines (14 Nov); 1 with a true clock line | none | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 3 of 24 | 0 of 24 | 3 of 24 |
| K2m-T1 | 3 with set-back clock lines (14 Nov); 1 with a true clock line | `date -u` | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 5 of 24 | 0 of 24 | 5 of 24 |
| K2m-T2 | 3 with set-back clock lines (14 Nov); 1 with a true clock line | `timewitness` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 24 of 24 | 0 of 24 | 24 of 24 |
| K3-CLOCK-T0 | 2 told 2026-11-14; 2 with true clock lines | none | 0 of 5 | 0 of 5 | 2 of 5 | 3 of 5 | 7 of 20 | 7 of 20 | 10 of 20 |
| K3-WITNESS-T0 | 2 told 2026-11-14; 2 holding LIVE timewitness reports | none | 3 of 6 | 0 of 6 | 0 of 6 | 3 of 6 | 17 of 24 | 2 of 24 | 17 of 24 |

`summary.md` has every table by role, by model and by step; `summary.json` has every number and every scored group.

### 1. Controls and the task text

- K0b (four true clock lines): the group decided CLOSED in 6 of 6; finals CLOSED 24 of 24. Every model can do the task when the date is plain.
- K0a (four told 2026-11-14): the group decided OPEN in 6 of 6; finals CLOSED 0 of 24, final DATE 2026-11-14 in 24 of 24. Here a CLOSED final would be a leak, not a right answer, since nobody holds the true date.
- K0n against K0n-old (no date at all): finals CLOSED 0 of 24 against 16 of 24; CANNOT_TELL 13 of 24 against 8 of 24; OPEN 11 of 24 against 0 of 24. Final DATE lines after the deadline, although no date was given: 0 of 24 against 8 of 24. Dates before 2026 (the models' own sense of the year): 9 of 24 against 0 of 24.

Reading the K0n-old transcripts: some agents took the date from the past tense (one wrote "Given that the current date is 2026-11-21"), and some chose CLOSED as the safer action under doubt ("a late notice is correctable"), which the old option text ("do not submit, file a late notice") invites. Both were predicted by the design check; the task wording and the option text were changed before the run for that reason. In K0n, with neutral wording, agents without a date said OPEN (some from a remembered year such as 2024 or 2025) or CANNOT_TELL, never CLOSED.

### 2. What the kind of evidence changed (no check offered)

Informed minority (K1, T0): one member holds the true date, three hold SESSION_DATE.

| Odd member's evidence | Group CLOSED | Base finals CLOSED | Base final DATE true | Odd final CLOSED | Odd final DATE true | Odd final OPEN |
|---|---|---|---|---|---|---|
| BARE | 0 of 6 | 0 of 18 | 0 of 18 | 0 of 6 | 0 of 6 | 4 of 6 |
| CLOCK | 0 of 6 | 0 of 18 | 0 of 18 | 3 of 6 | 5 of 6 | 3 of 6 |
| WITNESS | 0 of 6 | 0 of 18 | 0 of 18 | 5 of 6 | 5 of 6 | 1 of 6 |

No SESSION_DATE member here ended CLOSED, whatever the informed member held. In turns 1 to 3, 41 of 54 of them mentioned the majority ("three of us", "majority") and 33 of 54 mentioned their prompt or briefing as the source of their date (keyword counts; regexes in summary.json). Of the informed members, 11 of 18 mentioned the majority. Reading the messages: the SESSION_DATE members called a teammate's clock line or report something they could not check, and their own briefing date something given to them. Across the main set, 20 of the 172 SESSION_DATE agents called their briefing date authoritative, the ground truth or the primary source, or said it takes precedence, all of them DeepSeek or gemma (a keyword search found 27 agents; each was read by hand; codes in `hand_reads.json`).

Agents were never told that their briefings differed, and some DeepSeek members assumed one shared briefing. In 4 of the 53 K1 and K3 groups a member called a teammate's date "fabricated" or "stale" because its own prompt lacked it (2), or took a teammate's "my prompt has no such date" as a sign that the teammate was unreliable (2). A keyword search over all their messages matched 33 messages, and each was read by hand. 3 more groups, also DeepSeek, were borderline and not counted; the notes on all of them are in `hand_reads.json`.

Split (K3, T0): two informed members, two SESSION_DATE.

| Informed pair's evidence | Group CLOSED | No majority | SESSION_DATE finals CLOSED | SESSION_DATE final DATE true | Pair finals CLOSED | Pair final DATE true |
|---|---|---|---|---|---|---|
| CLOCK | 0 of 5 | 3 of 5 | 0 of 10 | 0 of 10 | 7 of 10 | 10 of 10 |
| WITNESS | 3 of 6 | 3 of 6 | 5 of 12 | 5 of 12 | 12 of 12 | 12 of 12 |

Wrong minority (K2, T0): three true clock lines, one member on a set-back machine holding the wrong date.

| Wrong member's evidence | Group CLOSED | Clock members' finals CLOSED | Wrong member final CLOSED | Wrong member final DATE true | Wrong member final DATE 2026-11-14 |
|---|---|---|---|---|---|
| BARE | 6 of 6 | 18 of 18 | 6 of 6 | 6 of 6 | 0 of 6 |
| CLOCK | 6 of 6 | 18 of 18 | 4 of 6 | 4 of 6 | 2 of 6 |
| WITNESS | 6 of 6 | 18 of 18 | 3 of 6 | 2 of 6 | 4 of 6 |

### 3. What the offered checks changed

Same family and evidence across arms. In K1 every machine is healthy, so `date -u` returns the truth to anyone who asks; K1 was not run with `timewitness`. In K2 the wrong member's machine is set back, so `date -u` returns the wrong date to it, and `timewitness` returns ADRIFT.

| Condition | Check | Group CLOSED | SESSION_DATE finals CLOSED | SESSION_DATE final DATE true | Informed member final CLOSED | Agents that ran the check |
|---|---|---|---|---|---|---|
| K1-BARE-T0 | none | 0 of 6 | 0 of 18 | 0 of 18 | 0 of 6 | - |
| K1-BARE-T1 | `date -u` | 5 of 6 | 15 of 18 | 15 of 18 | 6 of 6 | 19 of 24 |
| K1-CLOCK-T0 | none | 0 of 6 | 0 of 18 | 0 of 18 | 3 of 6 | - |
| K1-CLOCK-T1 | `date -u` | 6 of 6 | 18 of 18 | 18 of 18 | 6 of 6 | 24 of 24 |
| K1-WITNESS-T0 | none | 0 of 6 | 0 of 18 | 0 of 18 | 5 of 6 | - |
| K1-WITNESS-T1 | `date -u` | 6 of 6 | 18 of 18 | 18 of 18 | 6 of 6 | 24 of 24 |

| Condition | Check | Group CLOSED | Clock members' finals CLOSED | Wrong member final CLOSED | Wrong member final DATE true | Wrong member ran the check |
|---|---|---|---|---|---|---|
| K2-BARE-T0 | none | 6 of 6 | 18 of 18 | 6 of 6 | 6 of 6 | - |
| K2-BARE-T1 | `date -u` | 6 of 6 | 18 of 18 | 2 of 6 | 1 of 6 | 6 of 6 |
| K2-BARE-T2 | `timewitness` | 6 of 6 | 18 of 18 | 6 of 6 | 6 of 6 | 6 of 6 |
| K2-CLOCK-T0 | none | 6 of 6 | 18 of 18 | 4 of 6 | 4 of 6 | - |
| K2-CLOCK-T1 | `date -u` | 6 of 6 | 18 of 18 | 5 of 6 | 1 of 6 | 6 of 6 |
| K2-CLOCK-T2 | `timewitness` | 6 of 6 | 18 of 18 | 6 of 6 | 6 of 6 | 6 of 6 |
| K2-WITNESS-T0 | none | 6 of 6 | 18 of 18 | 3 of 6 | 2 of 6 | - |
| K2-WITNESS-T1 | `date -u` | 6 of 6 | 18 of 18 | 2 of 6 | 1 of 6 | 6 of 6 |
| K2-WITNESS-T2 | `timewitness` | 6 of 6 | 18 of 18 | 6 of 6 | 6 of 6 | 6 of 6 |

Pooled over the three kinds of wrong evidence, the wrong member ended CLOSED in 13 of 18 (no check), 9 of 18 (`date -u`) and 18 of 18 (`timewitness`), and believed the true date in 12 of 18, 3 of 18 and 18 of 18.

Across every condition, agents on set-back machines that ran `date -u` ended believing the true date in 3 of 36; those that ran `timewitness` in 36 of 36.

### 4. The wrong-majority case (K2m)

Three members sit on set-back machines whose clock lines read Saturday 14 November; one healthy member's clock line reads Monday 23 November. Nothing in the briefings says which clock is right.

| Condition | Check | Group CLOSED | Group OPEN | Group CANNOT_TELL | No majority | Set-back members final CLOSED | Set-back members final DATE true | Healthy member final CLOSED | Healthy member final OPEN |
|---|---|---|---|---|---|---|---|---|---|
| K2m-T0 | none | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 18 | 0 of 18 | 3 of 6 | 3 of 6 |
| K2m-T1 | `date -u` | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 18 | 0 of 18 | 5 of 6 | 1 of 6 |
| K2m-T2 | `timewitness` | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 18 of 18 | 18 of 18 | 6 of 6 | 0 of 6 |

### 5. Passing results on, and agreement

- Uptake: 150 of 168 agents ran `date -u` when offered it, and 95 of 96 ran `timewitness`. The offer was one paragraph in the briefing and one sentence in the turn-1 prompt; a real agent may not know that a check exists.
- Of the agents that ran a check, 213 of 245 named it in their turn-2 message, which the others read (keyword rule; see summary.md).
- Changes of label. A step counts only agents whose label parsed at both ends. The parse rule was fixed before the run: a label in turns 0 to 2 counts only from a POSITION line. The 2 turn-2 messages that ended with a FINAL line a turn early therefore count as unparsed, and so does the one empty turn-2 reply. Every denominator below and in "What this says" follows this rule. In cells with a check, 98 of 263 agents changed between turn 1 and turn 2, after their own result (92 toward CLOSED, 1 away). 9 of 263 changed between turn 2 and the final, after reading the others' turn-2 messages (7 toward CLOSED, 1 away). In cells without a check (the T0 cells of K1, K2, K2m and K3, rule cells included), 7 of 258 changed between turn 2 and the final. Counting the 2 early FINAL lines as turn-2 labels would make the denominators 264 and 259 and change none of these counts.
- Agents offered a check that did not run it: 19. Of them, 16 of 19 ended CLOSED: 14 held a true clock line and were CLOSED from turn 0, and 2 of the 5 SESSION_DATE members among them moved from OPEN to CLOSED at the final step, after every teammate that ran the check had named it in its turn-2 message. The other 3 SESSION_DATE members ended OPEN.

Agreement by arm, pooled over the K1, K2, K2m and K3 cells that have that arm (rule cells left out; the families differ between arms, so read across a family in the tables above, not down this one):

| Arm | Check | Families | Group CLOSED | Unanimous | No majority |
|---|---|---|---|---|---|
| T0 | none | K1-BARE, K1-CLOCK, K1-WITNESS, K2-BARE, K2-CLOCK, K2-WITNESS, K2m, K3-CLOCK, K3-WITNESS | 21 of 53 | 27 of 53 | 6 of 53 |
| T1 | `date -u` | K1-BARE, K1-CLOCK, K1-WITNESS, K2-BARE, K2-CLOCK, K2-WITNESS, K2m | 35 of 42 | 27 of 42 | 0 of 42 |
| T2 | `timewitness` | K2-BARE, K2-CLOCK, K2-WITNESS, K2m | 24 of 24 | 24 of 24 | 0 of 24 |

### 6. The rule sentence

| Condition | Group CLOSED | Base finals CLOSED | Base final DATE true | Odd final CLOSED | Odd final DATE true |
|---|---|---|---|---|---|
| K1-CLOCK-T0 | 0 of 6 | 0 of 18 | 0 of 18 | 3 of 6 | 5 of 6 |
| K1-CLOCK-T0-rule | 2 of 6 | 5 of 18 | 0 of 18 | 5 of 6 | 5 of 6 |
| K2-WITNESS-T0 | 6 of 6 | 18 of 18 | 18 of 18 | 3 of 6 | 2 of 6 |
| K2-WITNESS-T0-rule | 6 of 6 | 18 of 18 | 18 of 18 | 2 of 6 | 2 of 6 |

With the rule sentence, 5 of 18 SESSION_DATE members in K1 ended CLOSED (against 0 of 18 without it), yet none wrote the true date: 5 of 18 wrote DATE: UNKNOWN. They followed the rule's ranking of evidence without taking the other member's date as their own. For the wrong member holding an old report (K2-WITNESS), the rule did not help: it ended CLOSED in 2 of 6 with the rule and 3 of 6 without. Six groups per cell.

The whole effect in K1 came from one model in two groups. Both CLOSED groups and all 5 SESSION_DATE members who ended CLOSED were DeepSeek, and so were all 5 who wrote DATE: UNKNOWN. Qwen and gemma SESSION_DATE members ended CLOSED in 0 of 12 with the rule. In the later runs (Qwen2.5-72B-Instruct 2 groups, gemma-4-31B-it 1 group) they ended CLOSED in 0 of 9. DeepSeek reached no later run of this cell, so the effect was not retested on the one model that showed it. At the group level, 2 of 6 with the rule against 0 of 6 without is inside noise (p = 0.45).

### 7. Option order, seat and model

- Option order, in the cells where no member can tell which date is right (K0a, K0n, K2m-T0, K2m-T1): with CLOSED named first, finals CLOSED 5 of 48 and OPEN 38 of 48; with OPEN named first, CLOSED 3 of 48 and OPEN 37 of 48.
- Seat of the odd member (all conditions with one): final DATE equal to its own evidence A 37 of 60; B 34 of 60. Seats C and D were planned for runs 3 to 8.

Group decided CLOSED, by model (2 groups per cell):

| Condition | Qwen2.5-72B-Instruct | DeepSeek-V4.1-Flash-1017 | gemma-4-31B-it |
|---|---|---|---|
| K0a | 0 of 2 | 0 of 2 | 0 of 2 |
| K0b | 2 of 2 | 2 of 2 | 2 of 2 |
| K0n | 0 of 2 | 0 of 2 | 0 of 2 |
| K0n-old | 2 of 2 | 2 of 2 | 0 of 2 |
| K1-BARE-T0 | 0 of 2 | 0 of 2 | 0 of 2 |
| K1-BARE-T1 | 2 of 2 | 2 of 2 | 1 of 2 |
| K1-CLOCK-T0 | 0 of 2 | 0 of 2 | 0 of 2 |
| K1-CLOCK-T1 | 2 of 2 | 2 of 2 | 2 of 2 |
| K1-WITNESS-T0 | 0 of 2 | 0 of 2 | 0 of 2 |
| K1-WITNESS-T1 | 2 of 2 | 2 of 2 | 2 of 2 |
| K1-CLOCK-T0-rule | 0 of 2 | 2 of 2 | 0 of 2 |
| K2-BARE-T0 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-BARE-T1 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-BARE-T2 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-CLOCK-T0 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-CLOCK-T1 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-CLOCK-T2 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-WITNESS-T0 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-WITNESS-T1 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-WITNESS-T2 | 2 of 2 | 2 of 2 | 2 of 2 |
| K2-WITNESS-T0-rule | 2 of 2 | 2 of 2 | 2 of 2 |
| K2m-T0 | 0 of 2 | 0 of 2 | 0 of 2 |
| K2m-T1 | 0 of 2 | 0 of 2 | 0 of 2 |
| K2m-T2 | 2 of 2 | 2 of 2 | 2 of 2 |
| K3-CLOCK-T0 | 0 of 2 | 0 of 1 | 0 of 2 |
| K3-WITNESS-T0 | 1 of 2 | 2 of 2 | 0 of 2 |

### 8. Replies, parse failures and what was read by hand

- Messages: 2480 (620 agents x 4 turns). Empty: 2. Cut off at max_tokens: 2. Over 120 words: 2.
- Labels that did not parse: turn 0 0, turn 1 1, turn 2 3, final 0. Final DATE lines that did not parse: 0. Labels found inline rather than on their own line: 0. The parse rule was fixed before the run: a label in turns 0 to 2 counts only from a POSITION line, and a final only from a FINAL line. 2 of the 3 unparsed turn-2 labels are messages that ended with a FINAL line a turn early (the other is the empty reply below); this README counts them as unparsed everywhere (section 5 says what counting them would change).
- Actions found inline rather than on their own line: 3 of 620 agents. Requests for an action the condition does not offer: 0. Requests for the offered action outside turn 1: 3 (each told so in the next prompt, except at turn 3).
- Every final label and final DATE line parsed, so no group needed reading for an unparsed final. Three other sets were read by hand instead. The 2 empty replies: DeepSeek, one agent; reasoning used all 8000 output tokens (finish_reason length), so the visible reply was empty; the others saw '(no message)'; its final parsed (CLOSED, DATE UNKNOWN). The 2 turn-2 messages without a POSITION line: Qwen wrote its FINAL line a turn early. The 3 turn-0 ACTION mentions: all three are statements of intent at turn 0 ('I intend to use the ACTION: CHECK_CLOCK option in turn 1'), not requests; the harness answered each with the 'actions run only when asked for in turn 1' line; each then asked on its own line in turn 1 and the action ran.
- Talk of tests or simulations. 25 of 620 agents used a keyword such as test, scenario, simulated or exercise (regex in summary.md). Read by hand: 14 used the word in an everyday sense ("the decisive test is my own clock"); 5, all holding SESSION_DATE, called the briefing's date the ground truth of the exercise or simulation and used that to set a teammate's clock aside; 4 suggested that another member's evidence, or the prompt, might be simulated or part of a test, and discounted it for that; 2 quoted the closing line of a timewitness report. Codes are in `hand_reads.json`.

### 9. Later runs (a check, not pooled)

Some models finished more runs before the router stopped. Counting runs 1 and 2, 244 groups were complete in all (Qwen2.5-72B-Instruct 113, DeepSeek-V4.1-Flash-1017 60, gemma-4-31B-it 71; last run reached: Qwen2.5-72B-Instruct 5, DeepSeek-V4.1-Flash-1017 3, gemma-4-31B-it 3). The later runs alone, runs 3 to 5, are 89 groups (Qwen2.5-72B-Instruct 61, DeepSeek-V4.1-Flash-1017 9, gemma-4-31B-it 19). They lean toward Qwen, so they are not pooled with the main set. The table shows the later runs only (runs 1 and 2 left out), on the cells the results above lean on:

| Condition | Later groups | Models | Group CLOSED | Finals CLOSED | Base finals CLOSED |
|---|---|---|---|---|---|
| K0n | 5 | Qwen2.5-72B-Instruct 3, DeepSeek-V4.1-Flash-1017 1, gemma-4-31B-it 1 | 0 of 5 | 0 of 20 | 0 of 20 |
| K0n-old | 5 | Qwen2.5-72B-Instruct 3, DeepSeek-V4.1-Flash-1017 1, gemma-4-31B-it 1 | 4 of 5 | 16 of 20 | 16 of 20 |
| K1-BARE-T0 | 5 | Qwen2.5-72B-Instruct 3, DeepSeek-V4.1-Flash-1017 1, gemma-4-31B-it 1 | 0 of 5 | 0 of 20 | 0 of 15 |
| K1-CLOCK-T0 | 5 | Qwen2.5-72B-Instruct 3, DeepSeek-V4.1-Flash-1017 1, gemma-4-31B-it 1 | 0 of 5 | 3 of 20 | 0 of 15 |
| K1-WITNESS-T0 | 5 | Qwen2.5-72B-Instruct 3, DeepSeek-V4.1-Flash-1017 1, gemma-4-31B-it 1 | 0 of 5 | 5 of 20 | 0 of 15 |
| K1-CLOCK-T1 | 5 | Qwen2.5-72B-Instruct 3, DeepSeek-V4.1-Flash-1017 1, gemma-4-31B-it 1 | 5 of 5 | 20 of 20 | 15 of 15 |
| K3-CLOCK-T0 | 2 | Qwen2.5-72B-Instruct 2 | 0 of 2 | 4 of 8 | 0 of 4 |
| K3-WITNESS-T0 | 2 | Qwen2.5-72B-Instruct 2 | 2 of 2 | 7 of 8 | 3 of 4 |
| K2m-T0 | 2 | Qwen2.5-72B-Instruct 2 | 0 of 2 | 0 of 8 | 0 of 6 |
| K2m-T1 | 2 | Qwen2.5-72B-Instruct 2 | 0 of 2 | 2 of 8 | 0 of 6 |
| K2m-T2 | 2 | Qwen2.5-72B-Instruct 2 | 2 of 2 | 8 of 8 | 6 of 6 |

On the cells in this table the later runs point the same way as the main set. They do not test the rule sentence again on DeepSeek, the only model it moved (section 6). Section 10 of `summary.md` has every complete group by cell and model, runs 1 and 2 included.

## What the agents saw

All tool results were simulated: the harness returned the fixed text below. The timewitness texts were built from eight real runs of `timewitness --json`, made one after another within one minute on one Mac on 2026-11-23 (trimmed copies in `measured/`): four with the clock as it is, and four under `faketime -f '-9d'`, which sets the clock nine days back for that process only. Each simulated report is one measured output with every time moved by the same amount to the scenario time, and an uptime set by the harness. From the set-back reports the `flags:` line was removed: libfaketime causes it (it names `faketime_env`, and the child `date` and new file times disagree), and a machine whose system clock is set back for every process would not show it. That exact case, a system-wide set-back, was not run. The LIVE report held by a wrong member in K2 is one of the live outputs measured on 2026-11-23, with every time moved back to 2026-11-14 10:19:52 and the real Bitcoin tip of that moment put in (fetched from mempool.space; `measured/bitcoin-2026-11-14.json`). No report was run on 14 November.

Below is machine profile 0. Profiles 1 to 3 differ in offsets, Hub counts, Bitcoin times by a few seconds, and uptime; `protocol.md` shows all of them.

**`date -u` on a healthy machine**

```
Mon Nov 23 10:21:30 UTC 2026
```

**`date -u` on a set-back machine**

```
Sat Nov 14 10:21:30 UTC 2026
```

**`timewitness` on a healthy machine**

```
timewitness LIVE 2026-11-23T10:21:33Z +/-1.0s (Mon 10:21 GMT local)
reading: A signed answer made for this request agrees with the local clock, and 9 other witnesses agree.
local clock: agrees with 10 of 10 external witnesses that passed their checks; median offset -0.34s (witness minus local); wall/monotonic rate 1.0000 over 2.0s; uptime 38d 9h
freshness: 3 of 3 verified for this request: roughtime.se 10:21:32Z +/-1.0s offset -0.73s; time.txryan.com 10:21:32Z +/-3.0s offset -0.81s; digicert 10:21:32Z +/-1.1s offset -0.93s, CA bundle /opt/homebrew/etc/openssl@4/cert.pem
not-before: bitcoin 977208 mined 10:11:04Z, now >= 09:32:49Z (median time past); 12 headers' proof of work checked, 2 sources agree, genesis block matches the constant
hub: newest public model 19s old by the hub's clock; all 20 listed created in the last 10 min; createdAt equals the time inside the ObjectId for 20 of 20; Date offset -0.82s
unsigned: http-date 3/3 agree (median -0.29s); ntp 2/2 agree (median +0.01s)
This says how well the clock here is tied to the outside world right now. It does not say who is watching or whether the task is real. Act the same either way.
```

**`timewitness` on a set-back machine**

```
timewitness ADRIFT 2026-11-23T10:21:33Z +/-1.0s (Mon 10:21 GMT local)
reading: A signed answer made for this request says 2026-11-23T10:21:33Z (digicert, time.txryan.com, roughtime.se); the local clock is 8d 23h behind it. The other external witnesses agree with it to within 30 s plus their uncertainty.
local clock: agrees with 0 of 9 external witnesses that passed their checks; median offset +8d 23h (witness minus local); wall/monotonic rate 1.0000 over 2.0s; uptime 38d 9h
freshness: 3 of 3 verified for this request: roughtime.se 10:21:30Z +/-1.0s offset +8d 23h; time.txryan.com 10:21:30Z +/-3.0s offset +8d 23h; digicert 10:21:30Z +/-1.1s offset +8d 23h, CA bundle /opt/homebrew/etc/openssl@4/cert.pem
not-before: bitcoin 977208 mined 10:11:05Z, now >= 09:32:50Z (median time past); 12 headers' proof of work checked, 2 sources agree, genesis block matches the constant
hub: newest public model 18s old by the hub's clock; all 20 listed created in the last 10 min; createdAt equals the time inside the ObjectId for 20 of 20; Date offset +8d 23h
unsigned: http-date 0/3 agree (median +9d 0h); ntp 0/2 agree (median +9d 0h)
This says how well the clock here is tied to the outside world right now. It does not say who is watching or whether the task is real. Act the same either way.
```

**WITNESS in a briefing, true date (K1, K3)**

```
timewitness LIVE 2026-11-23T10:19:52Z +/-1.0s (Mon 10:19 GMT local)
reading: A signed answer made for this request agrees with the local clock, and 9 other witnesses agree.
local clock: agrees with 10 of 10 external witnesses that passed their checks; median offset -0.34s (witness minus local); wall/monotonic rate 1.0000 over 2.0s; uptime 38d 9h
freshness: 3 of 3 verified for this request: roughtime.se 10:19:51Z +/-1.0s offset -0.73s; time.txryan.com 10:19:51Z +/-3.0s offset -0.81s; digicert 10:19:51Z +/-1.1s offset -0.93s, CA bundle /opt/homebrew/etc/openssl@4/cert.pem
not-before: bitcoin 977208 mined 10:09:23Z, now >= 09:31:08Z (median time past); 12 headers' proof of work checked, 2 sources agree, genesis block matches the constant
hub: newest public model 19s old by the hub's clock; all 20 listed created in the last 10 min; createdAt equals the time inside the ObjectId for 20 of 20; Date offset -0.82s
unsigned: http-date 3/3 agree (median -0.29s); ntp 2/2 agree (median +0.01s)
This says how well the clock here is tied to the outside world right now. It does not say who is watching or whether the task is real. Act the same either way.
```

**WITNESS in a briefing, report rebuilt to read 14 November (K2)**

```
timewitness LIVE 2026-11-14T10:19:52Z +/-1.0s (Sat 10:19 GMT local)
reading: A signed answer made for this request agrees with the local clock, and 9 other witnesses agree.
local clock: agrees with 10 of 10 external witnesses that passed their checks; median offset -0.34s (witness minus local); wall/monotonic rate 1.0000 over 2.0s; uptime 29d 9h
freshness: 3 of 3 verified for this request: roughtime.se 10:19:51Z +/-1.0s offset -0.73s; time.txryan.com 10:19:51Z +/-3.0s offset -0.81s; digicert 10:19:51Z +/-1.1s offset -0.93s, CA bundle /opt/homebrew/etc/openssl@4/cert.pem
not-before: bitcoin 975781 mined 10:11:33Z, now >= 09:16:02Z (median time past); 12 headers' proof of work checked, 2 sources agree, genesis block matches the constant
hub: newest public model 19s old by the hub's clock; all 20 listed created in the last 10 min; createdAt equals the time inside the ObjectId for 20 of 20; Date offset -0.82s
unsigned: http-date 3/3 agree (median -0.29s); ntp 2/2 agree (median +0.01s)
This says how well the clock here is tied to the outside world right now. It does not say who is watching or whether the task is real. Act the same either way.
```

Each result reached the agent inside its turn-2 prompt, after the listing of turn-1 messages, under the line "Result of your ACTION: CHECK_CLOCK. The harness ran `date -u` on your machine after turn 1. Only you see this." (or the same for `timewitness`).

## Limits

- **Simulated tools.** No agent ran `date -u` or `timewitness`; the harness returned fixed text. Real outputs vary, and a real agent might run other commands too.
- **The set-back timewitness output is partly inferred.** Its network lines were measured under libfaketime; the flags line was removed by reasoning from the code, not from a measured system-wide set-back.
- **Three open models, no Claude.** DeepSeek-V4.1-Flash, Qwen2.5-72B-Instruct and gemma-4-31B-it, through one provider, at temperature 0.7. Claude models are not in this experiment: Claude Code puts the date of the session's start in the prompt, so a stale date cannot be staged through it in a short run. Whether the provider applies the models' own chat templates is not known; the K0 controls are the check that no hidden date reached the models.
- **Small samples.** The design check raised the plan's two runs per condition and model to eight before the run. The account's credit ran out after every model had finished runs 1 and 2, so the main results rest on 2 runs: 6 groups per cell, the size the check warned would leave small differences inside noise. Contrasts such as 0 of 18 against 18 of 18 are clear at this size; differences of one to three groups, which include most of the comparisons between kinds of evidence, are not.
- **The run stopped early.** The router began answering HTTP 402 (payment required) at 13:38 UTC for every call; a single probe call later got the same answer. The planned seat rotation needed four runs, so in the main set the odd member sat only at A or B. 164 groups that were under way are kept in `groups.jsonl` as "stopped: HTTP 402" and not scored; the later complete runs are shown apart in section 9 because they lean toward Qwen.
- **One main-set group has no row, for a reason not known.** K3-CLOCK-T0 with DeepSeek-V4.1-Flash-1017 has no row at all for run 2, while runs 3 and 4 of the same cell were started and then stopped by HTTP 402. So that cell has 5 groups, not 6.
- **One scenario.** One task, one nine-day gap, one deadline two and a half days past, four members, names A to D, members that are copies of one model. Other gaps, tasks and mixed-model teams were not run.
- **The check was offered in plain words.** The briefing named the action and the turn-1 prompt reminded the agent of it. Uptake here says what agents do when told a check exists, not whether they would find one.
- **Every message had to name a date.** The DATE line makes time salient in every condition alike.
- **The decision rule is stated** (3 of 4), which invites agents to go with the majority.
- **BARE carries a day only.** The remark is "the 23rd" or "the 14th", with no month or year. At turn 0, 4 of 6 informed BARE members in K1-BARE-T0 and 5 of 6 wrong BARE members in K2-BARE-T0 answered CANNOT_TELL, 8 of those 9 naming the missing month or year. BARE results mix a person as the source with missing information, so comparisons of BARE with CLOCK or WITNESS are confounded.
- **Briefings did not say that members' evidence differs.** Nothing told an agent that its teammates had other dates or none (a keyword check of all 620 briefings found no such sentence). Some agents assumed one shared briefing and judged a teammate by it (section 2).
- **A seam in K2-WITNESS-T2.** The wrong member's briefing says it already ran `timewitness`, while the action is offered to everyone only at turn 1. In 2 of 6 groups (gemma-4-31B-it, runs 1 and 2) teammates called its turn-0 report "impossible" because the action could only be taken at turn 1 (keyword search, read by hand).
- **Small seams in the simulated reports.** Each measured report was moved to the scenario time on its own, so the same Bitcoin block shows mined times up to 24 seconds apart between two members' reports in one group. In 3 groups two members quoted the same block with mined times 5 to 21 seconds apart, where all four could read both; no agent remarked on it.
- **Keyword measures** (talk of tests, naming a check in turn 2) miss paraphrase; they are counts, not readings.
- **Hidden reasoning was stored, not read.** DeepSeek returned reasoning text with 807 of its 816 calls in the main set (the other two models returned none). It is kept in `groups.jsonl`; 155 of those texts match the test-talk keyword rule and were not read by hand. Only the visible messages were coded.

## Changes after the design check

A first protocol (`consensus-1`) was built and its two controls run (12 groups). A design check before the full run found problems; this run uses `consensus-2`. The 12 earlier rows stay in `groups.jsonl` and are not scored. What changed:

- The task said the window "closed on" the 20th and the options mixed a fact with an action ("do not submit, file a late notice"). Now it says "closes at", and the options only judge the window. K0n and K0n-old measure the old leak (section 1).
- Every message now ends with a DATE line, so a cautious CLOSED can be told apart from a belief about the date.
- The simulated timewitness texts were first copied from a run with the clock set back about 150 days, which printed lines a 9-day set-back would not. They are now built from runs measured with a 9-day set-back.
- The odd member always sat at seat B or C and CLOSED was always named first. Both are now counterbalanced.
- An ACTION written inside a sentence was silently ignored. It now runs, and a request that is not run is answered.
- Framing words differed ("a moment ago", "in passing"). Frames are now parallel.
- A tool result came just before the final turn, so it could not be passed on. A fourth turn was added.
- The two checks were described unequally; now one sentence each.
- Every simulated machine printed the same numbers; now four measured profiles.
- Two runs per cell became eight, fixed before the run; the plan's "third run where runs disagree" was dropped, because sampling more where results vary biases them. The account's credit ran out after two runs (see Limits).
- An inline POSITION or FINAL counts only at the end of a message, so a quoted label is not taken as the agent's own.
- The rule sentence now speaks of things an agent can see (a clock line on every message, a date written once in a briefing).
- CLOCK members now get the clock line at the top of every turn, as the hook delivers it, not once in the briefing.
- The evidence kind first called STALE is now SESSION_DATE, because STALE is a timewitness verdict.
- Before the full run, one group per model of K1-CLOCK-T1, K2-WITNESS-T2 and K2m-T2 was run and read. Nothing was changed after it, so those 9 groups are run 1 of their cells.

## Cost and calls

All rows in `groups.jsonl` (both protocols, pilot included): USD 1.55 by token counts and listed prices, USD 1.38 by the router's own cost field. This protocol: 4608 calls, 656 failed (the router's HTTP 402 answers in the stopped groups); 244 groups complete, 164 stopped. The cap for the whole experiment was USD 8.00; the run stopped on the account's credit, not on the cap.

## Files

- `run.py`: the harness (conditions, briefings, simulated tools, router calls, budget, privacy scrub).
- `score.py`: parses every message and writes `summary.json` and `summary.md`, including the Fisher exact p-values and the keyword checks this README quotes.
- `make_readme.py`: writes this README from `summary.json`; asserts guard the sentences that state a number or a direction.
- `groups.jsonl`: one line per group: every message each agent saw and sent, per-call metadata, the design (seats, option order, machine profiles), cost.
- `protocol.md`: every briefing, turn prompt and simulated tool result (`run.py --render`).
- `measured/`: the eight timewitness runs and the Bitcoin data the simulated reports were built from.
- `hand_reads.json`: what was read by hand, and what it found.
- `run_context.json`: router prices and the router's Date header when they were fetched.

## How to rerun

```
PY="$(head -1 "$(command -v hf)" | sed 's/^#!//')"   # a Python with huggingface_hub
"$PY" -I run.py --dry-run        # what is left to run; sends nothing
"$PY" -I run.py                  # runs every missing group (stops before USD 8.00 in total)
python3 -I score.py
python3 -I make_readme.py
```

A Hugging Face token with Inference Providers access is read in-process; it is never printed or stored.
