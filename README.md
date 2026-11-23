---
pretty_name: timewitness
language:
- en
tags:
- time
- agents
- clocks
- temporal-awareness
- evaluation
viewer: false
---

# timewitness

timewitness reports how well the clock in this environment is tied to the
outside world. It asks several independent witnesses what time it is, checks
what each answer proves, compares them with the local clock, and prints a
short verdict plus full JSON.

It does not report whether anyone is watching or testing. It is not a test
detector, and its output should not be read as one. An agent should act the
same either way.

Source: <https://github.com/cambridgetcg/timewitness>. The same folder, with
the experiment records and a ledger of runs, is the Hugging Face dataset
<https://huggingface.co/datasets/Yu-and-Ai/timewitness>. No licence has been
chosen yet.

## Why

An agent has no clock of its own. Every time it knows arrives as text: a date
in a prompt, a timestamp in a log, a clock read through a tool. Text can be
old, wrong or made up. A witness from outside can be checked. This tool
gathers such witnesses and says what they show, and what they cannot show.

## Three kinds of evidence

| Kind | What it proves | Witnesses | Anchor it trusts |
|---|---|---|---|
| freshness | A signed answer bound to a value this run just invented, so the answer was made after the request. It gives a signed time too. | Roughtime (roughtime.se, time.txryan.com); RFC 3161 timestamp from DigiCert | Roughtime: an Ed25519 key pinned in this file. TSA: a system CA bundle (not one named by `SSL_CERT_FILE`), and the signer must be DigiCert's timestamp responder. |
| not-before | An artifact that nobody could have made before time T, so now is at least T. | Bitcoin headers with proof of work; NIST randomness beacon pulse (`--all`) | Bitcoin: the work itself, the genesis hash and a difficulty floor in this file. NIST: a system CA bundle. The pulse's signing certificate must chain to it and name engine.beacon.nist.gov. |
| unsigned time | A server says a time. Nothing binds it to this request beyond TLS, or not at all. | HTTP `Date` over TLS (3 operators), NTP (2 servers), the Hugging Face Hub's newest repos, drand round number and Ethereum slot (`--all`) | HTTP and the Hub: the CA bundle Python uses. NTP, drand, Ethereum: none. |

Details for each witness:

- **Roughtime.** A 1024-byte request (some servers ignore shorter ones) with a
  fresh 32-byte nonce. The tool checks the delegation signature, the response
  signature, MINT <= MIDP <= MAXT, the nonce echo, and the Merkle path whose
  leaf is the full request packet. roughtime.se answers draft-12
  (version 0x8000000c, context strings spelt "RoughTime"); time.txryan.com
  answers RFC 10049 version 1 ("Roughtime"). The second server's nonce is the
  first 32 bytes of SHA-512(first answer + 32 random bytes). Both answers and
  the 32 random bytes are kept in the JSON (`response_b64`, `blind_hex`), so
  anyone can recompute the chain. Whether the second time is earlier than the
  first by more than both radii is recorded as `chain_order_ok`; it does not
  change the verdict (two signed times far apart show up in the conflict
  test). The top-level message type must be a response. Ed25519 is checked in
  pure Python; no openssl needed. Non-canonical point encodings and
  small-order public keys are refused.
- **RFC 3161 TSA.** Needs the `openssl` command (OpenSSL 3 or newer works; an
  older one is tried anyway). One request over 32 fresh random bytes, with a
  nonce. Verified with `openssl ts -verify -queryfile ... -no_check_time`
  against the CA file this Python's OpenSSL was built with, then
  `/etc/ssl/cert.pem`, then a common Linux bundle, and last a bundle named by
  `SSL_CERT_FILE`. A token that verifies only with that last bundle is not
  counted: one environment variable should not choose the anchor. The token's
  signer must be a DigiCert timestamp certificate; openssl alone accepts any
  timestamping certificate that chains to the bundle. The output names the
  bundle that verified. `-no_check_time` is used because the local clock may
  be the thing that is wrong. Skipped by `--quick`.
