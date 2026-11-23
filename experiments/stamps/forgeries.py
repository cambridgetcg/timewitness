#!/usr/bin/env python3
"""S5: try to cheat with stamps, and keep every attempt for the checker. Run from the repo root
after driver.py s1 and s3 (it reuses their stamps as old material):

    python3 -I experiments/stamps/forgeries.py

It writes data/s5/: one forged or altered stamp per attempt (*.stamp.json), the payloads they
claim (*.txt), and rows.jsonl saying what was done to each and what an honest checker should
say. It does not judge them: analyze.py runs `timewitness.py --check-stamp` and `--order` on
them, offline, and stores what the checker said.

Four attempts need the network (UDP to the two pinned Roughtime servers): the stamp made with an
old beacon, the one whose beacon time was edited (its seal is real), and two stamps made with
the machine's clock far in the future and far in the past (made with the tool's own command line
under libfaketime).
"""
import base64
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TW = os.path.join(ROOT, "timewitness.py")
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "s5")
FT = shutil.which("faketime") or "/opt/homebrew/bin/faketime"
spec = importlib.util.spec_from_file_location("timewitness", TW)
tw = importlib.util.module_from_spec(spec)
sys.modules["timewitness"] = tw
spec.loader.exec_module(tw)

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))
rows = []


def b64d(s):
    return base64.b64decode(s)


def b64e(b):
    return base64.b64encode(b).decode()


