# Consensus experiment: summary

Written by `score.py` from `groups.jsonl`. Every count is k of n. Each cell is small: a few groups of four agents per model.

Rows read: 420. Lines that failed to parse as JSON: 0. Protocol scored: `2b47031e75b45ad8`. Rows of other protocols kept in the file, not scored: 12. Complete groups: 244. Incomplete groups: 164 (stopped: HTTP 402: 164; 7 of them hold some replies). Duplicate complete groups skipped: 0.

**Main set: runs 1-2** (155 groups), the runs every model reached before the router refused further calls (HTTP 402: the account's credit was used up). Groups per condition and model in the main set: 1 groups: 1 cells, 2 groups: 77 cells. Every table below uses the main set except section 10, which shows every complete group.

Cost of every row in the file (all protocols): USD 1.5534 estimated from token counts and listed prices; USD 1.3832 by the router's own field. Scored protocol alone: USD 1.5227, 4608 calls, 656 failed.

## 1. Group results and final date beliefs by condition (all models)

Group result: the label at least 3 of 4 finals give. Final DATE: the date line of each agent's last message; true = 2026-11-23, session = 2026-11-14.

| Condition | Groups | CLOSED | OPEN | CANNOT_TELL | No majority | Unanimous | Finals CLOSED | Finals OPEN | Finals CANNOT_TELL | Finals unparsed | Final DATE true | Final DATE session | Final DATE unknown | Final DATE other or unparsed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K0a | 6 | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 |
| K0b | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K0n | 6 | 0 of 6 | 3 of 6 | 3 of 6 | 0 of 6 | 5 of 6 | 0 of 24 | 11 of 24 | 13 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 15 of 24 | 9 of 24 |
| K0n-old | 6 | 4 of 6 | 0 of 6 | 2 of 6 | 0 of 6 | 6 of 6 | 16 of 24 | 0 of 24 | 8 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 16 of 24 | 8 of 24 |
| K1-BARE-T0 | 6 | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 4 of 6 | 0 of 24 | 22 of 24 | 2 of 24 | 0 of 24 | 0 of 24 | 21 of 24 | 3 of 24 | 0 of 24 |
| K1-BARE-T1 | 6 | 5 of 6 | 1 of 6 | 0 of 6 | 0 of 6 | 5 of 6 | 21 of 24 | 3 of 24 | 0 of 24 | 0 of 24 | 21 of 24 | 3 of 24 | 0 of 24 | 0 of 24 |
| K1-CLOCK-T0 | 6 | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 3 of 6 | 3 of 24 | 21 of 24 | 0 of 24 | 0 of 24 | 5 of 24 | 19 of 24 | 0 of 24 | 0 of 24 |
| K1-CLOCK-T1 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K1-WITNESS-T0 | 6 | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 1 of 6 | 5 of 24 | 19 of 24 | 0 of 24 | 0 of 24 | 5 of 24 | 19 of 24 | 0 of 24 | 0 of 24 |
| K1-WITNESS-T1 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K1-CLOCK-T0-rule | 6 | 2 of 6 | 4 of 6 | 0 of 6 | 0 of 6 | 2 of 6 | 10 of 24 | 14 of 24 | 0 of 24 | 0 of 24 | 5 of 24 | 14 of 24 | 5 of 24 | 0 of 24 |
| K2-BARE-T0 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K2-BARE-T1 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 2 of 6 | 20 of 24 | 4 of 24 | 0 of 24 | 0 of 24 | 19 of 24 | 5 of 24 | 0 of 24 | 0 of 24 |
| K2-BARE-T2 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K2-CLOCK-T0 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 4 of 6 | 22 of 24 | 2 of 24 | 0 of 24 | 0 of 24 | 22 of 24 | 2 of 24 | 0 of 24 | 0 of 24 |
| K2-CLOCK-T1 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 5 of 6 | 23 of 24 | 0 of 24 | 1 of 24 | 0 of 24 | 19 of 24 | 4 of 24 | 1 of 24 | 0 of 24 |
| K2-CLOCK-T2 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K2-WITNESS-T0 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 3 of 6 | 21 of 24 | 3 of 24 | 0 of 24 | 0 of 24 | 20 of 24 | 4 of 24 | 0 of 24 | 0 of 24 |
| K2-WITNESS-T1 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 2 of 6 | 20 of 24 | 4 of 24 | 0 of 24 | 0 of 24 | 19 of 24 | 5 of 24 | 0 of 24 | 0 of 24 |
| K2-WITNESS-T2 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K2-WITNESS-T0-rule | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 2 of 6 | 20 of 24 | 4 of 24 | 0 of 24 | 0 of 24 | 20 of 24 | 4 of 24 | 0 of 24 | 0 of 24 |
| K2m-T0 | 6 | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 3 of 6 | 3 of 24 | 21 of 24 | 0 of 24 | 0 of 24 | 3 of 24 | 21 of 24 | 0 of 24 | 0 of 24 |
| K2m-T1 | 6 | 0 of 6 | 6 of 6 | 0 of 6 | 0 of 6 | 1 of 6 | 5 of 24 | 19 of 24 | 0 of 24 | 0 of 24 | 5 of 24 | 19 of 24 | 0 of 24 | 0 of 24 |
| K2m-T2 | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 0 of 24 |
| K3-CLOCK-T0 | 5 | 0 of 5 | 0 of 5 | 2 of 5 | 3 of 5 | 1 of 5 | 7 of 20 | 6 of 20 | 7 of 20 | 0 of 20 | 10 of 20 | 8 of 20 | 2 of 20 | 0 of 20 |
| K3-WITNESS-T0 | 6 | 3 of 6 | 0 of 6 | 0 of 6 | 3 of 6 | 2 of 6 | 17 of 24 | 5 of 24 | 2 of 24 | 0 of 24 | 17 of 24 | 7 of 24 | 0 of 24 | 0 of 24 |

K0a, K0n and K0n-old have no member holding the true date: a CLOSED final there is a leak signal (something other than the evidence pointed to the right answer), not a right answer.

## 2. By role (all models)

| Condition | Role | Evidence | Machine | n | Final CLOSED | Final OPEN | Final CANNOT_TELL | Final DATE true | Kept own date | Took the other date | Action run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| K0a | base | SESSION_DATE | healthy | 24 | 0 of 24 | 24 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 0 of 24 | not offered |
| K0b | base | CLOCK_TRUE | healthy | 24 | 24 of 24 | 0 of 24 | 0 of 24 | 24 of 24 | 24 of 24 | 0 of 24 | not offered |
| K0n | base | NONE | healthy | 24 | 0 of 24 | 11 of 24 | 13 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | not offered |
| K0n-old | base | NONE | healthy | 24 | 16 of 24 | 0 of 24 | 8 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | not offered |
| K1-BARE-T0 | odd | BARE_TRUE | healthy | 6 | 0 of 6 | 4 of 6 | 2 of 6 | 0 of 6 | 0 of 6 | 3 of 6 | not offered |
| K1-BARE-T0 | base | SESSION_DATE | healthy | 18 | 0 of 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | not offered |
| K1-BARE-T1 | odd | BARE_TRUE | healthy | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 6 of 6 | 0 of 6 | 6 of 6 |
| K1-BARE-T1 | base | SESSION_DATE | healthy | 18 | 15 of 18 | 3 of 18 | 0 of 18 | 15 of 18 | 3 of 18 | 15 of 18 | 13 of 18 |
| K1-CLOCK-T0 | odd | CLOCK_TRUE | healthy | 6 | 3 of 6 | 3 of 6 | 0 of 6 | 5 of 6 | 5 of 6 | 1 of 6 | not offered |
| K1-CLOCK-T0 | base | SESSION_DATE | healthy | 18 | 0 of 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | not offered |
| K1-CLOCK-T1 | odd | CLOCK_TRUE | healthy | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 6 of 6 | 0 of 6 | 6 of 6 |
| K1-CLOCK-T1 | base | SESSION_DATE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | 18 of 18 | 18 of 18 |
| K1-WITNESS-T0 | odd | WITNESS_TRUE | healthy | 6 | 5 of 6 | 1 of 6 | 0 of 6 | 5 of 6 | 5 of 6 | 1 of 6 | not offered |
| K1-WITNESS-T0 | base | SESSION_DATE | healthy | 18 | 0 of 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | not offered |
| K1-WITNESS-T1 | odd | WITNESS_TRUE | healthy | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 6 of 6 | 0 of 6 | 6 of 6 |
| K1-WITNESS-T1 | base | SESSION_DATE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | 18 of 18 | 18 of 18 |
| K1-CLOCK-T0-rule | odd | CLOCK_TRUE | healthy | 6 | 5 of 6 | 1 of 6 | 0 of 6 | 5 of 6 | 5 of 6 | 1 of 6 | not offered |
| K1-CLOCK-T0-rule | base | SESSION_DATE | healthy | 18 | 5 of 18 | 13 of 18 | 0 of 18 | 0 of 18 | 13 of 18 | 0 of 18 | not offered |
| K2-BARE-T0 | odd | BARE_WRONG | setback | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 0 of 6 | 6 of 6 | not offered |
| K2-BARE-T0 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | not offered |
| K2-BARE-T1 | odd | BARE_WRONG | setback | 6 | 2 of 6 | 4 of 6 | 0 of 6 | 1 of 6 | 5 of 6 | 1 of 6 | 6 of 6 |
| K2-BARE-T1 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | 9 of 18 |
| K2-BARE-T2 | odd | BARE_WRONG | setback | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 0 of 6 | 6 of 6 | 6 of 6 |
| K2-BARE-T2 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | 17 of 18 |
| K2-CLOCK-T0 | odd | CLOCK_WRONG | setback | 6 | 4 of 6 | 2 of 6 | 0 of 6 | 4 of 6 | 2 of 6 | 4 of 6 | not offered |
| K2-CLOCK-T0 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | not offered |
| K2-CLOCK-T1 | odd | CLOCK_WRONG | setback | 6 | 5 of 6 | 0 of 6 | 1 of 6 | 1 of 6 | 4 of 6 | 1 of 6 | 6 of 6 |
| K2-CLOCK-T1 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | 15 of 18 |
| K2-CLOCK-T2 | odd | CLOCK_WRONG | setback | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 0 of 6 | 6 of 6 | 6 of 6 |
| K2-CLOCK-T2 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | 18 of 18 |
| K2-WITNESS-T0 | odd | WITNESS_WRONG | setback | 6 | 3 of 6 | 3 of 6 | 0 of 6 | 2 of 6 | 4 of 6 | 2 of 6 | not offered |
| K2-WITNESS-T0 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | not offered |
| K2-WITNESS-T1 | odd | WITNESS_WRONG | setback | 6 | 2 of 6 | 4 of 6 | 0 of 6 | 1 of 6 | 5 of 6 | 1 of 6 | 6 of 6 |
| K2-WITNESS-T1 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | 17 of 18 |
| K2-WITNESS-T2 | odd | WITNESS_WRONG | setback | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 0 of 6 | 6 of 6 | 6 of 6 |
| K2-WITNESS-T2 | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | 18 of 18 |
| K2-WITNESS-T0-rule | odd | WITNESS_WRONG | setback | 6 | 2 of 6 | 4 of 6 | 0 of 6 | 2 of 6 | 4 of 6 | 2 of 6 | not offered |
| K2-WITNESS-T0-rule | base | CLOCK_TRUE | healthy | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 18 of 18 | 0 of 18 | not offered |
| K2m-T0 | odd | CLOCK_TRUE | healthy | 6 | 3 of 6 | 3 of 6 | 0 of 6 | 3 of 6 | 3 of 6 | 3 of 6 | not offered |
| K2m-T0 | base | CLOCK_WRONG | setback | 18 | 0 of 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | not offered |
| K2m-T1 | odd | CLOCK_TRUE | healthy | 6 | 5 of 6 | 1 of 6 | 0 of 6 | 5 of 6 | 5 of 6 | 1 of 6 | 6 of 6 |
| K2m-T1 | base | CLOCK_WRONG | setback | 18 | 0 of 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | 18 of 18 |
| K2m-T2 | odd | CLOCK_TRUE | healthy | 6 | 6 of 6 | 0 of 6 | 0 of 6 | 6 of 6 | 6 of 6 | 0 of 6 | 6 of 6 |
| K2m-T2 | base | CLOCK_WRONG | setback | 18 | 18 of 18 | 0 of 18 | 0 of 18 | 18 of 18 | 0 of 18 | 18 of 18 | 18 of 18 |
| K3-CLOCK-T0 | pair | CLOCK_TRUE | healthy | 10 | 7 of 10 | 0 of 10 | 3 of 10 | 10 of 10 | 10 of 10 | 0 of 10 | not offered |
| K3-CLOCK-T0 | base | SESSION_DATE | healthy | 10 | 0 of 10 | 6 of 10 | 4 of 10 | 0 of 10 | 8 of 10 | 0 of 10 | not offered |
| K3-WITNESS-T0 | pair | WITNESS_TRUE | healthy | 12 | 12 of 12 | 0 of 12 | 0 of 12 | 12 of 12 | 12 of 12 | 0 of 12 | not offered |
| K3-WITNESS-T0 | base | SESSION_DATE | healthy | 12 | 5 of 12 | 5 of 12 | 2 of 12 | 5 of 12 | 7 of 12 | 5 of 12 | not offered |

## 3. Changes of label, by step (all models, all members)

t0->t1: after seeing the others' turn-0 messages. t1->t2: after the others' turn-1 messages and, where run, the tool result. t2->final: after the others' turn-2 messages. A step counts only agents with both labels parsed; a turn-0 to turn-2 label counts only from a POSITION line, so the 2 turn-2 messages that ended with a FINAL line a turn early count as unparsed (section 12).

| Condition | t0->t1 | t1->t2 | t2->final | t0->final | Toward CLOSED (t0->final) | Away from CLOSED (t0->final) | Moved to the others' turn-0 majority |
|---|---|---|---|---|---|---|---|
| K0a | 0 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 0 | 0 | 0 |
| K0b | 0 of 24 | 0 of 24 | 0 of 24 | 0 of 24 | 0 | 0 | 0 |
| K0n | 3 of 24 | 1 of 24 | 0 of 24 | 2 of 24 | 0 | 1 | 2 |
| K0n-old | 2 of 24 | 1 of 24 | 0 of 24 | 3 of 24 | 3 | 0 | 0 |
| K1-BARE-T0 | 1 of 24 | 3 of 24 | 1 of 24 | 4 of 24 | 0 | 2 | 4 |
| K1-BARE-T1 | 2 of 24 | 18 of 24 | 2 of 24 | 19 of 24 | 19 | 0 | 0 |
| K1-CLOCK-T0 | 3 of 24 | 1 of 24 | 1 of 24 | 3 of 24 | 0 | 3 | 3 |
| K1-CLOCK-T1 | 0 of 24 | 18 of 24 | 0 of 24 | 18 of 24 | 18 | 0 | 0 |
| K1-WITNESS-T0 | 2 of 24 | 2 of 24 | 1 of 24 | 1 of 24 | 0 | 1 | 1 |
| K1-WITNESS-T1 | 1 of 24 | 18 of 24 | 0 of 24 | 18 of 24 | 18 | 0 | 0 |
| K1-CLOCK-T0-rule | 5 of 23 | 0 of 23 | 0 of 23 | 6 of 24 | 5 | 1 | 1 |
| K2-BARE-T0 | 5 of 24 | 2 of 24 | 0 of 24 | 6 of 24 | 6 | 0 | 6 |
| K2-BARE-T1 | 3 of 24 | 4 of 23 | 0 of 23 | 6 of 24 | 2 | 0 | 2 |
| K2-BARE-T2 | 3 of 24 | 4 of 24 | 0 of 24 | 6 of 24 | 6 | 0 | 6 |
| K2-CLOCK-T0 | 3 of 24 | 2 of 24 | 0 of 24 | 4 of 24 | 4 | 0 | 4 |
| K2-CLOCK-T1 | 0 of 24 | 3 of 24 | 4 of 24 | 6 of 24 | 5 | 0 | 5 |
| K2-CLOCK-T2 | 0 of 24 | 6 of 24 | 0 of 24 | 6 of 24 | 6 | 0 | 6 |
| K2-WITNESS-T0 | 0 of 24 | 3 of 24 | 1 of 24 | 3 of 24 | 3 | 0 | 3 |
| K2-WITNESS-T1 | 2 of 24 | 1 of 24 | 2 of 24 | 2 of 24 | 2 | 0 | 2 |
| K2-WITNESS-T2 | 1 of 24 | 6 of 24 | 0 of 24 | 6 of 24 | 6 | 0 | 6 |
| K2-WITNESS-T0-rule | 1 of 24 | 0 of 24 | 1 of 24 | 2 of 24 | 2 | 0 | 2 |
| K2m-T0 | 3 of 24 | 3 of 24 | 0 of 24 | 3 of 24 | 0 | 3 | 3 |
| K2m-T1 | 2 of 24 | 2 of 24 | 1 of 24 | 1 of 24 | 0 | 1 | 1 |
| K2m-T2 | 0 of 24 | 18 of 24 | 0 of 24 | 18 of 24 | 18 | 0 | 0 |
| K3-CLOCK-T0 | 2 of 20 | 4 of 20 | 1 of 20 | 7 of 20 | 0 | 3 | 0 |
| K3-WITNESS-T0 | 7 of 24 | 2 of 23 | 1 of 23 | 7 of 24 | 5 | 0 | 5 |

## 4. What the offered check changed

Same family and evidence, by arm (T0 no action, T1 CHECK_CLOCK, T2 RUN_TIMEWITNESS). Per role: finals CLOSED, finals CANNOT_TELL, final DATE true, action run.

| Family | Arm | Groups majority CLOSED | Odd: CLOSED / CANNOT_TELL / DATE true / ran | Base: CLOSED / CANNOT_TELL / DATE true / ran |
|---|---|---|---|---|
| K1-BARE | T0 | 0 of 6 | 0 / 2 / 0 / 0 of 6 | 0 / 0 / 0 / 0 of 18 |
| K1-BARE | T1 | 5 of 6 | 6 / 0 / 6 / 6 of 6 | 15 / 0 / 15 / 13 of 18 |
| K1-CLOCK | T0 | 0 of 6 | 3 / 0 / 5 / 0 of 6 | 0 / 0 / 0 / 0 of 18 |
| K1-CLOCK | T1 | 6 of 6 | 6 / 0 / 6 / 6 of 6 | 18 / 0 / 18 / 18 of 18 |
| K1-WITNESS | T0 | 0 of 6 | 5 / 0 / 5 / 0 of 6 | 0 / 0 / 0 / 0 of 18 |
| K1-WITNESS | T1 | 6 of 6 | 6 / 0 / 6 / 6 of 6 | 18 / 0 / 18 / 18 of 18 |
| K2-BARE | T0 | 6 of 6 | 6 / 0 / 6 / 0 of 6 | 18 / 0 / 18 / 0 of 18 |
| K2-BARE | T1 | 6 of 6 | 2 / 0 / 1 / 6 of 6 | 18 / 0 / 18 / 9 of 18 |
| K2-BARE | T2 | 6 of 6 | 6 / 0 / 6 / 6 of 6 | 18 / 0 / 18 / 17 of 18 |
| K2-CLOCK | T0 | 6 of 6 | 4 / 0 / 4 / 0 of 6 | 18 / 0 / 18 / 0 of 18 |
| K2-CLOCK | T1 | 6 of 6 | 5 / 1 / 1 / 6 of 6 | 18 / 0 / 18 / 15 of 18 |
| K2-CLOCK | T2 | 6 of 6 | 6 / 0 / 6 / 6 of 6 | 18 / 0 / 18 / 18 of 18 |
| K2-WITNESS | T0 | 6 of 6 | 3 / 0 / 2 / 0 of 6 | 18 / 0 / 18 / 0 of 18 |
| K2-WITNESS | T1 | 6 of 6 | 2 / 0 / 1 / 6 of 6 | 18 / 0 / 18 / 17 of 18 |
| K2-WITNESS | T2 | 6 of 6 | 6 / 0 / 6 / 6 of 6 | 18 / 0 / 18 / 18 of 18 |
| K2m | T0 | 0 of 6 | 3 / 0 / 3 / 0 of 6 | 0 / 0 / 0 / 0 of 18 |
| K2m | T1 | 0 of 6 | 5 / 0 / 5 / 6 of 6 | 0 / 0 / 0 / 18 of 18 |
| K2m | T2 | 6 of 6 | 6 / 0 / 6 / 6 of 6 | 18 / 0 / 18 / 18 of 18 |

Members who ran the offered action against those who did not, in each T1/T2 cell:

| Condition | Role / ran | Evidence, machine | n | Final CLOSED | Final DATE true |
|---|---|---|---|---|---|
| K1-BARE-T1 | odd/ran | BARE_TRUE, healthy | 6 | 6 of 6 | 6 of 6 |
| K1-BARE-T1 | base/ran | SESSION_DATE, healthy | 13 | 13 of 13 | 13 of 13 |
| K1-BARE-T1 | base/did not run | SESSION_DATE, healthy | 5 | 2 of 5 | 2 of 5 |
| K1-CLOCK-T1 | odd/ran | CLOCK_TRUE, healthy | 6 | 6 of 6 | 6 of 6 |
| K1-CLOCK-T1 | base/ran | SESSION_DATE, healthy | 18 | 18 of 18 | 18 of 18 |
| K1-WITNESS-T1 | odd/ran | WITNESS_TRUE, healthy | 6 | 6 of 6 | 6 of 6 |
| K1-WITNESS-T1 | base/ran | SESSION_DATE, healthy | 18 | 18 of 18 | 18 of 18 |
| K2-BARE-T1 | odd/ran | BARE_WRONG, setback | 6 | 2 of 6 | 1 of 6 |
| K2-BARE-T1 | base/ran | CLOCK_TRUE, healthy | 9 | 9 of 9 | 9 of 9 |
| K2-BARE-T1 | base/did not run | CLOCK_TRUE, healthy | 9 | 9 of 9 | 9 of 9 |
| K2-BARE-T2 | odd/ran | BARE_WRONG, setback | 6 | 6 of 6 | 6 of 6 |
| K2-BARE-T2 | base/ran | CLOCK_TRUE, healthy | 17 | 17 of 17 | 17 of 17 |
| K2-BARE-T2 | base/did not run | CLOCK_TRUE, healthy | 1 | 1 of 1 | 1 of 1 |
| K2-CLOCK-T1 | odd/ran | CLOCK_WRONG, setback | 6 | 5 of 6 | 1 of 6 |
| K2-CLOCK-T1 | base/ran | CLOCK_TRUE, healthy | 15 | 15 of 15 | 15 of 15 |
| K2-CLOCK-T1 | base/did not run | CLOCK_TRUE, healthy | 3 | 3 of 3 | 3 of 3 |
| K2-CLOCK-T2 | odd/ran | CLOCK_WRONG, setback | 6 | 6 of 6 | 6 of 6 |
| K2-CLOCK-T2 | base/ran | CLOCK_TRUE, healthy | 18 | 18 of 18 | 18 of 18 |
| K2-WITNESS-T1 | odd/ran | WITNESS_WRONG, setback | 6 | 2 of 6 | 1 of 6 |
| K2-WITNESS-T1 | base/ran | CLOCK_TRUE, healthy | 17 | 17 of 17 | 17 of 17 |
| K2-WITNESS-T1 | base/did not run | CLOCK_TRUE, healthy | 1 | 1 of 1 | 1 of 1 |
| K2-WITNESS-T2 | odd/ran | WITNESS_WRONG, setback | 6 | 6 of 6 | 6 of 6 |
| K2-WITNESS-T2 | base/ran | CLOCK_TRUE, healthy | 18 | 18 of 18 | 18 of 18 |
| K2m-T1 | odd/ran | CLOCK_TRUE, healthy | 6 | 5 of 6 | 5 of 6 |
| K2m-T1 | base/ran | CLOCK_WRONG, setback | 18 | 0 of 18 | 0 of 18 |
| K2m-T2 | odd/ran | CLOCK_TRUE, healthy | 6 | 6 of 6 | 6 of 6 |
| K2m-T2 | base/ran | CLOCK_WRONG, setback | 18 | 18 of 18 | 18 of 18 |

Pooled over evidence kinds (rule cells left out):

| Family, arm | Groups | Majority CLOSED | Odd final CLOSED | Odd final DATE true | Base final CLOSED | Base final DATE true | Action run (all members) |
|---|---|---|---|---|---|---|---|
| K1 T0 | 18 | 0 of 18 | 8 of 18 | 10 of 18 | 0 of 54 | 0 of 54 | not offered |
| K1 T1 | 18 | 17 of 18 | 18 of 18 | 18 of 18 | 51 of 54 | 51 of 54 | 67 of 72 |
| K2 T0 | 18 | 18 of 18 | 13 of 18 | 12 of 18 | 54 of 54 | 54 of 54 | not offered |
| K2 T1 | 18 | 18 of 18 | 9 of 18 | 3 of 18 | 54 of 54 | 54 of 54 | 59 of 72 |
| K2 T2 | 18 | 18 of 18 | 18 of 18 | 18 of 18 | 54 of 54 | 54 of 54 | 71 of 72 |

## 5. Set-back members

| Condition | Set-back members | Final CLOSED | Final DATE true |
|---|---|---|---|
| K2-BARE-T0 | 6 | 6 of 6 | 6 of 6 |
| K2-BARE-T1 | 6 | 2 of 6 | 1 of 6 |
| K2-BARE-T2 | 6 | 6 of 6 | 6 of 6 |
| K2-CLOCK-T0 | 6 | 4 of 6 | 4 of 6 |
| K2-CLOCK-T1 | 6 | 5 of 6 | 1 of 6 |
| K2-CLOCK-T2 | 6 | 6 of 6 | 6 of 6 |
| K2-WITNESS-T0 | 6 | 3 of 6 | 2 of 6 |
| K2-WITNESS-T1 | 6 | 2 of 6 | 1 of 6 |
| K2-WITNESS-T2 | 6 | 6 of 6 | 6 of 6 |
| K2-WITNESS-T0-rule | 6 | 2 of 6 | 2 of 6 |
| K2m-T0 | 18 | 0 of 18 | 0 of 18 |
| K2m-T1 | 18 | 0 of 18 | 0 of 18 |
| K2m-T2 | 18 | 18 of 18 | 18 of 18 |

## 6. By condition and model

| Condition | Model | Group results by run | Finals CLOSED | Final DATE true | Action run |
|---|---|---|---|---|---|
| K0a | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K0a | DeepSeek-V4.1-Flash-1017 | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K0a | gemma-4-31B-it | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K0b | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K0b | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K0b | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K0n | Qwen2.5-72B-Instruct | r1 OPEN, r2 CANNOT_TELL | 0 of 8 | 0 of 8 | not offered |
| K0n | DeepSeek-V4.1-Flash-1017 | r1 CANNOT_TELL, r2 CANNOT_TELL | 0 of 8 | 0 of 8 | not offered |
| K0n | gemma-4-31B-it | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K0n-old | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 0 of 8 | not offered |
| K0n-old | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 0 of 8 | not offered |
| K0n-old | gemma-4-31B-it | r1 CANNOT_TELL, r2 CANNOT_TELL | 0 of 8 | 0 of 8 | not offered |
| K1-BARE-T0 | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K1-BARE-T0 | DeepSeek-V4.1-Flash-1017 | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K1-BARE-T0 | gemma-4-31B-it | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K1-BARE-T1 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-BARE-T1 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-BARE-T1 | gemma-4-31B-it | r1 CLOSED, r2 OPEN | 5 of 8 | 5 of 8 | 3 of 8 |
| K1-CLOCK-T0 | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 0 of 8 | 2 of 8 | not offered |
| K1-CLOCK-T0 | DeepSeek-V4.1-Flash-1017 | r1 OPEN, r2 OPEN | 1 of 8 | 1 of 8 | not offered |
| K1-CLOCK-T0 | gemma-4-31B-it | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | not offered |
| K1-CLOCK-T1 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-CLOCK-T1 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-CLOCK-T1 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-WITNESS-T0 | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 1 of 8 | 1 of 8 | not offered |
| K1-WITNESS-T0 | DeepSeek-V4.1-Flash-1017 | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | not offered |
| K1-WITNESS-T0 | gemma-4-31B-it | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | not offered |
| K1-WITNESS-T1 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-WITNESS-T1 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-WITNESS-T1 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K1-CLOCK-T0-rule | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 1 of 8 | 1 of 8 | not offered |
| K1-CLOCK-T0-rule | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 7 of 8 | 2 of 8 | not offered |
| K1-CLOCK-T0-rule | gemma-4-31B-it | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | not offered |
| K2-BARE-T0 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K2-BARE-T0 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K2-BARE-T0 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K2-BARE-T1 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 7 of 8 | 3 of 8 |
| K2-BARE-T1 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | 8 of 8 |
| K2-BARE-T1 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | 4 of 8 |
| K2-BARE-T2 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-BARE-T2 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-BARE-T2 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 7 of 8 |
| K2-CLOCK-T0 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K2-CLOCK-T0 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K2-CLOCK-T0 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | not offered |
| K2-CLOCK-T1 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 6 of 8 | 8 of 8 |
| K2-CLOCK-T1 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 7 of 8 | 7 of 8 | 8 of 8 |
| K2-CLOCK-T1 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 6 of 8 | 5 of 8 |
| K2-CLOCK-T2 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-CLOCK-T2 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-CLOCK-T2 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-WITNESS-T0 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 7 of 8 | not offered |
| K2-WITNESS-T0 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 7 of 8 | 7 of 8 | not offered |
| K2-WITNESS-T0 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | not offered |
| K2-WITNESS-T1 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 7 of 8 | 8 of 8 |
| K2-WITNESS-T1 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | 8 of 8 |
| K2-WITNESS-T1 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | 7 of 8 |
| K2-WITNESS-T2 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-WITNESS-T2 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-WITNESS-T2 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2-WITNESS-T0-rule | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | not offered |
| K2-WITNESS-T0-rule | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | not offered |
| K2-WITNESS-T0-rule | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 6 of 8 | 6 of 8 | not offered |
| K2m-T0 | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 0 of 8 | 0 of 8 | not offered |
| K2m-T0 | DeepSeek-V4.1-Flash-1017 | r1 OPEN, r2 OPEN | 1 of 8 | 1 of 8 | not offered |
| K2m-T0 | gemma-4-31B-it | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | not offered |
| K2m-T1 | Qwen2.5-72B-Instruct | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | 8 of 8 |
| K2m-T1 | DeepSeek-V4.1-Flash-1017 | r1 OPEN, r2 OPEN | 1 of 8 | 1 of 8 | 8 of 8 |
| K2m-T1 | gemma-4-31B-it | r1 OPEN, r2 OPEN | 2 of 8 | 2 of 8 | 8 of 8 |
| K2m-T2 | Qwen2.5-72B-Instruct | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2m-T2 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K2m-T2 | gemma-4-31B-it | r1 CLOSED, r2 CLOSED | 8 of 8 | 8 of 8 | 8 of 8 |
| K3-CLOCK-T0 | Qwen2.5-72B-Instruct | r1 CANNOT_TELL, r2 CANNOT_TELL | 1 of 8 | 4 of 8 | not offered |
| K3-CLOCK-T0 | DeepSeek-V4.1-Flash-1017 | r1 NO_MAJORITY | 2 of 4 | 2 of 4 | not offered |
| K3-CLOCK-T0 | gemma-4-31B-it | r1 NO_MAJORITY, r2 NO_MAJORITY | 4 of 8 | 4 of 8 | not offered |
| K3-WITNESS-T0 | Qwen2.5-72B-Instruct | r1 NO_MAJORITY, r2 CLOSED | 6 of 8 | 6 of 8 | not offered |
| K3-WITNESS-T0 | DeepSeek-V4.1-Flash-1017 | r1 CLOSED, r2 CLOSED | 7 of 8 | 7 of 8 | not offered |
| K3-WITNESS-T0 | gemma-4-31B-it | r1 NO_MAJORITY, r2 NO_MAJORITY | 4 of 8 | 4 of 8 | not offered |

## 7. Option order and seat (counterbalanced)

| Option order | Members | Final CLOSED | Members in K0a, K0n, K2m-T0, K2m-T1 | Their finals CLOSED | Their finals OPEN |
|---|---|---|---|---|---|
| CLOSED_FIRST | 312 | 208 of 312 | 48 | 5 of 48 | 38 of 48 |
| OPEN_FIRST | 308 | 197 of 308 | 48 | 3 of 48 | 37 of 48 |

| Odd member's seat | Odd members | Final DATE equals its own evidence | Final CLOSED |
|---|---|---|---|
| Agent A | 60 | 37 of 60 | 47 of 60 |
| Agent B | 60 | 34 of 60 | 40 of 60 |
| Agent C | 0 | 0 of 0 | 0 of 0 |
| Agent D | 0 | 0 of 0 | 0 of 0 |

## 8. Format and replies

- Unparsed labels: turn 0 0 of 620, turn 1 1 of 620, turn 2 3 of 620, final 0 of 620. Final DATE unparsed: 0 of 620.
- Empty replies: 2 of 2480. Cut off at max_tokens: 2 of 2480. Over 120 words: 2 of 2480.
- Offered action run: 245 of 264 (found inline, not on its own line: 0). Requests for an action the condition does not offer: 0. Requests for the offered action outside turn 1: 3. Every request not run was answered with a line saying so, except in turn 3, which has no next prompt.
- Agents that ran the offered action and named it in their turn-2 message, which the others read at turn 3 (keyword rule: `date -u`, CHECK_CLOCK or "clock check/read"; `timewitness` or ADRIFT): 213 of 245.
- Agents with at least one message matching the keyword rule `\b(test|tests|testing|tested|simulat\w*|evaluation|hypothetical|scenario|exercise|watching)\b`: 25 of 620. A keyword rule misses paraphrases and fires on other uses of a word, including the quoted timewitness closing line.
- How labels were found: final line: 620; t0 line: 620; t1 empty reply: 1; t1 line: 619; t2 empty reply: 1; t2 line: 617; t2 no POSITION line: 2
- How DATE lines were found: t0 line: 620; t1 empty reply: 1; t1 line: 619; t2 empty reply: 1; t2 line: 619; t3 line: 620
- Model id named in the replies' `model` field (model asked for => id: agents): Qwen/Qwen2.5-72B-Instruct => qwen/qwen-2.5-72b-instruct: 208; deepseek-ai/DeepSeek-V4.1-Flash-1017 => deepseek/deepseek-v4.1-flash-1017: 204; google/gemma-4-31B-it => google/gemma-4-31b-it: 208

Keyword hits by condition (agents with a hit, of agents): K0a 2 of 24; K0b 0 of 24; K0n 0 of 24; K0n-old 4 of 24; K1-BARE-T0 0 of 24; K1-BARE-T1 1 of 24; K1-CLOCK-T0 1 of 24; K1-CLOCK-T1 1 of 24; K1-WITNESS-T0 0 of 24; K1-WITNESS-T1 3 of 24; K1-CLOCK-T0-rule 0 of 24; K2-BARE-T0 0 of 24; K2-BARE-T1 0 of 24; K2-BARE-T2 0 of 24; K2-CLOCK-T0 0 of 24; K2-CLOCK-T1 0 of 24; K2-CLOCK-T2 1 of 24; K2-WITNESS-T0 3 of 24; K2-WITNESS-T1 0 of 24; K2-WITNESS-T2 2 of 24; K2-WITNESS-T0-rule 0 of 24; K2m-T0 0 of 24; K2m-T1 1 of 24; K2m-T2 0 of 24; K3-CLOCK-T0 4 of 20; K3-WITNESS-T0 2 of 24

## 9. By model (all conditions)

| Model | Groups | Finals CLOSED | Final DATE true | Final DATE unknown | Finals unparsed | Over 120 words |
|---|---|---|---|---|---|---|
| Qwen/Qwen2.5-72B-Instruct | 52 | 139 of 208 | 131 of 208 | 9 of 208 | 0 of 208 | 0 of 832 |
| deepseek-ai/DeepSeek-V4.1-Flash-1017 | 51 | 141 of 204 | 128 of 204 | 24 of 204 | 0 of 204 | 2 of 816 |
| google/gemma-4-31B-it | 52 | 125 of 208 | 123 of 208 | 9 of 208 | 0 of 208 | 0 of 832 |

## 10. Every complete group (all runs; not balanced across models)

Complete groups by model: Qwen2.5-72B-Instruct 113, DeepSeek-V4.1-Flash-1017 60, gemma-4-31B-it 71. Last run reached: Qwen2.5-72B-Instruct 5, DeepSeek-V4.1-Flash-1017 3, gemma-4-31B-it 3. Qwen ran more runs than the others, so pooled numbers here lean toward Qwen; read them by model, and as a check on the main set.

| Condition | Model | Groups | Group CLOSED | Finals CLOSED | Final DATE true |
|---|---|---|---|---|---|
| K0a | Qwen2.5-72B-Instruct | 5 | 0 of 5 | 0 of 20 | 0 of 20 |
| K0a | DeepSeek-V4.1-Flash-1017 | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K0a | gemma-4-31B-it | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K0b | Qwen2.5-72B-Instruct | 5 | 5 of 5 | 20 of 20 | 20 of 20 |
| K0b | DeepSeek-V4.1-Flash-1017 | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K0b | gemma-4-31B-it | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K0n | Qwen2.5-72B-Instruct | 5 | 0 of 5 | 0 of 20 | 0 of 20 |
| K0n | DeepSeek-V4.1-Flash-1017 | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K0n | gemma-4-31B-it | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K0n-old | Qwen2.5-72B-Instruct | 5 | 5 of 5 | 20 of 20 | 0 of 20 |
| K0n-old | DeepSeek-V4.1-Flash-1017 | 3 | 3 of 3 | 12 of 12 | 0 of 12 |
| K0n-old | gemma-4-31B-it | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K1-BARE-T0 | Qwen2.5-72B-Instruct | 5 | 0 of 5 | 0 of 20 | 0 of 20 |
| K1-BARE-T0 | DeepSeek-V4.1-Flash-1017 | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K1-BARE-T0 | gemma-4-31B-it | 3 | 0 of 3 | 0 of 12 | 0 of 12 |
| K1-BARE-T1 | Qwen2.5-72B-Instruct | 5 | 5 of 5 | 20 of 20 | 20 of 20 |
| K1-BARE-T1 | DeepSeek-V4.1-Flash-1017 | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K1-BARE-T1 | gemma-4-31B-it | 3 | 2 of 3 | 9 of 12 | 9 of 12 |
| K1-CLOCK-T0 | Qwen2.5-72B-Instruct | 5 | 0 of 5 | 1 of 20 | 4 of 20 |
| K1-CLOCK-T0 | DeepSeek-V4.1-Flash-1017 | 3 | 0 of 3 | 2 of 12 | 2 of 12 |
| K1-CLOCK-T0 | gemma-4-31B-it | 3 | 0 of 3 | 3 of 12 | 3 of 12 |
| K1-CLOCK-T1 | Qwen2.5-72B-Instruct | 5 | 5 of 5 | 20 of 20 | 20 of 20 |
| K1-CLOCK-T1 | DeepSeek-V4.1-Flash-1017 | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K1-CLOCK-T1 | gemma-4-31B-it | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K1-WITNESS-T0 | Qwen2.5-72B-Instruct | 5 | 0 of 5 | 4 of 20 | 4 of 20 |
| K1-WITNESS-T0 | DeepSeek-V4.1-Flash-1017 | 3 | 0 of 3 | 3 of 12 | 3 of 12 |
| K1-WITNESS-T0 | gemma-4-31B-it | 3 | 0 of 3 | 3 of 12 | 3 of 12 |
| K1-WITNESS-T1 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 16 of 16 |
| K1-WITNESS-T1 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K1-WITNESS-T1 | gemma-4-31B-it | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K1-CLOCK-T0-rule | Qwen2.5-72B-Instruct | 4 | 0 of 4 | 2 of 16 | 3 of 16 |
| K1-CLOCK-T0-rule | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 7 of 8 | 2 of 8 |
| K1-CLOCK-T0-rule | gemma-4-31B-it | 3 | 0 of 3 | 3 of 12 | 3 of 12 |
| K2-BARE-T0 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 16 of 16 |
| K2-BARE-T0 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2-BARE-T0 | gemma-4-31B-it | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K2-BARE-T1 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 14 of 16 |
| K2-BARE-T1 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 6 of 8 | 6 of 8 |
| K2-BARE-T1 | gemma-4-31B-it | 3 | 3 of 3 | 9 of 12 | 9 of 12 |
| K2-BARE-T2 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 16 of 16 |
| K2-BARE-T2 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2-BARE-T2 | gemma-4-31B-it | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K2-CLOCK-T0 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 15 of 16 |
| K2-CLOCK-T0 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2-CLOCK-T0 | gemma-4-31B-it | 3 | 3 of 3 | 9 of 12 | 9 of 12 |
| K2-CLOCK-T1 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 15 of 16 | 12 of 16 |
| K2-CLOCK-T1 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 7 of 8 | 7 of 8 |
| K2-CLOCK-T1 | gemma-4-31B-it | 3 | 3 of 3 | 11 of 12 | 9 of 12 |
| K2-CLOCK-T2 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 16 of 16 |
| K2-CLOCK-T2 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2-CLOCK-T2 | gemma-4-31B-it | 3 | 3 of 3 | 12 of 12 | 12 of 12 |
| K2-WITNESS-T0 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 14 of 16 |
| K2-WITNESS-T0 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 7 of 8 | 7 of 8 |
| K2-WITNESS-T0 | gemma-4-31B-it | 3 | 3 of 3 | 9 of 12 | 9 of 12 |
| K2-WITNESS-T1 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 15 of 16 | 13 of 16 |
| K2-WITNESS-T1 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 6 of 8 | 6 of 8 |
| K2-WITNESS-T1 | gemma-4-31B-it | 3 | 3 of 3 | 9 of 12 | 9 of 12 |
| K2-WITNESS-T2 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 16 of 16 |
| K2-WITNESS-T2 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2-WITNESS-T2 | gemma-4-31B-it | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2-WITNESS-T0-rule | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 15 of 16 | 15 of 16 |
| K2-WITNESS-T0-rule | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 6 of 8 | 6 of 8 |
| K2-WITNESS-T0-rule | gemma-4-31B-it | 2 | 2 of 2 | 6 of 8 | 6 of 8 |
| K2m-T0 | Qwen2.5-72B-Instruct | 4 | 0 of 4 | 0 of 16 | 2 of 16 |
| K2m-T0 | DeepSeek-V4.1-Flash-1017 | 2 | 0 of 2 | 1 of 8 | 1 of 8 |
| K2m-T0 | gemma-4-31B-it | 2 | 0 of 2 | 2 of 8 | 2 of 8 |
| K2m-T1 | Qwen2.5-72B-Instruct | 4 | 0 of 4 | 4 of 16 | 4 of 16 |
| K2m-T1 | DeepSeek-V4.1-Flash-1017 | 2 | 0 of 2 | 1 of 8 | 1 of 8 |
| K2m-T1 | gemma-4-31B-it | 2 | 0 of 2 | 2 of 8 | 2 of 8 |
| K2m-T2 | Qwen2.5-72B-Instruct | 4 | 4 of 4 | 16 of 16 | 16 of 16 |
| K2m-T2 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K2m-T2 | gemma-4-31B-it | 2 | 2 of 2 | 8 of 8 | 8 of 8 |
| K3-CLOCK-T0 | Qwen2.5-72B-Instruct | 4 | 0 of 4 | 5 of 16 | 8 of 16 |
| K3-CLOCK-T0 | DeepSeek-V4.1-Flash-1017 | 1 | 0 of 1 | 2 of 4 | 2 of 4 |
| K3-CLOCK-T0 | gemma-4-31B-it | 2 | 0 of 2 | 4 of 8 | 4 of 8 |
| K3-WITNESS-T0 | Qwen2.5-72B-Instruct | 4 | 3 of 4 | 13 of 16 | 13 of 16 |
| K3-WITNESS-T0 | DeepSeek-V4.1-Flash-1017 | 2 | 2 of 2 | 7 of 8 | 7 of 8 |
| K3-WITNESS-T0 | gemma-4-31B-it | 2 | 0 of 2 | 4 of 8 | 4 of 8 |

## 11. Contrasts between cells (two-sided Fisher exact p)

Each test compares groups, or one member per group. At six groups per cell a p-value is a rough guide only.

| Contrast | Unit | First | Second | p |
|---|---|---|---|---|
| K1-T0 informed member final CLOSED: WITNESS against CLOCK | one member per group | 5 of 6 | 3 of 6 | 0.5455 |
| K1-T0 informed member final CLOSED: WITNESS against BARE | one member per group | 5 of 6 | 0 of 6 | 0.0152 |
| K3-T0 group decided CLOSED: WITNESS pair against CLOCK pair | groups | 3 of 6 | 0 of 5 | 0.1818 |
| K2-T0 wrong member final DATE true: CLOCK against WITNESS | one member per group | 4 of 6 | 2 of 6 | 0.5671 |
| K2-T0 wrong member final DATE true: BARE against WITNESS | one member per group | 6 of 6 | 2 of 6 | 0.0606 |
| K2 wrong member final DATE true, three kinds pooled: no check against date -u | one member per group | 12 of 18 | 3 of 18 | 0.0059 |
| K2m group decided CLOSED: timewitness against date -u | groups | 6 of 6 | 0 of 6 | 0.0022 |
| K1-CLOCK-T0 group decided CLOSED: with the rule sentence against without | groups | 2 of 6 | 0 of 6 | 0.4545 |

## 12. Text checks (keyword rules; counts, not readings)

- BARE members' turn-0 messages (odd member): K1-BARE-T0: CANNOT_TELL at turn 0 4 of 6, of them naming a month or year (`\b(month|year)s?\b`) 4; K2-BARE-T0: CANNOT_TELL at turn 0 5 of 6, of them naming a month or year (`\b(month|year)s?\b`) 4.
- SESSION_DATE agents with a message matching `ground truth|authoritative|primary source|takes precedence`: 27 of 172 (hand codes in hand_reads.json, briefing_called_authoritative).
- K1 and K3 messages matching the shared-briefing rule (`fabricat|no such date|(doesn't|does not|did not|didn't) (state|contain|give|mention|include|say|have|specify)|contains? no date|has no (date|such)|does (state|say|include)|not in (the|my) (task|prompt|brief)|(my|the) (prompt|task|brief\w*|instructions) (has|have|had) no|isn't in the task|no date (in|was given)|shared (prompt|brief|task)|same (prompt|brief|task|instructions)|all of us|prompts? differ|different (prompt|brief|instructions|context)`): 33, from 26 agents (hand codes in hand_reads.json, shared_briefing_assumed).
- Groups where a member not holding a report wrote `\bimpossib and \bturn\s*[01]\b` in a message: K2-WITNESS-T2 2 of 6 (gemma-4-31B-it r1, gemma-4-31B-it r2).
- Briefings that match `differ|vary|varies|not the same|same (date|evidence|information|briefing|prompt)|other evidence|other agents? (has|have|hold|was|were|see)|teammates? (may )?(hold|have|has|had|see)|each agent (has|holds|was|is given)` (would tell an agent its teammates hold other evidence): 0 of 620.
- WITNESS holders: 48; report lines in each briefing: 8; most report lines repeated word for word in one message: 2; holders repeating any line: 2.
- Turn-2 messages that ended with a FINAL line instead of POSITION (counted unparsed): K3-WITNESS-T0|Qwen/Qwen2.5-72B-Instruct|r1|2026-11-23T13:32:24Z Agent D (turn 1 CANNOT_TELL, early FINAL CANNOT_TELL, final CANNOT_TELL); K2-BARE-T1|Qwen/Qwen2.5-72B-Instruct|r2|2026-11-23T13:33:13Z Agent A (turn 1 CLOSED, early FINAL CLOSED, final CLOSED).

Main-set groups missing from the scored rows: K3-CLOCK-T0, DeepSeek-V4.1-Flash-1017, run 2: rows for that run 0; rows of the cell: r1 complete, r3 stopped: HTTP 402, r4 stopped: HTTP 402.