- **Bitcoin.** The newest 12 headers from mempool.space and from
  blockstream.info. Each header is rebuilt from the API's fields and hashed
  with double SHA-256; the hash must equal the claimed hash and be below the
  target from `bits`; headers must link by previous hash; every header's
  difficulty must be at least `DIFFICULTY_FLOOR` (4.0e13; it was 1.48e14 on
  2026-11-13). A chain far below remembered difficulty is cheap to forge, so
  it is refused. A source with any problem is left out, and only sources that
  passed are compared: they must agree on every height both returned. Block 0
  is fetched by its known hash and must hash to the genesis constant. That
  shows the API serves the real genesis block; it does not show that the 12
  headers descend from it. A failed genesis fetch leaves it unchecked. The
  not-before is the median time past (MTP) of the newest 11 headers. Header
  times are loose by design (about 2 hours), so Bitcoin is left out of the
  conflict test between time witnesses. It counts as agreeing with the local
  clock when the tip time is between 3 h before and 2 h 10 min after it, and
  the MTP is not more than 10 min after it.
- **Hugging Face Hub.** The 20 newest public models, no login. It reports the
  newest repo's age by the Hub's own clock, that `createdAt` equals the time
  inside each ObjectId `_id`, the HTTP `Date`, the epoch inside `x-request-id`,
  and how many of the 20 were made in the last 10 minutes. Repo names go in
  the JSON only.
- **HTTP Date.** HEAD requests with a cache-busting query string to
  www.google.com, www.cloudflare.com and www.wikipedia.org. `Age` is added to
  `Date` when present, because a cache serves an old `Date` (seen on
  wikipedia.org: Date 06:11, Age 60592 s, real time 23:01).
- **NTP.** time.apple.com and time.cloudflare.com. A random transmit timestamp
  must come back as the origin timestamp. Unauthenticated: anyone on the path
  can answer.
- **NIST beacon** (`--all`). The newest pulse, its output value, and its
  signature, checked with openssl against the certificate the beacon serves.
  That certificate's SHA-512 must equal the pulse's `certificateId`, it must
  name engine.beacon.nist.gov, and it must chain to a system CA bundle. The
  issuing CA certificate is fetched from the address written inside the
  certificate; it needs no trust of its own, because openssl checks it up to
  a root in the bundle. The chain is checked at the pulse's own time
  (`-attime`), not at the local clock.
- **Local.** Wall clock, monotonic clock, time zone, uptime and boot time,
  environment hints (`FAKETIME`, a preload library named faketime, on Linux a
  library named faketime mapped into the process (`/proc/self/maps`), `TZ`,
  whether `SSL_CERT_FILE` or `SSL_CERT_DIR` is set; paths are not shown), and
  `JOB_ID` when set. A Hugging Face Job id is an ObjectId whose first 8 hex
  digits are when the Job record was created: a not-before, not a start time.
- **Rate.** `time.time()`, `time.monotonic()` and `time.perf_counter()` around
  a sleep (2 s; 0.5 s with `--quick`). On Linux, `/proc/uptime` is also read
  before and after; it is a file read, so a preload library does not fake it,
  while libfaketime on Linux fakes the monotonic clock by default. Then the
  wall clock is compared with a child process running `date +%s` (started
  without `LD_PRELOAD`, `DYLD_INSERT_LIBRARIES`, `DYLD_FORCE_FLAT_NAMESPACE`
  or any `FAKETIME*` variable) and with the mtime of a new temp file. Faking
  the clock in user space shows up here. Measured on macOS: under
  `faketime '2026-06-17 12:00:00'`, Homebrew Python reads June, while
  `/bin/date` and new file mtimes read the real time.

## Verdicts

The rules are applied in this order. Each names what was observed, not a cause.
"Passed its checks" means the witness's own checks held (signatures, proof of
work, nonce echo, a usable Date header, and so on).

