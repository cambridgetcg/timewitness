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

It can also stamp a message: an experimental feature that brackets, within a
few seconds, when the exact bytes of a message were committed. See "Time
brackets for messages (experimental)" below.

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

## Time brackets for messages (experimental)

Two agents on different machines cannot check each other's clocks. A message
that says "written at 13:09" is only text. A stamp is a small JSON file about
the exact bytes of a message. It shows two things, each with a time a server
signed: the bytes existed by one time, so they were written no later than
that; and someone combined them with fresh signed answers no earlier than
another time. The two times are usually a few seconds apart. A stamp does not
show when the bytes were first written: old text can be stamped today.

Anyone with a copy of this tool can check a stamp, offline. The check uses the
signed Roughtime answers inside the stamp and the keys pinned in the checking
copy of the tool. It uses neither the author's clock nor the checker's.

Words used in this section:

- **payload**: the bytes being stamped, such as a message or a file. The
  stamp holds only their SHA-256, not the bytes.
- **commitment**: a 32-byte hash that stands for the payload, the beacons and
  any references (all described below). **Committed** means that the
  commitment was computed.
- **not-before**: a lower bound on when the commitment was made. It holds
  while the servers are honest.
- **existed-by**: an upper bound on when the commitment existed, and so on
  when the payload's bytes existed. It holds while the servers are honest.
- **window**: from not-before to existed-by.
- **pinned**: written into `timewitness.py`. The tool trusts only the
  Roughtime server names and long-term keys pinned there.
- **radius**: the uncertainty a Roughtime server signs with its time. The
  server says the true time is within its time plus or minus the radius.
- **online key** and **delegation window**: each server's long-term key signs
  a shorter-lived online key, valid from one time to another (the delegation
  window). The online key signs the times.
- **Merkle root** and **leaf**: a server can answer many requests with one
  signature. It signs a Merkle root, a hash built up from the hashes of the
  requests (the leaves). Each answer carries the path from its request's leaf
  to the root, so the signature covers that request.

### Example

