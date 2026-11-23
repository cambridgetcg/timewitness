# timewitness in twelve conditions

Run on 2026-11-14 between 01:40 and 01:43 UTC with the tool as it is in this folder's parent.
Eight conditions ran on one MacBook (macOS, Python 3.15.2, libfaketime 0.9.13 from Homebrew,
`/usr/bin/sandbox-exec` for the no-network runs). Four ran inside one Hugging Face Job
(`python:3.12` image, cpu-basic, Linux x86_64, Python 3.12.16, libfaketime from Debian's `faketime` package).

Each row is one run. `results/<name>.json` is the full report, `results/<name>.txt` the text an
agent would see, `results/<name>.stderr` the exit code. This file is written by `make_readme.py` from those reports.

| Condition | Verdict | Exit | Signed answers made for this request | Witnesses that passed their checks | Flags |
|---|---|---|---|---|---|
| MacBook, as it is (`mac-live`) | LIVE | 0 | 3 of 3 | 10 of 10 | none |
| MacBook, network denied by the OS sandbox (`mac-no-network`) | SEALED | 1 | 0 of 3 | 0 of 10 | none |
| MacBook, clock set back to 2026-06-17 12:00 local time, ticking (`mac-clock-set-back-june`) | ADRIFT | 1 | 3 of 3 | 5 of 10 | faketime_env, other_process_disagrees, filesystem_disagrees |
| MacBook, clock frozen at 2026-06-17 12:00 local time (`mac-clock-frozen`) | ADRIFT | 1 | 3 of 3 | 5 of 10 | faketime_env, clock_frozen, other_process_disagrees, filesystem_disagrees |
| MacBook, clock running 10 times too fast (`mac-clock-10x`) | ANCHORED | 0 | 3 of 3 | 10 of 10 | faketime_env, clock_rate_off, other_process_disagrees |
| MacBook, no network and clock frozen in June (`mac-sealed-and-frozen`) | SEALED | 1 | 0 of 3 | 0 of 10 | faketime_env, clock_frozen, other_process_disagrees, filesystem_disagrees |
| MacBook, every network answer replayed from a recording 90 s old (`mac-replay-90s-later`) | STALE | 1 | 0 of 3 | 5 of 10 | none |
| MacBook, replay, with the clock set back to the recording's moment (`mac-replay-clock-set-back`) | STALE | 1 | 0 of 3 | 5 of 10 | faketime_env, other_process_disagrees, filesystem_disagrees |
| Hugging Face Job (Linux container), as it is (`hf-job-live`) | LIVE | 0 | 3 of 3 | 8 of 10 | none |
| Hugging Face Job, clock set back to 2026-06-17 12:00, ticking (`hf-job-clock-set-back-june`) | ADRIFT | 1 | 3 of 3 | 3 of 10 | faketime_env, other_process_disagrees, filesystem_disagrees |
| Hugging Face Job, clock frozen at 2026-06-17 12:00 (`hf-job-clock-frozen`) | ADRIFT | 1 | 3 of 3 | 3 of 10 | faketime_env, clock_frozen, other_process_disagrees, filesystem_disagrees |
| Hugging Face Job, clock running 10 times too fast (`hf-job-clock-10x`) | ANCHORED | 0 | 3 of 3 | 8 of 10 | faketime_env, clock_rate_off, other_process_disagrees |

12:00 is each machine's local time: the Mac's faked clock started at 11:00 UTC and the Job's at 12:00 UTC.
An earlier run of this experiment called the set-back clock "frozen". It was not: `faketime 'DATE' command`
turns the date into an offset and the clock ticks on. A frozen clock needs `faketime -f 'DATE'`, used here.

## What the rows show

- **A clock moved away from the real time is caught while the network is open.** In the four runs with the clock
  set back or frozen, the two Roughtime servers and the timestamp authority signed this run's own random value,
  so the tool gave the signed time and how far the local clock was from it (149 days 14 h behind on the Mac).
- **A frozen clock also shows up locally.** The wall clock moved 0.00 s during a 2 s sleep on the Mac while the
  monotonic clock moved 2.00 s. In the Linux Job libfaketime froze the monotonic clock too (0.00 s); the kernel's
  own uptime counter moved 1.91 s. All three frozen runs carry the `clock_frozen` flag.
- **With a clock far from now, TLS stops working.** Certificates look not yet valid, so the HTTP, Hub and
  Bitcoin witnesses failed in all four of those runs. Roughtime (a pinned key, no certificates) and the
  timestamp authority (checked without the local clock) still answered.
- **A clock that only runs fast agrees with the signed answers at the start**, so the verdict is ANCHORED with a
  rate flag. On the Mac the wall clock ran 10.00 times the monotonic clock. In the Job libfaketime sped up the
  monotonic clock as well (ratio 1.0000); the kernel's uptime counter showed 0.20 s against 2.00 s of wall time.
  The witnesses ran one after another, so the ones asked later met a clock that had run ahead: the local clock
  agreed with 4 of 10 on the Mac and 4 of 8 in the Job (the signed answers and Bitcoin), and the reading says so.
  The first line's time is 5 s (Mac) and 6 s (Job) after the signed answers, which is the time the rest of
  the run took.
- **A replayed world is caught by the nonce, not by the clock.** With the local clock set back to the moment of
  the recording, the five witnesses that carry nothing of ours (Bitcoin, the Hub, three HTTP Date headers) all
  passed and all agreed with the clock. The five that must return a value this run had just invented all
  failed: two Roughtime answers and the timestamp token (signed, but for another request), and two NTP answers
  (the random transmit value did not come back). The signed ones make the verdict STALE.
- **Sealed and frozen leaves only local evidence.** With no network, the first line shows the faked time
  (2026-06-17T11:00:00Z), marked unchecked. The flags still say the clock is being faked: it did not move, and a
  child `date` process and a new file's mtime read a time 149 days 14 h later.
- **A container seconds old shows the host's uptime** (43 days in the Job). The Job's id holds the time its
  record was created, 16 s before the first run started; the tool reports it as an unsigned not-before.
- **Small things that differed between the two machines.** From the Job, NTP (UDP port 123) never answered
  (0 of 8 tries), while Roughtime (UDP port 2002) always did (8 of 8).
- **None of this says whether anyone was watching.** The live MacBook run and the live Job run gave the same
  verdict for the same reason: both were connected to the real network at the real time.

## Limits

- One run per condition, one machine of each kind, one clock-faking tool (libfaketime), which works in user
  space and leaves its name in the environment. A clock faked in a hypervisor or kernel was not tried.
- The replay runs use the tool's own `--replay` flag, which answers every exchange from a file. A real
  record/replay proxy that also terminates TLS was not built.
- The Job has open outbound network. Hugging Face Jobs offer no switch to cut it, so no sealed run was made there.
- The recording used for the replay runs is not kept: it holds other people's public repo names and raw server answers.
- The reports give the machine's time zone name and offset, as the local witness reads them.

## Re-run

```
bash experiments/environments/run_mac.sh        # the eight Mac conditions; needs libfaketime and sandbox-exec
bash experiments/environments/run_hf_job.sh     # the four Job conditions; needs the hf CLI, logged in, with Jobs credit
python3 -I experiments/environments/make_readme.py
```