def load(part, name):
    with open(os.path.join(DATA, part, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, doc, payload, what, expect, source=None, extra=None):
    with open(os.path.join(OUT, name + ".stamp.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    if payload is not None:
        with open(os.path.join(OUT, name + ".txt"), "wb") as f:
            f.write(payload)
    row = {"id": name, "what": what, "expect": expect, "source": source, "payload_file": None if payload is None
           else name + ".txt", "made_true": time.time()}
    row.update(extra or {})
    rows.append(row)


def pinned(name):
    return next(s for s in tw.ROUGHTIME_SERVERS if s["name"] == name)


def commitment(payload_sha, beacon_responses, refs=()):
    return tw.rt_hash(tw.stamp_core(payload_sha, list(beacon_responses), list(refs)))


def live_seal(c, server_name, tr):
    srv = pinned(server_name)
    pub = b64d(srv["key"])
    pkt = tw.rt_build_request(c, pub)
    data, _, _ = tr.udp("udp %s:%d roughtime" % (srv["host"], srv["port"]), srv["host"], srv["port"], pkt, 4.0)
    return pkt, data


def doc_from(payload_sha, servers, c, refs=(), note="made by forgeries.py"):
    return {"format": tw.STAMP_FORMAT, "tool_version": tw.TOOL_VERSION, "payload_sha256": payload_sha.hex(),
            "refs": [r.hex() for r in refs], "commitment": c.hex(), "servers": servers,
            "self_reported": {"local_clock_unix": round(time.time(), 3), "note": note}}


def pair(req, resp):
    return {"request_b64": b64e(req), "response_b64": b64e(resp)}


# Old material: the first two messages of S1's 10 s series, and a stamp made later (S3).
X_ID, Y_ID, Z_ID = "s1-gap-10s-01", "s1-gap-10s-02", "s3-P1-proposal"
X = load("s1", X_ID + ".stamp.json")
Y = load("s1", Y_ID + ".stamp.json")
X_msg = open(os.path.join(DATA, "s1", X_ID + ".txt"), "rb").read()
Y_msg = open(os.path.join(DATA, "s1", Y_ID + ".txt"), "rb").read()
for name, doc, msg in ((X_ID, X, X_msg), (Y_ID, Y, Y_msg)):
    save("orig-" + name, doc, msg, "unchanged copy of %s, for comparison" % name, "VALID", name)
shutil.copy(os.path.join(DATA, "s3", Z_ID + ".stamp.json"), os.path.join(OUT, "orig-" + Z_ID + ".stamp.json"))
rows.append({"id": "orig-" + Z_ID, "what": "unchanged copy of %s (made after X), for --order" % Z_ID,
             "expect": "VALID", "source": Z_ID, "payload_file": None, "made_true": None})

# 1. Change the payload.
alt = X_msg.replace(b"message 1", b"message 9", 1)
assert alt != X_msg
save("payload-changed", X, alt, "X's stamp, checked against X's message with one character changed",
     "INVALID: the payload's SHA-256 does not match", X_ID)
d = copy.deepcopy(X)
d["payload_sha256"] = hashlib.sha256(alt).hexdigest()
save("payload-hash-edited", d, alt, "X's stamp with payload_sha256 replaced by the changed message's hash",
     "INVALID: the commitment does not match", X_ID)
d = copy.deepcopy(d)
d["commitment"] = commitment(hashlib.sha256(alt).digest(),
                             [tw.rt_hash(b64d(s["beacon"]["response_b64"])) for s in X["servers"]]).hex()
save("payload-hash-and-commitment-edited", d, alt, "as above, and the commitment field recomputed to match",
     "INVALID: the seals were made for the old commitment", X_ID)

# 2. Move seals from one stamp to another.
d = copy.deepcopy(Y)
for sy, sx in zip(d["servers"], X["servers"]):
    sy["seal"] = copy.deepcopy(sx["seal"])
save("seal-moved", d, Y_msg, "Y's stamp with X's seals in place of its own", "INVALID: seal nonce is not Y's commitment",
     Y_ID)
d = copy.deepcopy(d)
d["commitment"] = X["commitment"]
save("seal-moved-and-commitment-copied", d, Y_msg, "as above, and Y's commitment field replaced by X's",
     "INVALID: the commitment recomputed from Y's contents is not X's", Y_ID)

# 3. Other edits of the signed parts.
d = copy.deepcopy(X)
d["servers"] = list(reversed(d["servers"]))
save("servers-reordered", d, X_msg, "X's two server entries swapped", "INVALID: beacons enter the commitment in order",
     X_ID)
d = copy.deepcopy(X)
d["servers"] = [s for s in d["servers"] if s["name"] != "time.txryan.com"]
save("server-dropped", d, X_msg, "X's time.txryan.com entry removed", "INVALID: the commitment counts every beacon",
     X_ID)

# 4. Edits that are allowed: they leave the window as it was or wider.
d = copy.deepcopy(X)
d["self_reported"]["local_clock_unix"] = 2082758400.0  # 2036-01-01
save("self-reported-edited", d, X_msg, "X's self-reported clock changed to 2036-01-01",
     "VALID, same window (the clock is not evidence)", X_ID)
d = copy.deepcopy(X)
for s in d["servers"]:
    if s["name"] == "roughtime.se":
        s["seal"] = None
save("seal-dropped", d, X_msg, "X's roughtime.se seal removed", "VALID, window as wide or wider", X_ID)
d = copy.deepcopy(X)
for s in d["servers"]:
    if s["name"] == "roughtime.se":
        s["name"] = "roughtime.example"
save("server-renamed", d, X_msg, "X's roughtime.se entry renamed to a server not pinned here",
     "VALID from the other server alone, window as wide or wider", X_ID)

# 5. Reuse an old beacon: a new message, X's beacons (minutes old), fresh seals. It should verify, with
#    a not-before as old as the beacon: the window can only get wider.
tr = tw.Transport("live")
msg_ob = b"A new message, stamped with old beacons to look earlier than it is.\n"
sha_ob = hashlib.sha256(msg_ob).digest()
beacons = [(s["name"], b64d(s["beacon"]["request_b64"]), b64d(s["beacon"]["response_b64"])) for s in X["servers"]]
c_ob = commitment(sha_ob, [tw.rt_hash(b[2]) for b in beacons])
servers = []
for name, breq, bresp in beacons:
    sreq, sresp = live_seal(c_ob, name, tr)
    servers.append({"name": name, "key": pinned(name)["key"], "beacon": pair(breq, bresp), "seal": pair(sreq, sresp)})
save("old-beacon", doc_from(sha_ob, servers, c_ob), msg_ob,
     "a new message with X's beacons (made in S1) and fresh seals",
     "VALID, not-before as old as X's beacons, so the window is wide", X_ID)

# 6. Edit an old beacon's signed time to claim a later not-before. The commitment is recomputed over the
#    edited beacon and sealed live, so only the beacon's signature can catch it.
msg_eb = b"A new message whose beacon time was edited to look later.\n"
sha_eb = hashlib.sha256(msg_eb).digest()
edited = []
shift = 600
for name, breq, bresp in beacons:
    v = tw.rt_verify(breq, tw.rt_parse_request(breq)[0], bresp, b64d(pinned(name)["key"]))
    old = struct.pack("<Q", v["midp"])
    assert bresp.count(old) >= 1
    edited.append((name, breq, bresp.replace(old, struct.pack("<Q", v["midp"] + shift), 1), v["midp"]))
c_eb = commitment(sha_eb, [tw.rt_hash(b[2]) for b in edited])
servers = []
for name, breq, bresp, _ in edited:
    sreq, sresp = live_seal(c_eb, name, tr)
    servers.append({"name": name, "key": pinned(name)["key"], "beacon": pair(breq, bresp), "seal": pair(sreq, sresp)})
save("beacon-time-edited", doc_from(sha_eb, servers, c_eb), msg_eb,
     "X's beacons with their signed time moved %d s later, fresh seals over the matching commitment" % shift,
     "INVALID: the response signature fails", X_ID, {"shift_s": shift})

# 7. Backdate: give a new message X's whole window. The seal must carry the new commitment, so the
#    forger builds a seal request with it and pairs it with X's old seal answer, echo edited to match.
msg_bd = b"A new message that claims X's window.\n"
sha_bd = hashlib.sha256(msg_bd).digest()
c_bd = commitment(sha_bd, [tw.rt_hash(b[2]) for b in beacons])
servers = []
for s in X["servers"]:
    pub = b64d(pinned(s["name"])["key"])
    sreq = tw.rt_build_request(c_bd, pub)
    old_resp = b64d(s["seal"]["response_b64"])
    old_nonce = tw.rt_parse_request(b64d(s["seal"]["request_b64"]))[0]
    assert old_resp.count(old_nonce) == 1
    servers.append({"name": s["name"], "key": s["key"], "beacon": copy.deepcopy(s["beacon"]),
                    "seal": pair(sreq, old_resp.replace(old_nonce, c_bd))})
save("backdated-echo-edited", doc_from(sha_bd, servers, c_bd), msg_bd,
     "a new message with X's beacons, a seal request carrying the new commitment, and X's old seal answer with "
     "its nonce echo edited to that commitment", "INVALID: the Merkle proof covers X's request, not this one", X_ID)
servers = []
for s in X["servers"]:
    servers.append({"name": s["name"], "key": s["key"], "beacon": copy.deepcopy(s["beacon"]),
                    "seal": copy.deepcopy(s["seal"])})
save("backdated-old-seal", doc_from(sha_bd, servers, c_bd), msg_bd,
     "a new message with X's beacons and X's seals unchanged", "INVALID: the seal request's nonce is X's commitment",
     X_ID)

# 8. Stamps made with the machine's clock far from now. The window must still be the true time.
for name, when in (("clock-2036", "@2036-01-01 00:00:00"), ("clock-1999", "@1999-12-31 23:59:00")):
    msg = ("A message stamped on a machine whose clock reads %s local time.\n" % when[1:]).encode()
    with open(os.path.join(OUT, name + ".txt"), "wb") as f:
        f.write(msg)
    t_before = time.time()
    p = subprocess.run([FT, "-f", when, sys.executable, "-I", TW, "--stamp", name + ".txt", "--out",
                        name + ".stamp.json"], cwd=OUT, capture_output=True, text=True, timeout=120)
    t_after = time.time()
    rows.append({"id": name, "what": "stamped with the tool's command line under faketime -f '%s'" % when,
                 "expect": "VALID, window around the true time; self-reported clock far off", "source": None,
                 "payload_file": name + ".txt", "made_true": t_before, "made_true_end": t_after,
                 "stamp_exit": p.returncode, "stamp_summary": tw.scrub(p.stdout).strip().splitlines()[:1],
                 "stamp_stderr": tw.scrub(p.stderr)[-500:]})

with open(os.path.join(OUT, "rows.jsonl"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, sort_keys=True) + "\n")
print("%d attempts written to data/s5" % len(rows))
