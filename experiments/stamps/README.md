# Time brackets between agents whose clocks disagree

This folder tests the stamp feature of `timewitness.py` (`--stamp`, `--check-stamp`, `--order`, `--ref`;
see "Time brackets for messages" in the top-level README) with four agents whose clocks disagree. The
agents are small processes, not language models. Everything ran on 2026-11-23 between 14:03 and 14:13 UTC on one
MacBook (macOS, Python 3.15.2, libfaketime 0.9.13), with tool version 0.2.0. The two-machine part (S4)
did not run: Hugging Face refused both submissions because the account's credit had run out (see S4).
This file is written by `make_readme.py` from the results files.

## Words used here

- **agent**: one long-running process (`agent.py`) under one clock. For each message it reads its own clock,
  writes a message that states the reading, and stamps the message with the tool's own `--stamp` code.
- **self-reported time**: the clock reading an agent wrote into its message, to the millisecond. The analysis
  uses the same reading as the agent stored it in its row, at full precision; the two agree to within 1 ms.
  Graded from the message text instead, every count below stays the same; only the ties at +60 s in S2,
  if graded anyway, come out differently (see S2).
- **stamp**, **window**, **not-before**, **existed-by**: as in the top-level README. The window runs from
  not-before to existed-by, both signed by the Roughtime servers pinned in the tool.
- **true time**: the driver's clock. The driver (`driver.py`) runs unfaked, starts the agents, sends each
  message at a planned true time and records when everything happened.
- **true separation**: the true time between the moments two stamps were committed.
- **right**, **wrong**, **undecided**: a decision that matches the truth, one that is the opposite of the
  truth, and no decision. Reading self-reported times always gives a decision. Stamps give none when the
  windows are too close.
- **tie**: a self-reported decision whose right answer is decided by less than 0.01 s, so that it is counted
  neither right nor wrong. Only the 16 self-reported checks at +60 s in S2 are ties.

## The four clocks

| Agent | How the clock was set | Clock error measured (median over its messages in S1) |
|---|---|---|
| `true` | not faked | +0.055 s |
| `behind-7m` | `faketime -f '-7m'` | -419.945 s |
| `ahead-2h` | `faketime -f '+2h'` | +7200.055 s |
| `set-back-june` | `faketime -f '@2026-06-17 12:00:00'` | -13748581 s (159 days 3 h behind) |

libfaketime reads `@2026-06-17 12:00:00` in the machine's time zone (British Summer Time on that date), so the
set-back clock started at 2026-06-17 11:00:00 UTC when its agent started, and then ticked. Each agent is one
process, so its clock runs on from one message to the next. The agents call the tool's command-line entry
(`main(["--stamp", ...])`) inside that process; no Python start-up is paid per stamp.