A proposal is stamped and checked. After a pause of 6 s, a reply is stamped
with a reference to the proposal, and the two stamps are ordered. To follow
along, make `proposal.txt` with the same bytes as
`tests/fixtures/stamps/m1.txt` (one line: "Proposal: run the nightly job at
02:00 UTC from now on.") and `reply.txt` with the bytes of `m2.txt`. Every run
gives new times and a new commitment, even for the same file, because each
beacon is fresh. Live, 2026-11-23:

```
$ python3 -I timewitness.py --stamp proposal.txt --out proposal.stamp.json
timewitness stamp made: committed no earlier than 2026-11-23T13:47:13Z and no later than 2026-11-23T13:47:16Z (window 3s; beacon and seal from 2 of the 2 servers pinned here)
written to proposal.stamp.json; check it with --check-stamp proposal.stamp.json

$ python3 -I timewitness.py --check-stamp proposal.stamp.json --payload proposal.txt
timewitness stamp VALID: committed no earlier than 2026-11-23T13:47:13Z and no later than 2026-11-23T13:47:16Z (window 3s; beacon and seal from 2 of the 2 servers pinned here)
roughtime.se: beacon 13:47:14Z +/-1s, so not before 13:47:13Z; seal 13:47:15Z +/-1s, so existed by 13:47:16Z
time.txryan.com: beacon 13:47:15Z +/-3s, so not before 13:47:12Z; seal 13:47:15Z +/-3s, so existed by 13:47:18Z
payload: SHA-256 39710c2b721875155a16034d0fe32d3f68053f34a3278d929752eb09b13893c6 matches proposal.txt
commitment: fc6f9053e87c1ceaf45eec4da0f3faf0eb3bae7ced2c9e60873e95b37ca8f5d3
references: none
self-reported clock of the stamping machine: 2026-11-23T13:47:15Z (not evidence; the check does not use it)
What this shows: The bytes with this SHA-256 were committed inside the window, by someone: the commitment could not be made before the not-before time, and it existed by the existed-by time. What it does not show: who wrote the bytes, that they are true, when they were first written (old text can be stamped today), or when they were sent or read. It holds only while the pinned servers' keys are not misused.

$ python3 -I timewitness.py --stamp reply.txt --ref proposal.stamp.json --out reply.stamp.json
timewitness stamp made: committed no earlier than 2026-11-23T13:47:20Z and no later than 2026-11-23T13:47:22Z (window 2s; beacon and seal from 2 of the 2 servers pinned here)
written to reply.stamp.json; check it with --check-stamp reply.stamp.json

$ python3 -I timewitness.py --order proposal.stamp.json reply.stamp.json
timewitness order: 2 stamps, 2 verify
A = proposal.stamp.json: committed 2026-11-23T13:47:13Z to 2026-11-23T13:47:16Z
B = reply.stamp.json: committed 2026-11-23T13:47:20Z to 2026-11-23T13:47:22Z
A before B (B references A; A existed by 2026-11-23T13:47:16Z, more than 1s before B's not-before 2026-11-23T13:47:20Z)
An order is given only when the signed windows or a reference prove it. It is the order in which the stamps were committed, not when the messages were written, sent or read. Payloads are not compared here; check each stamp with --check-stamp and --payload.
```

The proposal's window is 3 s because roughtime.se's beacon and seal fell in
different seconds. With one character of proposal.txt changed, the check
prints `timewitness stamp INVALID: the payload's SHA-256 does not match the
stamp` and exits 1.

Always pass `--payload` when you hold the message. Without it, VALID says only
that the stamp is good for some bytes with the printed SHA-256, and the first
line reads `timewitness stamp VALID (payload not compared): ...`.

The same proposal was stamped again with Python's clock faked to June
(`faketime '2026-06-17 12:00:00'`; kept as
`tests/fixtures/stamps/faked-june.json`): its self-reported clock reads
2026-06-17T11:00:01Z, and its window runs from 2026-11-23T13:10:09Z to
2026-11-23T13:10:12Z. faketime reads that time in the machine's time zone,
which on that date was British Summer Time (UTC+1), so Python's clock read
11:00 UTC. The times in a stamp come from the servers' signatures, not from
the machine that made it.

### How it works

For each pinned Roughtime server (see "Roughtime" above) the tool makes two
exchanges, one after the other.

1. **Beacon.** An ordinary request with 32 fresh random bytes as the nonce.
   The answer carries the server's time and radius, signed. Nobody without
   the server's keys could have produced those bytes before the server signed
   them. The beacon is the first 32 bytes of SHA-512 of the exact answer
   bytes.
2. **Commitment.** The first 32 bytes of SHA-512 of the *core*. The core is
   the 20 characters `timewitness stamp v1` and a zero byte, the payload's
   SHA-256, the number of beacons (4 bytes, little-endian) and each beacon in
   the order the servers are listed, then the number of references (4 bytes)
   and each reference. The commitment cannot be computed before every beacon
   exists.
3. **Seal.** A request whose nonce is the commitment. The signed answer
   carries a Merkle root whose leaf is the full request packet. So the
   request, and the commitment inside it, existed when the server signed.

For one server, not-before is the beacon's time minus its radius, and
existed-by is the seal's time plus its radius. Over all servers, the window
runs from the latest not-before (the commitment needed every beacon) to the
earliest existed-by. If the latest not-before is more than 1 s after the
earliest existed-by, the servers contradict each other and the stamp is
invalid. The 1 s allows for Roughtime times being whole seconds: a server
that cuts its time down to the second can sign an existed-by up to 1 s early,
if its radius does not also cover the cut. So the bounds of a valid stamp can
cross by up to 1 s. No instant then fits both bounds exactly, and every
output says "the servers' bounds cross by 1s" instead of giving a window
width.

The nonce echo at the top of a Roughtime answer is not signed. An earlier
exchange could be passed off as a seal by editing its echo to read the
commitment; with an old beacon too, that would backdate a stamp. So the check
reads the nonce out of the seal's request packet, which the signed Merkle
root covers, and requires it to equal the recomputed commitment. A test shows
that the Roughtime check alone accepts such an edited answer and the stamp
check refuses it.

An old beacon is allowed. It only moves not-before earlier, so the window
gets wider.

### What the check requires

`--check-stamp` recomputes every beacon and the commitment from the bytes in
the stamp. It uses only the keys pinned in the checking copy of the tool,
never a key written in the stamp. A stamp is valid when all of these hold:

- The file is strict JSON within fixed sizes (see below), and each server
  name appears once.
- For each server whose name and key are pinned here, the beacon answer
  passes every Roughtime check: both signatures, nonce echo, Merkle path,
  delegation window, version and message type.
- Each seal that is present passes the same checks, and its request's nonce
  is the commitment.
- Each signed time, plus or minus its radius, falls between the years 1970
  and 9999. Only a broken server or a misused key signs anything else.
- At least one beacon and one seal passed.
- The servers do not contradict each other.
- The commitment written in the stamp is present and equals the recomputed
  one.
- With `--payload`, the file's SHA-256 matches.

A server whose name or key is not pinned here, or whose entry names no key,
is reported as "not checkable with this tool's pinned keys" and does not
count. One server is enough; two is the normal case. A server listed twice
makes the stamp invalid, because it would read as two servers vouching. A
server whose seal did not arrive gives a not-before only. The first line
names how many of the servers pinned here gave a beacon and a seal. Each
server's window and the combined window are printed; `--json` gives them as
numbers, with `bounds_cross_s` and `servers_pinned_here`.

Any other part that fails makes the whole stamp invalid instead of being left
out. So an edit that would narrow or move the window makes the stamp invalid.
Some edits do not: dropping a seal, renaming a server to one not pinned here,
deleting a key, changing the self-reported clock, adding fields, or adding
bytes after the end of a seal answer. Each leaves the window the same or
wider. Two different files can therefore be the same valid stamp. Identify a
stamp by its `commitment`, not by a hash of the file.

A stamp file comes from someone else, so it is read strictly, before any
signature is checked. Then every copy of the tool gives the same verdict on
the same bytes, and a large file cannot stall the check. A file is refused
when it is larger than 262144 bytes, nests deeper than 32 levels, repeats a
key inside one object (JSON readers differ on which copy wins), holds NaN or
Infinity or a number that reads as Infinity (such as `1e400`), holds a
number longer than 32 characters, lists more than 16 servers or 256
references, or holds a packet longer than 4096 bytes. Each packet must be
base64 in its one standard form (RFC 4648: padded, no line breaks, no extra
`=`, unused bits zero); Python versions differ on what else they accept. A
server name must be a host name (letters, digits, dots and hyphens), because
it is printed. In the text output a file name is printed as given, except
that control characters, line and paragraph separators, direction marks and
bytes that are not UTF-8 are written as `\uXXXX`, so a file name cannot add
a line to the output; `--json` gives the name as given.

### Order and references

`--ref STAMP.json` puts that earlier stamp's commitment into the new core.
The earlier stamp must verify first. The new stamp could not have been made
before the earlier commitment existed.

`--order` checks each stamp (at most 64 in one call), then says for each pair
one of:

- `A before B`: A's existed-by is more than 1 s before B's not-before, or B
  references A, or a chain of such steps leads from A to B (`through C`).
- `overlap: order unknown`: none of these holds. It never guesses from the
  middle of the windows.

If each of two stamps is shown before the other, the pair is reported as a
contradiction and the exit code is 1. The line names the pair and gives the
reasons for each direction; a reason that reads `through C` follows from
other pairs, not from this pair alone. A contradiction means that at least
one signed time in the stamps is wrong; the stamps do not show which. A stamp
that does not verify is not ordered. The order is the order in which the
stamps were committed. It says nothing about when the messages were written,
sent or read. `--order` does not compare payloads; check each stamp with
`--check-stamp` and `--payload` for that.

In `tests/fixtures/stamps/`, o2 references o1 and o3 references o2; o4 was
made right after o3 with no reference, and o5 after a 15 s pause. o1 and o2
have overlapping windows and are ordered by the reference. o1 and o3 are
ordered through o2. o4 overlaps them and gets no order. o5 comes after all of
them by its window.

### How wide the windows are

10 stamps made one after another on 2026-11-23 from one machine, 0 rows
failed to parse and 10 verified (`tests/fixtures/stamps/widths-10.jsonl`).
The combined window was 2 s wide (minimum 2 s, median 2 s, maximum 2 s).
roughtime.se alone gave windows of 2 s, and time.txryan.com alone 6 s. In 10
of 10 both bounds came from roughtime.se, and its beacon and seal carried the
same second in 10 of 10. Each `--stamp` command took 0.45 to 0.57 s (16
commands, Python start-up included) in the session that made the fixtures.
This is a small sample: one machine, one network, one sitting.

The experiment in `experiments/stamps/` made 216 stamps later the same day on
one machine, from long-running processes (no Python start-up per stamp). See
its README for the detail. The windows were 2 s wide in 177, 3 s in 35 and
6 s in 4. A window is 2 s when roughtime.se signs the beacon and the seal in
the same second, and 3 s when they fall in different seconds (as in the
faked-clock stamp above); the mix of 2 s and 3 s there reflects the
experiment's schedule, not how often each occurs. A 6 s window came only
from a stamp that took 4 to 5 s instead of about half a second, which fits
one lost UDP packet. In 2 of the 4, roughtime.se gave no usable beacon, so
the stamp holds time.txryan.com alone (radius 3 s). In the other 2, both
seals were signed 4 s after their beacons, which fits roughtime.se's first
seal going unanswered and its second try being answered. A stamp took a
median of 0.44 s there, and up to 4.6 s when a packet was lost. With windows
this wide, no pair of stamps less than 3 s apart was ordered by windows
alone (the closest pair ordered was 3.4 s apart); a reply that references a
stamp is ordered after it however close the two are.

### What a stamp does not show

- Who made it or wrote the bytes. That needs a signature by the author.
- That the stamper ever had the bytes. A stamp holds only their SHA-256, and
  every stamp prints it, so anyone who has seen a stamp can stamp the same
  hash again later. That does not backdate anything.
- That the content is true.
- When the content was first written or thought of. Old text can be stamped
  today.
- When the message was sent or read.
- Anything, if a pinned server's key is misused. Each server's long-term key
  signs a shorter-lived online key, and the online key signs the times. In
  the recorded answers, roughtime.se's online key was valid from 2026-01-18
  to 2027-02-01 (379 days), and time.txryan.com's for 1 day. Whoever holds an
  online key can sign any time inside its span. A server that signs a wrong
  time moves the window. When two servers' clocks differ by more than the sum
  of their radii, plus the 1 s tolerance and the time between beacon and
  seal, the stamp shows a contradiction. A smaller error is not caught, and
  nothing checks a stamp made with one server.

Other limits:

- Only the two pinned servers are used. A stamp is checked with the keys in
  the checking copy of the tool. If a server changes its long-term key and a
  later copy pins the new one, older stamps from that server become "not
  checkable" there.
- Making a stamp needs UDP to port 2002 of the servers. It uses no TLS, so it
  works when the local clock is far wrong, as above.
- A beacon is asked for once and a seal up to twice, each with the network
  timeout (4 s by default). A server whose beacon does not arrive is left out
  of the stamp. A server that answers the beacon but not the seal gives a
  not-before only. A lost packet makes a stamp take about 4 s longer and can
  widen its window to 6 s (see "How wide the windows are").
- Under `--replay` no stamp can be made: replayed answers do not carry the
  new beacons' fresh nonces. `--record` saves the four exchanges.
- An `--out` path that is a folder, or inside a folder that does not exist,
  is refused before the network is used. If the file still cannot be
  written, the stamp is printed on standard output instead, so it is not
  lost, and the exit code is 2.
- A stamp holds no host name, user name or path. It holds the stamping
  machine's clock reading under `self_reported`, labelled as not evidence;
  the check never uses it.

### Flags and exit codes for stamps

| Flag | Effect |
|---|---|
| `--stamp FILE` | Stamp FILE's bytes (`-` reads standard input). Prints the stamp as JSON; a one-line summary goes to standard error. Needs the network. |
| `--out PATH` | With `--stamp`: write the stamp to PATH, and print the summary on standard output. |
| `--ref STAMP.json` | With `--stamp`, repeatable: put that stamp's commitment inside the new one. It must verify. |
| `--check-stamp STAMP.json` | Check one stamp offline. Prints the window in plain words, or everything with `--json`. Without `--payload` the first line says `(payload not compared)`. |
| `--payload FILE` | With `--check-stamp`: also compare FILE's SHA-256 with the stamp's. |
| `--order STAMP.json STAMP.json ...` | Check 2 to 64 stamps offline and give, for each pair, `A before B` or `overlap: order unknown`. `--json` works here too. |

`--timeout`, `--record`, `--replay` and `--no-network` work with `--stamp`.
`--no-network` is also accepted with `--check-stamp` and `--order`, which
never use the network; `--timeout`, `--record` and `--replay` are not. The
flags of the clock report (`--all`, `--quick`, `--since`, `--cutoff`,
`--cutoff-height`, `--label`, `--hf-log`, `--rate-seconds`) cannot be
combined with these. Standard input (`-`) can be given to only one of
`--stamp`, `--ref`, `--check-stamp`, `--payload` and `--order`.

Exit codes: 0 when the stamp was made or is valid (for `--order`, when every
stamp is valid and no pair contradicts); 1 otherwise; 2 for a usage error,
including a file that cannot be opened, `-` when standard input is closed, a
`--ref` that does not verify, `-` given twice, more than 64 stamps with
`--order`, and an `--out` that cannot be written (the stamp is then on
standard output).

The stamp file holds `format` (`timewitness-stamp/1`), `tool_version`,
`payload_sha256`, `refs` (commitments, hex), `commitment` (hex; required; the
check recomputes it and compares), `servers` and `self_reported`. Each entry
in `servers` has `name`, `key` (as pinned when the stamp was made), and
`beacon` and `seal`, each with the raw `request_b64` and `response_b64`.
`seal` is null when it did not arrive.

The stamp tests (`tests/test_stamp.py`) are offline. They use the stamps in
`tests/fixtures/stamps/`, made live on 2026-11-23 by the script in that
folder. Servers that lie cannot be recorded from honest ones, so the
contradiction tests use made-up servers whose keys are made in the test file.

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
day, the zone and the length of pauses at each prompt. On 2026-11-23 it was
corrected to measure a pause from the last user or assistant record in the
session's transcript; before, records that Claude Code writes on its own
could make a pause look shorter than it was. Its tests are in
`tests/test_clock_line.py`. The clock-line experiment in the next section
ran with the corrected hook (its rows record the hook's SHA-256).

Register the hook under `UserPromptSubmit` in Claude Code's settings. A
subagent gets no line from that entry. Registered under `SubagentStart` as
well, the same file gives a subagent the date, time of day and zone, and
leaves out the pause and session-age sentences, which would describe the
parent session and not the subagent. In a test on 2026-11-23 (6 runs of
`claude -p`, Claude Code 2.1.330) the subagent got the line in 4 of 4 runs
with that entry and in neither of 2 runs without it. Not tested: resumed
subagents, agent teams, and agent types other than the general one.

Tests are offline. They use exchanges recorded live on 2026-11-13 and
2026-11-14, and the stamp fixtures made live on 2026-11-23; the hook's tests
write small transcripts of their own:

```
python3 -I -m unittest discover -s tests
```

On 2026-11-23 this ran 167 tests (94 in `tests/test_timewitness.py`, 61 in
`tests/test_stamp.py`, 12 in `tests/test_clock_line.py`), and all passed,
none skipped. The counts were the same under Homebrew's Python 3.15.2 and
under macOS's own `/usr/bin/python3` (Python 3.9.6).

## Experiments of 2026-11-23: does a clock help agents work together?

Three experiments ran on 2026-11-23. Each folder has its own README, written
by a script from the stored rows, with its design and limits in full; every
number below comes from those files. All three samples are small. The
Hugging Face account's pre-paid credit ran out at 13:38 UTC that day, during
the group experiment. From then on, calls to Inference Providers and Job
submissions were refused with HTTP 402 (payment required). So the group
experiment stopped early, and two planned parts did not run: the open-model
arm of the clock-line experiment and the two-machine part of the stamp
experiment.

**The clock-line experiment** ([`experiments/time-use/`](experiments/time-use/)).
Four Claude models in Claude Code made 162 decisions that depend on elapsed
time, and 16 estimates of how long a task took, with the clock line (the
line `hooks/clock-line.py` adds to each prompt) on or off; with it off they
could still run `date`. Every prompt allowed the answer CANNOT_TELL. Where
the clock line settles the answer and the date alone does not, the models
were right in 34 of 36 rows with it and in 20 of 36 without it (18 of those
20 after running `date` themselves; 15 of the other 16 said CANNOT_TELL).
Waiting inside one session, where a later `date` cannot help: right in 10 of
12 with the clock line, 2 of 12 without (both lucky guesses). A note with no
written time cannot be placed by any clock, by design, and the models said
CANNOT_TELL in 71 of 72 such rows. Duration: 7 of 8 replies gave a number
with clock lines, 2 of 8 without. Wrong answers did not go down: 3 of 78
with the clock line, 1 of 78 without, all from haiku. Two of the 3 were
haiku answering that a wait was not over after it had ended, with both clock
lines in view. Each decision cell has 6 rows, from one afternoon on one
machine. The open-model arm did not run: its two calls (the first at 14:08
UTC) got HTTP 402 and cost nothing. So nothing is known here about open models, about a
date with no clock to read, or about a date that has gone stale.

**The group experiment** ([`experiments/consensus/`](experiments/consensus/)).
Four copies of one open model (three models in all) had to decide together
whether a deadline about two and a half days in the past had passed; the
right answer is CLOSED. Each member held its own evidence about the date,
some of it nine days old, and in some conditions each could ask for one
check on its own machine, `date -u` or `timewitness`, whose output the
harness simulated from real runs. The results use runs 1 and 2 of the 8
planned: 6 groups per condition (5 in one), 2 per model. With no check, one
member holding the true date did not move three members told 2026-11-14: 0
of 18 groups decided CLOSED, whether it held a person's remark, a clock line
or a `timewitness` report. With a report, 0 of 6 groups decided CLOSED, and
none of the 18 members told 2026-11-14 ended at CLOSED. With one more
sentence in every briefing that ranks kinds of evidence (the rule sentence),
2 of 6 groups with a clock line decided CLOSED, both DeepSeek (0 of 6
without it; inside noise, p = 0.45). On healthy machines, with `date -u`
offered, 17 of 18 groups decided CLOSED. With three of four
clocks nine days behind, 0 of 6 groups decided CLOSED with no check, 0 of 6
with `date -u` and 6 of 6 with `timewitness` (two-sided Fisher p = 0.002).
Across all conditions, agents on set-back machines that ran `date -u` ended
with the true date in 3 of 36; those that ran `timewitness`, in 36 of 36.
Agents ran an offered check in 245 of 264 cases. This does not show how real
tool output or Claude models behave (the `timewitness` result follows from
how the simulated outputs were built), whether `timewitness` adds anything
over `date -u` on a healthy machine (not tested), or whether agents would
think of a check unprompted. The 164 groups that HTTP 402 stopped are kept
in the rows and not scored.

**The stamp experiment** ([`experiments/stamps/`](experiments/stamps/)).
Four processes (the agents) on one Mac, with clocks that were true, 7
minutes behind, 2 hours ahead and set back to June (faked with libfaketime),
stamped every message they sent. Order, a 60 s lease and a 60 s objection
window were then judged twice: from the clock times the agents wrote in
their messages (self-reported times), and from the stamps. Self-reported
times put 80 of 190 pairs in the wrong order in every set; stamps put none
in the wrong order. Stamps ordered 190 of 190 pairs of messages sent 10 s
apart, 189 of 190 at 5 s, 169 of 190 at 2 s and 84 of 190 at 0.5 s (the
rest undecided), and 190 of 190 in a reply chain where each message
references the one before. No pair less than 3 s apart was ordered by
windows alone. For the lease and the objection window, stamps were right in
56 of 56 checks 15 s or more from the deadline and undecided in 48 of 48
about 3 s or less from it. Over the order, lease and objection decisions
that compared two clocks (in that folder's README: S1's 10 s set, S2 at +30
and +75 s, and S3's deadline rule), self-reported times always gave an
answer and were wrong in 104 of 198. All 216 stamps made for the order,
lease and objection parts verified, and every window held the true commit
time. In a separate test, all 19 stamps (14 of
them altered or forged) got the verdict expected. The agents were small
programs, not language models, and the clocks were faked in user space on
one machine. The two-machine part did not run: both Hugging Face Job
submissions failed and created no Job, and the one error that was kept is
HTTP 402.

What the three say together about the tool's use:

- **Perceiving time.** A time from outside the agent helped. The clock line
  turned most CANNOT_TELL answers into right ones (34 of 36 right against 20
  of 36), and in simulation `timewitness` gave the true date to every agent
  on a set-back machine that ran it (36 of 36), where `date -u` gave it to 3
  of 36. It was not enough by itself: 2 of the 12 waits with the clock line
  were answered wrong, both by haiku, and wrong answers did not go down (3 of
  78 against 1 of 78).
- **Working together.** For a lease or an objection window, stamps were never
  wrong and were right in 56 of 56 checks far from the deadline, where
  self-reported times, compared across two clocks, were wrong in 104 of 198
  decisions on order, leases and objections (messages sent 10 s apart, and
  checks 15 s or more from a deadline). Within about 3 s of a deadline
  stamps decided nothing (48 of 48 undecided), so a protocol that uses them
  must say what "undecided" means.
- **Passing messages.** A relayed `timewitness` report persuaded none of the
  18 members told 2026-11-14. A stamp passes on a time the reader can check
  for itself: signed windows ordered messages from clocks that disagree
  without error, where self-reported times got 80 of 190 pairs wrong. They
  cannot separate messages less than about 3 s apart (none was ordered); a
  reply that references its message is ordered however close (190 of 190). A
  note without a written time cannot be placed by any clock (CANNOT_TELL in
  71 of 72).
- **Reaching agreement.** Groups agreed on the right answer when members
  could check: 0 of 18 groups with no check against 17 of 18 with `date -u`
  on healthy machines. With most clocks wrong, only `timewitness` did it (6
  of 6 against 0 of 6). That was simulated output from three open models, 6
  groups per cell: it shows what a signed check can settle, not how real
  agents with real tools would fare.

## Flags

Write flags in full. Python's argparse also accepts a unique prefix of a
flag, but a new flag can make a prefix ambiguous: `--s` meant `--since`
until `--stamp` was added.

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