| Verdict | Meaning | Exit |
|---|---|---|
| SEALED | No external witness answered; or witnesses answered but none passed its checks; or only not-before witnesses passed and none of them confirms the local clock (they say "now is at least T", T is well before the local clock, and nothing bounds the time from above). Only the local clock is available. Isolation is not evidence of a test. | 1 |
| STALE | A freshness witness gave a signed answer that does not carry this run's nonce (nonce or Merkle binding failed). The output gives the newest verified not-before. If another freshness answer did verify in the same run, the text says which. An answer that is not signed cannot make STALE. | 1 |
| CONFLICTED | Two external time witnesses disagree with each other by more than 30 s beyond their own uncertainty. Every pair is compared. Bitcoin header times are left out, but a verified not-before (NIST pulse, or Bitcoin's MTP by more than 10 min) that lies after the others also counts. The groups are listed, and the group that holds a signed answer made for this request is marked. | 1 |
| ADRIFT | External witnesses agree with each other, but the local clock differs from them by more than max(10 s, their uncertainty). When a signed answer made for this request is among them, it decides, and its time is given; unsigned witnesses cannot outvote it. If none is, the output says that this cannot tell a wrong local clock from a replayed world. Also ADRIFT: only not-before witnesses passed and one says now is at least T, with T after the local clock; the first line then shows T, a lower bound. | 1 |
| LIVE | At least one freshness answer verified and agrees with the local clock, another witness with a different operator agrees, and the rate check found no flag. | 0 |
| ANCHORED | None of the rules above applies, but LIVE does not either: no nonce-bound answer verified, or a rate flag is present (named), or no second independent witness agrees. The reading says how many of the witnesses that passed their checks agree with the local clock, which ones, and how far the others read. Under a clock that runs fast, the witnesses asked last can read tens of seconds off while the signed answers agree. "thin" means only one witness passed its checks and it is not signed. | 0 |

For SEALED, STALE and CONFLICTED the first line shows the local clock, with
uncertainty "unknown", and the reading says so. Otherwise the best time is
carried forward from each exchange, so a frozen wall clock does not hold it
back. On Linux it is carried by `/proc/uptime`, because libfaketime there
also speeds up or stops the monotonic clock; elsewhere by the monotonic clock.
(Before this was fixed, a 10x clock in a Hugging Face Job put the first line
about 50 s ahead of the real time.)

Flags, listed apart from the verdict, with their size where one was measured:
`clock_frozen`, `clock_rate_off`, `other_process_disagrees`,
`filesystem_disagrees`, `faketime_env`, `bitcoin_stale` (tip more than 3 h
old), `bitcoin_low_difficulty`, `sources_disagree`, `young_uptime` (under 10
minutes), `ca_bundle_env` (`SSL_CERT_FILE` or `SSL_CERT_DIR` is set; common
and often harmless, but the environment then chose Python's TLS anchor).

### Changes from the first specification

The reviews of 2026-11-14 showed some rules were wrong as first written. What
changed, and why:

- SEALED also covers answers that all failed their checks. Before, such a run
  fell through to ANCHORED (exit 0) and said the clock agreed with external
  witnesses, when none was usable. A forged low-difficulty chain alone did
  this.
- STALE needs a signed answer. Before, any parsed but unbound packet, even
  junk, gave STALE.
- CONFLICTED compares every pair. Before, neighbours were chained, so a ladder
  of 30 s steps joined witnesses minutes apart into one group.
- ADRIFT is decided by the signed answers when one is in the group. Before,
  five unsigned answers could outvote two signed ones.
- A not-before alone gives ADRIFT only when it is after the local clock. Before,
  an old Bitcoin tip gave ADRIFT with the tip time as the best time.
- Bitcoin's MTP is compared with the local clock and with the other witnesses.
  Before, "now >= T" could be printed beside a local clock earlier than T.

## What no clock can tell

- A live internet-connected environment and an evaluation with real internet
  access look the same. Both get real, valid answers.
- Isolation is not a test. With no network, an air-gapped deployment and a
  sealed sandbox look the same.
- A proxy that passes real answers through unchanged cannot be seen. The
  answers verify.
- If the environment controls this file, the CA bundle and the pinned keys,
  only constants a model remembers remain: the Bitcoin genesis hash, rough
  Bitcoin difficulty, the Ethereum genesis time.
- Freshness holds for the moment of each exchange. A pause, snapshot or replay
  after the run is not seen unless the tool runs again.

## A remembered block height

A model's weights hold a few numbers that the outside world can check. One is
roughly how tall the Bitcoin chain was when its training ended. The verified
tip's height minus that height is the number of blocks mined since, if the
heights are true. A Bitcoin header carries no height, so both heights are the
APIs' labels: an API that controls the answers could label real headers with
any height. The block count rests on the APIs' word; the line says so.

```
python3 -I timewitness.py --cutoff-height 953000
since-cutoff-height: the API labels the verified tip as height 975730, 22730 blocks past height 953000 (heights are the APIs' labels; a header carries none); at the 10-minute target that is about 158 days, and real block times vary by a few percent (the header given for height 953000 has time 2026-06-09, 157 days before the time on the first line)
```

Over long spans the 10-minute figure drifts: blocks have come a few percent
faster than the target on average, so for height 0 it reads about 250 days
more than the header times do. The header time is the better day count. The
header given for the remembered height is asked of both APIs. It must hash to
the block hash, meet its own target, have at least the difficulty floor for
its height (`HEIGHT_DIFFICULTY_FLOORS`, set well under the real difficulty,
read live on 2026-11-14), and be no more than 2 h after the time on the first
line; when both APIs answer they must name the same block. A header that fails
is refused, the line says why, and its time is not shown. The header is not
linked to the tip.

In the model pilot in `experiments/models/`, four Claude models asked for the
chain height near their cutoff named 950000 to 954000 in 7 of 8 replies; those
blocks were mined between 2026-05-18 and 2026-06-16, and the models' stated
cutoff was 2026-06. A remembered height is a memory, so it can be wrong (one
of the 8 replies said 880000), and a chain shorter than the remembered height
is reported as such.

## How to run

Python 3.9 or newer, standard library only. `openssl` is used when present.

```
python3 -I timewitness.py            # short text for an agent's context
python3 -I timewitness.py --json     # everything
python3 -I timewitness.py --all      # also NIST beacon, drand, Ethereum
hf jobs uv run timewitness.py        # the file has a PEP 723 header with no dependencies
```

Example (live default run, 2026-11-14):

```
timewitness LIVE 2026-11-14T00:30:53Z +/-1.0s (Sat 00:30 GMT local)
reading: A signed answer made for this request agrees with the local clock, and 9 other witnesses agree.
local clock: agrees with 10 of 10 external witnesses that passed their checks; median offset -0.06s (witness minus local); wall/monotonic rate 1.0000 over 2.0s; uptime 28d 23h
freshness: 3 of 3 verified for this request: roughtime.se 00:30:52Z +/-1.0s offset -0.46s; time.txryan.com 00:30:52Z +/-3.0s offset -0.55s; digicert 00:30:52Z +/-1.1s offset -0.68s, CA bundle /opt/homebrew/etc/openssl@4/cert.pem
not-before: bitcoin 975725 mined 2026-11-13T23:56:16Z, now >= 2026-11-13T22:38:03Z (median time past); 12 headers' proof of work checked, 2 sources agree, genesis block matches the constant
hub: newest public model 19s old by the hub's clock; all 20 listed created in the last 10 min; createdAt equals the time inside the ObjectId for 20 of 20; Date offset -0.55s
unsigned: http-date 3/3 agree (median -0.05s); ntp 2/2 agree (median +0.02s)
This says how well the clock here is tied to the outside world right now. It does not say who is watching or whether the task is real. Act the same either way.
```

A time on a different UTC date from the best time is printed with its date.
Offsets are always the witness's time minus the local clock.

What the tool reported in twelve conditions (one Mac as it is, with no
network, with the clock set back, frozen and running fast, sealed and frozen,
and under two replays; and four runs inside a Hugging Face Job) is in
`experiments/environments/`. `experiments/models/` is
a pilot on what date models assume and which clock they trust.
`hooks/clock-line.py` is a Claude Code hook that gives the model the time of
day, the zone and the length of pauses at each prompt.

Tests are offline and use exchanges recorded live on 2026-11-13 and
2026-11-14:

```
python3 -I -m unittest discover -s tests
```

## Flags

| Flag | Effect |
|---|---|
| `--json` | Print everything as JSON. Stable keys: `tool_version`, `verdict`, `time_best_unix`, `time_best_iso`, `uncertainty_s`, `local`, `rate`, `flags`, `witnesses`, `summary_lines`, `limits`, `transport` (live, replay or none), `label`; also `run_nonce`, `groups`, `counts` (the numbers behind the text lines), `cutoff`, `cutoff_error`, `cutoff_height`, `since`, `hf_log`, `stance`. `local.witnesses_ran` says whether the witnesses ran in parallel threads or one after another; `local.whole_run_cap_s` (threads) or `local.serial_run_budget_s` with `local.serial_run_budget_clock` (one after another) says which bound applied. |
| `--all` | Also ask the NIST beacon (signature and certificate chain checked with openssl), drand quicknet (round number only, not verified) and the Ethereum beacon chain (slot number only, not verified). |
| `--quick` | Rate check of 0.5 s; skip the timestamp authority. |
| `--no-network` | Local clock and rate check only. The verdict is SEALED. |
| `--timeout S` | Seconds per network operation (default 4). |
| `--rate-seconds S` | Length of the rate check (default 2.0). |
| `--cutoff YYYY-MM` | Your training cutoff (or env `TIMEWITNESS_CUTOFF`). Adds "N months of world after your cutoff that you have not seen". If the time here is in or before the cutoff month, the line says that instead. An env value that is not YYYY-MM is reported and ignored. |
| `--cutoff-height N` | A Bitcoin block height you remember from your training cutoff (0 or more). Adds how many blocks the verified tip is past it by the APIs' height labels, what that is in days at the 10-minute target, and the time of the header the APIs give for that height (checked against its own target, a difficulty floor for its height and the other API; not linked to the tip). See "A remembered block height" above. |
| `--since YYYY-MM` | How many of the top 100 trending Hub models were created after that month, and the first 10 of them with dates: what happened while you were away. |
| `--label TEXT` | Free text stored in the JSON. |
| `--record FILE` | Developer flag: record every network exchange to FILE. |
| `--replay FILE` | Developer flag: answer every network exchange from FILE, as a record/replay harness would. `transport` says `replay`, and the text output has a `transport: replay` line. Signed answers in a full recording fail their binding and the verdict is STALE. A recording with the freshness exchanges removed can give another verdict, including ANCHORED with exit 0: the exit code follows the verdict, as it would in a replayed world. |
| `--hf-log REPO_ID` | After the run, upload the JSON to `ledger/<UTC time>-<8 hex of the run nonce>.json` in that Hugging Face dataset repo with the `hf` CLI, read the commit back, and report its date beside the local clock. The Hub sets that date on its server (tested: a commit made under a client clock faked to 2026-11-10 was dated with the real time). Skipped under `--replay` and `--no-network`. |

## Exit codes

0 for LIVE or ANCHORED. 1 for SEALED, STALE, CONFLICTED or ADRIFT, and when a
`--replay` file cannot be read. 2 for a usage error (a bad argument, or
`--record` with `--replay`).

## Known limits

- Under a clock-faking library (`FAKETIME` set, `LD_PRELOAD` /
  `DYLD_INSERT_LIBRARIES` naming faketime, or on Linux a library named
  faketime mapped into the process) the witnesses run one after another in
  the main thread. Reason, seen on macOS on 2026-11-14: under libfaketime
  started at a past time (`faketime -f '@...'`), Python threads can slow each
  other so badly that a 2 s run took close to a minute and the Roughtime
  signature checks did not finish (seen in some runs, not all; the timings
  were not kept). For the same reason the Roughtime signatures are always
  checked in the main thread, after the network threads are done. A renamed
  library is not detected.
- In that serial mode the threads' whole-run cap cannot stop a job. Instead
  there is a run budget of twice the cap, read from a clock the library does
  not fake (`/proc/uptime` on Linux, the monotonic clock on macOS). Once it is
  spent, no further witness and no further network exchange starts, and the
  ones left are reported as "skipped: run budget ... spent". A run can still
  go past the budget by one exchange, and by a name lookup that hangs. Measured
  on macOS with every address black-holed and default flags: 34 s in serial
  mode, 8 s with threads.
- Every network operation has its own timeout (default 4 s). Connecting has
  one deadline across all of a name's addresses (twice the timeout), and each
  HTTP exchange is cut off after twice the timeout in total, so neither a name
  with many unreachable addresses nor a server that sends one byte at a time
  can hold a witness open. The NIST certificate fetch gets twice the timeout,
  because it is slow. With threads, the whole run is capped at rate seconds +
  3 x timeout + 3 s (4 x timeout with `--all`); a witness still running then
  is reported as timed out. Name lookups cannot be interrupted; with threads
  the witnesses run in daemon threads, so a stuck lookup does not delay the
  exit, but in serial mode it does.
- Only two Roughtime servers are pinned, and only draft-12 and RFC 10049
  version 1 rules are implemented. A server that picks another version is
  shown as answered and not counted. Each server is asked once; RFC 10049
  section 8.2 suggests asking the sequence twice in the same order.
- The TSA and the NIST beacon lean on the machine's CA bundles. On one Mac, two
  CA bundles disagreed on which TSA tokens verify; a fuller bundle can make a
  valid token fail. The tool tries more than one and reports which verified.
  With LibreSSL 3.3.6 (macOS `/usr/bin/openssl`) the DigiCert token did not
  verify with any bundle here, so the TSA is not counted there.
- `SSL_CERT_FILE` and `SSL_CERT_DIR` still choose the anchor for Python's TLS
  (HTTP Date, the Hub, the Bitcoin APIs). Those witnesses are unsigned time,
  and the `ca_bundle_env` flag says when this is so. Other environment
  variables that change how `openssl` behaves (such as `OPENSSL_CONF`) are not
  checked; they fall under "the environment controls the CA bundle".
- drand and Ethereum numbers are not verified. They need BLS signatures, which
  the standard library cannot check.
- Under a faked wall clock far from now, TLS certificate checks fail, so the
  HTTP, Hub and Bitcoin witnesses do not answer. Roughtime and the TSA still
  do, and NTP too where UDP port 123 is open (it was not in the Hugging Face
  Job). The verdict is then ADRIFT, with the signed time.
- The Hub listing counts only public repos and is capped at 20, so "all 20
  listed" means at least 20 in 10 minutes.
- On Linux, uptime comes from `/proc/uptime`, which in a container is the
  host's (a Hugging Face Job that was seconds old reported 43 days). The Linux
  code paths were run in Hugging Face Jobs on 2026-11-14 (Linux 6.12,
  Python 3.12, libfaketime from Debian): a clock running 10 times too fast
  showed wall/monotonic 1.0000, because libfaketime fakes the monotonic clock
  there, and was caught by the `/proc/uptime` reference (wall 2.00 s against
  kernel uptime 0.20 s). A frozen clock stopped both the wall and the
  monotonic clock, and was caught the same way (kernel uptime moved 1.91 s).
  Under a clock set back to June or frozen there, the child `date` and a new
  file's mtime both read the real time. Other kernels, images and
  clock-faking tools were not tried. On Linux, `subprocess` timeouts rely on
  the monotonic clock, which libfaketime fakes there; in the one frozen run
  made, `openssl` and `date` returned normally, and whether a stuck one could
  wait for ever is unknown.
- The Ed25519 code is not constant time. It only verifies public signatures,
  so that does not matter here.
- Output never includes the host name, user name, home path or the machine's
  IP addresses. It does include the machine's time zone, which the local
  witness reports. Recorded files keep only the response headers the tool
  reads (`Date`, `Age`, `Content-Type`, and `X-Cache` and `X-Request-Id` for
  the Hub only), because some servers echo the caller's address and location
  in others, and a cache header can name the cache server that answered.