How the truth was kept. The monotonic clock on macOS is shared by every process and libfaketime does not fake
it, so each agent reports a monotonic reading with each wall-clock reading, and the driver turns it into true
time. A stamp's true commit time is the agent's clock reading stored in the stamp minus the agent's measured
clock error, measured against the driver's clock as it read at the start of the part. The driver's clock was
checked by `timewitness.py --quick` at the start of each part: LIVE all three times, and NTP put it 0.036 to
0.145 s behind. During S1 the Mac's wall clock moved 0.055 s against its monotonic clock; that is the `true`
agent's +0.055 s above, and it is in the other agents' figures too. True times are good to about 0.2 s.
Elapsed true times in S2 and S3 are differences of the monotonic clock and are good to about a millisecond
(each agent's measured clock error varied by less than 0.001 s within each of those parts). Every right or
wrong below rests on a true time difference of 0.37 s or more, except the self-reported checks at +60 s in
S2, which are decided by milliseconds and counted as ties (see S2).

## Results at a glance

| Part | Question | Decisions | Self-reported times: right / wrong / undecided | Stamps: right / wrong / undecided |
|---|---|---|---|---|
| S1 order, messages 10 s apart | which of two messages came first | 190 pairs | 110 / 80 / 0 | 190 / 0 / 0 |
| S1 order, messages 5 s apart | which of two messages came first | 190 pairs | 110 / 80 / 0 | 189 / 0 / 1 |
| S1 order, messages 2 s apart | which of two messages came first | 190 pairs | 110 / 80 / 0 | 169 / 0 / 21 |
| S1 order, messages 0.5 s apart | which of two messages came first | 190 pairs | 110 / 80 / 0 | 84 / 0 / 106 |
| S1 order, reply chain (each message references the one before) | which of two messages came first | 190 pairs | 110 / 80 / 0 | 190 / 0 / 0 |
| S2 lease, checked at +30 s and +75 s | has a 60 s lease expired | 32 checks | 20 / 12 / 0 | 32 / 0 / 0 |
| S2 lease, checked at +57 s and +63 s (added) | the same, about 3 s from the deadline | 32 checks | 20 / 12 / 0 | 0 / 0 / 32 |
| S2 lease, checked at +60 s (added) | the same, at the deadline | 16 checks | 16 ties (see S2) | 0 / 0 / 16 |
| S3 objection window | does an objection count (60 s from the proposal) | 24 objections | 12 / 12 / 0 | 24 / 0 / 0 |
| S4 two machines | | not run | | |
| S5 altered and forged stamps | which ones does the checker accept, and with what window | 19 stamps (14 altered or forged, 3 unchanged copies, 2 made under far-off clocks) | | every verdict as expected |

No decision made from stamps was wrong in any part. 216 stamps were made in S1 to S3; all 216 verified with
their payloads, and every one of their windows held the true commit time. For 2 of them
(s1-chain-04 and s1-chain-20) the margin was thin: the true commit time lay 0.17 and 0.19 s before existed-by,
less than the 0.2 s to which true times are good. Corrected by NTP's reading of the Mac's clock at the start
of S1, those margins are 0.03 and 0.05 s, and every window still holds its commit time when each part is
corrected by its own NTP readings.
235 rows were stored; 0 failed to parse.

## S1: order

Twenty messages, round robin over the four agents (`true`, `behind-7m`, `ahead-2h`, `set-back-june`), started
10, 5, 2 and 0.5 s apart. Then a reply chain, added to the spec: each message is sent as soon as the one
before it is stamped and puts that stamp's commitment inside its own (`--ref`). Each set was ordered (a) by
the self-reported times in the messages and (b) by `timewitness.py --order` over its 20 stamps. Truth for (b)
is the order of the true commit times, which matched the order in which the driver sent the messages in every
set. Truth for (a) is the order of the true times of the clock readings it compares; in S1 that order was the
same as the commit order for every pair.

| Set | Pairs | Self-reported: right / wrong | Stamps: right / wrong / undecided | Stamps decided by window / reference / through others | Window widths (s: count) | Median seconds per stamp |
|---|---|---|---|---|---|---|
| gap-10s | 190 | 110 / 80 | 190 / 0 / 0 | 190 / 0 / 0 | 2: 18, 6: 2 | 0.43 |
| gap-5s | 190 | 110 / 80 | 189 / 0 / 1 | 189 / 0 / 0 | 2: 19, 6: 1 | 0.40 |
| gap-2s | 190 | 110 / 80 | 169 / 0 / 21 | 169 / 0 / 0 | 2: 19, 6: 1 | 0.40 |
| gap-0.5s | 190 | 110 / 80 | 84 / 0 / 106 | 84 / 0 / 0 | 2: 20 | 0.40 |
| chain | 190 | 110 / 80 | 190 / 0 / 0 | 66 / 19 / 105 | 2: 16, 3: 4 | 0.41 |

Self-reported times put 80 of the 190 pairs in the wrong order in every set: the same pairs each time,
because the clock errors (minutes, hours, months) are much larger than the few seconds to three minutes
each set lasted. All 80 wrong pairs were pairs of messages from two different agents (150 such pairs per
set); the 40 pairs from one agent were always in the right order. Mixing two clocks is what fails.

Stamps never ordered a pair wrongly. Where they stop separating, by the true separation of the two
commitments (the four timed sets together, 760 pairs):

| True separation | Pairs | Ordered by --order | Wrong |
|---|---|---|---|
| 0 to 1 s | 27 | 0 | 0 |
| 1 to 2 s | 45 | 0 | 0 |
| 2 to 3 s | 40 | 0 | 0 |
| 3 to 4 s | 34 | 20 | 0 |
| 4 to 5 s | 40 | 39 | 0 |
| 5 to 6 s | 36 | 36 | 0 |
| 6 to 8 s | 43 | 42 | 0 |
| 8 to 10 s | 37 | 37 | 0 |
| 10 s or more | 458 | 458 | 0 |

No pair less than 3 s apart was ordered. The closest pair ordered by windows was 3.4 s apart. With both
windows 3 s wide or less, the widest pair left undecided was 3.6 s apart; the widest of all, 6.0 s, involved
a 6 s window. A window is 2 s when roughtime.se signs the beacon and the seal in the same second and 3 s when
they fall in different seconds. Window widths across the 216 stamps of S1 to S3: 2 s in 177, 3 s in 35, 6 s in 4.

All 4 of the 6 s windows came from stamps that took between 4 and 5 s instead of about half a second. In 2,
roughtime.se is missing from the stamp (no usable beacon, so the tool used time.txryan.com alone, radius 3 s).
In 2, both seals were signed 4 s after their beacons, which fits roughtime.se's first seal going unanswered
and its second try being answered (the tool tries a seal twice). Both cases fit one lost UDP packet and the
tool's 4 s timeout per exchange; the tool asks for a beacon only once.

In the reply chain every pair was ordered: 19 directly by a reference, 105 through other stamps and 66 by
windows. Each message waited only for the stamp before it (median 0.41 s to make a stamp). A reference orders
a reply after what it answers however close in time the two are.

## S2: a 60-second lease

Four rounds; in each one agent (the holder) stamps a claim: "agent X holds lease L for 60 seconds, starting
at my clock reading T". Each of the four agents (the challengers, the holder included) then asks whether
the lease has expired, at +30 s and +75 s as specified, and also at +57, +60 and +63 s (added, to find
where stamps stop deciding). (a) The challenger compares its own clock with T. (b) The challenger stamps
its question with a reference to the claim and compares windows: expired for certain when its not-before is
more than 60 s plus the tool's 1 s tolerance after the claim's existed-by; not expired for certain when its
existed-by plus 1 s is less than 60 s after the claim's not-before; otherwise undecided. The spec's rule has
no tolerance; both are shown below. Truth differs by method. (a) compares two clock readings, so its truth is
the true time between the claim's clock reading and the challenger's. (b) compares two stamps, so its truth
is the true time between the two commitments. The two times differ by at most 0.14 s here.

| Checked at | Checks | (a) true time between the clock readings (s) | (a) self-reported: right / wrong | (b) true time between the commitments (s) | (b) truly expired | (b) stamps, 1 s tolerance: right / wrong / undecided | (b) stamps, no tolerance |
|---|---|---|---|---|---|---|---|
| +30 s | 16 | 29.995 to 30.004 | 10 / 6 | 30.02 to 30.08 | 0 | 16 / 0 / 0 | 16 / 0 / 0 |
| +57 s | 16 | 56.995 to 57.004 | 10 / 6 | 57.05 to 57.11 | 0 | 0 / 0 / 16 | 16 / 0 / 0 |
| +60 s | 16 | 59.995 to 60.004 | 16 ties | 60.04 to 60.08 | 16 | 0 / 0 / 16 | 0 / 0 / 16 |
| +63 s | 16 | 62.996 to 63.004 | 10 / 6 | 63.03 to 63.14 | 16 | 0 / 0 / 16 | 16 / 0 / 0 |
| +75 s | 16 | 74.999 to 75.004 | 10 / 6 | 75.03 to 75.12 | 16 | 16 / 0 / 0 | 16 / 0 / 0 |

At +60 s the true time between the two clock readings was 59.995 to 60.004 s, within 0.01 s of the deadline, so
whether the lease had expired when the challenger read its clock is decided by milliseconds. The table counts
these 16 checks as ties. Graded anyway, they come out 10 right and 6 wrong with the readings as stored in the
rows, 11 and 5 with the readings as written in the messages, and 8 and 8 with the stored readings graded
against the time between the commitments. One check (holder and challenger both `true`) is wrong by the
stored reading and right by the written one. At +57 s and +63 s, about 3 s from the deadline, the
self-reported check was 20 right and 12 wrong, and all three ways of grading give the same counts there.

Self-reported decisions at +30 s and +75 s, by holder (rows) and challenger (columns):

| Holder \ challenger | `true` | `behind-7m` | `ahead-2h` | `set-back-june` |
|---|---|---|---|---|
| `true` | +30 right, +75 right | +30 right, +75 wrong | +30 wrong, +75 right | +30 right, +75 wrong |
| `behind-7m` | +30 wrong, +75 right | +30 right, +75 right | +30 wrong, +75 right | +30 right, +75 wrong |
| `ahead-2h` | +30 right, +75 wrong | +30 right, +75 wrong | +30 right, +75 right | +30 right, +75 wrong |
| `set-back-june` | +30 wrong, +75 right | +30 wrong, +75 right | +30 wrong, +75 right | +30 right, +75 right |

With the same clock on both sides the self-reported check was right 8 of 8 times: one clock measures a
duration correctly even when it reads the wrong date. Across two clocks it was wrong 12 of 24 times: at
+30 s whenever the challenger's clock was ahead of the holder's (a live lease called expired, 6 times),
and at +75 s whenever it was behind (an expired lease called live, 6 times).
Stamps were right in all 32 checks at +30 s and +75 s. All 80 challengers' stamps verified and referenced
the claim. Near the deadline they said undecided: with the tolerance, at all of +57, +60 and +63 s; without
it, +57 and +63 s were decided right and only +60 s stayed undecided. Every window in S2 was 2 s wide. So
with the tolerance the band where stamps cannot decide covers at least 57 to 63 s after the claim; without
it, the band lies inside that span and covers 60 s.

## S3: a 60-second objection window

Four rounds; in each one agent stamps a proposal with objections open for 60 seconds. The other three agents
object at +40 s (in time) and +80 s (late), each objection stamped with a reference to the proposal. At +70 s
the proposer stamps a closing record that references the three objections it received at +40 s. Rules:
"deadline" counts an objection made no more than 60 s after the proposal; "close" counts an objection made
before the closing record. (a) applies them to self-reported times, (b) to stamps (deadline: windows with the
1 s tolerance, as in S2; close: `--order` over the proposal, the six objections and the closing record).
As in S2, (a) is graded against the true times of the clock readings and (b) against the true commit times;
in S3 the two give the same answer for every objection under both rules.

| Rule | Self-reported: right / wrong / undecided | Stamps: right / wrong / undecided |
|---|---|---|
| deadline (60 s after the proposal) | 12 / 12 / 0 | 24 / 0 / 0 |
| before the closing record | 12 / 12 / 0 | 24 / 0 / 0 |

Self-reported times counted 6 of the 12 late objections and dropped 6 of the 12 in-time ones. Which way
each went depended only on whether the objector's clock was ahead of or behind the proposer's. Stamps
decided all 24 objections right under both rules; every objection was 19.9 s or more from the
deadline, well outside the undecided band found in S2.
31 of S3's 32 stamps had 3 s windows, against 0 of 84 in S2: in S3 roughtime.se signed the beacon and the
seal in different seconds 31 times. That happens when a commitment falls near the turn of a second, and
S3's schedule put its messages there.

## S4: two machines (not run)

The plan: two agents (`true`, `set-back-june`) inside one Hugging Face Job (Linux, cpu-basic) and two
(`behind-7m`, `ahead-2h`) on the MacBook, both drivers on one schedule keyed to a shared start time, the
Job's stamps brought back through its log and ordered with the Mac's, offline.

There were two submissions, and neither created a Job. That was checked, not inferred: the account's list
of Jobs, read on 2026-11-23 at 16:25 UTC, showed none from them. The first (14:07 UTC) was `run_s4.sh`;
its error output was not kept, and an earlier version of the script took a hex request id in that error for
a Job id (see Limits). The second (14:11 UTC) was not a repeat of `run_s4.sh` but a separate 2-minute Job that
only echoes, submitted by hand to read the error. It gave "Client error '402 Payment Required'": "Pre-paid credit balance is insufficient - add more credits to your account to use Jobs." The cause:
the account's pre-paid credit had run out at 13:38 UTC the same day, during the group experiment in
`experiments/consensus/`. Both rows of `data/s4-attempts.jsonl` were written by hand. `run_s4.sh` has since
been changed to read a Job id only when the submission succeeds, and otherwise to append a row to that file
and stop; that corrected failure path has never run.

No Job was created, so nothing was spent, and there is no two-machine result. At the listed USD 0.01 an hour
for cpu-basic, a Job of about 15 minutes would cost under USD 0.01. The Job half of `run_s4.sh` was
rehearsed on the Mac alone (packing, the Job's script, the log markers, the parser, the analysis); that is
not a two-machine result and is not kept here. What S1 to S3 do show is that the check uses nothing of the
machine that made a stamp: agents under four different clocks made stamps that one checker ordered together.

## S5: forgeries

`forgeries.py` takes stamps made earlier in this run (X = the first message of S1's 10 s set, Y = the
second, Z = S3's first proposal, made about 9 minutes after X) and produces 19 stamps to check: 14 altered
or forged, 3 unchanged copies for comparison, and 2 honest stamps made under far-off clocks. It writes the
verdict it expects for each into `data/s5/rows.jsonl`. `analyze.py` checks each with `--check-stamp`, adding
`--payload` for every stamp that has a payload file (all but `orig-s3-P1-proposal`, which is there for `--order`).
The checker gave the expected verdict for every one.

| Stamp | What was done | Checker said | Window |
|---|---|---|---|
| `orig-s1-gap-10s-01` | unchanged copy of s1-gap-10s-01, for comparison | VALID | 2 s |
| `orig-s1-gap-10s-02` | unchanged copy of s1-gap-10s-02, for comparison | VALID | 2 s |
| `orig-s3-P1-proposal` | unchanged copy of s3-P1-proposal (made after X), for --order | VALID | 3 s |
| `payload-changed` | X's stamp, checked against X's message with one character changed | INVALID: the payload's SHA-256 does not match the stamp | none |
| `payload-hash-edited` | X's stamp with payload_sha256 replaced by the changed message's hash | INVALID: the commitment written in the stamp is not the one recomputed from its contents | none |
| `payload-hash-and-commitment-edited` | as above, and the commitment field recomputed to match | INVALID: roughtime.se seal: the seal request's nonce is not this stamp's commitment | none |
| `seal-moved` | Y's stamp with X's seals in place of its own | INVALID: roughtime.se seal: the seal request's nonce is not this stamp's commitment | none |
| `seal-moved-and-commitment-copied` | as above, and Y's commitment field replaced by X's | INVALID: the commitment written in the stamp is not the one recomputed from its contents | none |
| `servers-reordered` | X's two server entries swapped | INVALID: the commitment written in the stamp is not the one recomputed from its contents | none |
| `server-dropped` | X's time.txryan.com entry removed | INVALID: the commitment written in the stamp is not the one recomputed from its contents | none |
| `self-reported-edited` | X's self-reported clock changed to 2036-01-01 | VALID | 2 s |
| `seal-dropped` | X's roughtime.se seal removed | VALID | 4 s |
| `server-renamed` | X's roughtime.se entry renamed to a server not pinned here | VALID | 6 s |
| `old-beacon` | a new message with X's beacons (made in S1) and fresh seals | VALID | 624 s |
| `beacon-time-edited` | X's beacons with their signed time moved 600 s later, fresh seals over the matching commitment | INVALID: roughtime.se beacon: failed: response signature | none |
| `backdated-echo-edited` | a new message with X's beacons, a seal request carrying the new commitment, and X's old seal answer with its nonce echo edited to that commitment | INVALID: roughtime.se seal: failed: Merkle proof over the request packet | none |
| `backdated-old-seal` | a new message with X's beacons and X's seals unchanged | INVALID: roughtime.se seal: the seal request's nonce is not this stamp's commitment | none |
| `clock-2036` | stamped with the tool's command line under faketime -f '@2036-01-01 00:00:00' | VALID | 2 s |
| `clock-1999` | stamped with the tool's command line under faketime -f '@1999-12-31 23:59:00' | VALID | 2 s |

- Every edit tried here of the payload, the commitment, a beacon's or a seal's bytes, or the order or number
  of server entries made the stamp invalid. Removing a seal or renaming a server kept it valid with a wider
  window (next point).
- The edits that stayed valid left X's window as it was or made it wider: changing the self-reported clock
  (2 s, the same), dropping roughtime.se's seal (4 s), renaming roughtime.se so it is not pinned (6 s).
- Reusing X's old beacons for a new message gave a valid stamp whose window began at X's not-before and
  ended at the new seal: 624 s wide (10.4 minutes). Editing a beacon's signed time to claim a later not-before
  broke its signature. `--order` would not put the old-beacon stamp before Z, which was made between its
  beacon and its seal ("overlap: order unknown"), while X before Z was shown ("A before B").
- Backdating a new message into X's window failed both ways tried: X's old seal answer with its nonce echo
  edited (the Merkle proof covers X's request, not the new one), and X's seal unchanged (its request carries
  X's commitment).
- Stamps made with the machine's clock at 2036-01-01 and at 1999-12-31 were valid (windows 2 s and 2 s), and
  each window held the true time it was made; only the self-reported clock showed the faked dates. X checked
  by a process whose own clock read 2036 gave the same window as checked normally.

## What this suggests for agents

These are readings of the tables above, for processes with wrong clocks on one machine.

**Perception of time.** An agent's clock reading is a claim about the agent, not about the world. Read
alone, a wrong clock still measured durations correctly (S2, same clock on both sides). Compared with
another agent's reading, it gave wrong answers in a large share of cases (S1, S2, S3), and nothing in the
readings themselves showed which ones. A stamp moves the time out of the agent: its window comes from
signed answers, so agents with clocks 159 days 3 h apart produced windows that agreed with true time.
A reader holding a message and its stamp can also see how far the author's clock is off: the stated reading
minus the middle of the window matched the author's real clock error to within 0.63 s in the 212 messages
of S1 to S3 whose stamp took 2 s or less, and to within 4.05 s in all of them (the author read its clock
before a stamp that then waited for a lost packet).

**Communication.** A stamp lets a reader place a message in time without trusting the sender's clock, and
the check is offline and the same for every reader. A reply that references the stamp it answers is
ordered after it however fast the exchange is (S1 reply chain). Without references, two messages need about
3 to 6 s between them before their windows order them (S1).

**Collaboration and consensus.** Leases and objection windows of a minute were decided right by stamps in
all 56 cases 15 s or more from the deadline, and left undecided in all 48 cases about 3 s or less from it
(0.04 to 3.14 s; S2, S3); distances in between were not tried. Stamps were never wrong. A protocol that uses
stamps has to say what "undecided" means, for example "a lease is held until a stamp shows it expired" or
"an objection counts unless a stamp shows it late". Self-reported times gave an answer every time and were
wrong in 104 of 198 decisions that compared two different clocks (S1's 10 s set, S2 at +30 and +75 s, S3's
deadline rule).

**Costs and limits for this use.** A stamp took a median of 0.44 s here (four UDP exchanges with two servers;
up to 4.6 s when a packet was lost) and resolves time to about 2 to 3 s, 6 s when a packet is lost. It shows
when bytes were committed, not who wrote them (that needs the author's signature), and it holds only while
the two pinned servers sign true times. None of this says whether anyone is watching or testing; the tool
reports how well time is tied to the outside world, and an agent should act the same either way.

## Limits

- One MacBook, one network, one sitting of about 10 minutes. The agents are processes, not language models.
- Clocks were faked only with libfaketime, in user space. A clock wrong at the system level was not tried.
- In the 10, 5 and 2 s sets every message started at the same fraction of a second, so the mix of 2 s and
  3 s windows reflects the schedule, not how often each occurs (S3's 3 s windows are the same effect).
- True times rest on the Mac's clock (NTP read it within 0.145 s) and on the shared monotonic clock.
- Added to the spec: S1's reply chain, S2's checks at +57, +60 and +63 s, S3's "close" rule, and the 1 s
  tolerance in the window rules of S2 and S3 (S2 also shows the spec's rule without it).
- S4 (two machines) did not run; see above.
- Not shown above: during S1's 5 s set, at 14:07 UTC, the first S4 submission failed, and an earlier version
  of `run_s4.sh` took it for a submitted Job and went on to start the S4 Mac half on this same Mac. That half
  begins with a `timewitness.py --quick` clock check, which asks the same Roughtime servers, and then starts two
  agents that wait. Whether the check ran before the process was stopped is unknown (only one line of its
  output survives). One of the two stamps that lost a beacon, s1-gap-5s-08, was sent at 14:07:16 UTC; no link
  between the two is shown.
- Only the two Roughtime servers pinned in the tool were used. If both signed a wrong time together,
  nothing here would show it.

## Files

- `driver.py`, `agent.py`: run S1, S2 and S3 (`python3 -I experiments/stamps/driver.py s1`), and each half of S4.
- `run_s4.sh`: S4, the Hugging Face Job and the Mac half on one schedule. It has never run to the end.
- `forgeries.py`: S5.
- `analyze.py`: checks every stamp offline with the tool and writes `results/<part>.json`.
- `make_readme.py`: writes this file from the results.
- `data/<part>/`: each message (`*.txt`) and its stamp (`*.stamp.json`), `rows.jsonl` (one row per message,
  with the planned, sent and true times and the agent's clock reading), `run.json` and `clock_check.json`.
  `data/s5/rows.jsonl` says what was done to each altered stamp and the verdict expected.
- `data/s4-attempts.jsonl`: the two refused Job submissions, written by hand. `data/s4-price.json`: the price
  of cpu-basic as `hf jobs hardware` listed it on 2026-11-23; it was not written by `run_s4.sh`, which writes its own
  copy to `data/s4-job/price.json`.
- `results/<part>.json`: the tables above and every pair, check and objection behind them.

## Re-run

```
python3 -I experiments/stamps/driver.py s1      # about 7 minutes; needs libfaketime and UDP to port 2002
python3 -I experiments/stamps/driver.py s2      # about 2 minutes
python3 -I experiments/stamps/driver.py s3      # about 2 minutes
bash experiments/stamps/run_s4.sh               # about 11 minutes; needs the hf CLI with Jobs credit
python3 -I experiments/stamps/forgeries.py      # after s1 and s3
python3 -I experiments/stamps/analyze.py        # offline
python3 -I experiments/stamps/make_readme.py
```
Use Homebrew's python3 on macOS: libfaketime cannot enter the system Python.
