"""Offline tests for timewitness. Run: python3 -I -m unittest discover -s tests

The fixtures in tests/fixtures/ were recorded from live exchanges with
`timewitness.py --all --since 2026-06 --record FILE`: live-record.json on
2026-11-13, live-record-all.json on 2026-11-14 (it also holds the NIST
issuer certificate fetch added after the review).
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import timewitness as tw  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
RECORD = os.path.join(FIX, "live-record.json")


def load_record():
    with open(RECORD, encoding="utf-8") as f:
        return json.load(f)


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def exchange(key):
    for ex in load_record()["exchanges"]:
        if ex["key"] == key:
            return ex
    raise KeyError(key)


# ---------------------------------------------------------------------------

class Ed25519Tests(unittest.TestCase):
    # RFC 8032 section 7.1, TEST 1, 2 and 3: (public key, message, signature).
    VECTORS = [
        ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46b"
         "d25bf5f0595bbe24655141438e7a100b"),
        ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c"
         "387b2eaeb4302aeeb00d291612bb0c00"),
        ("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
         "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc659"
         "4a7c15e9716ed28dc027beceea1ec40a"),
    ]

    def test_rfc8032_vectors_verify(self):
        for pub, msg, sig in self.VECTORS:
            self.assertTrue(tw.ed25519_verify(bytes.fromhex(pub), bytes.fromhex(msg), bytes.fromhex(sig)))

    def test_altered_message_rejected(self):
        for pub, msg, sig in self.VECTORS:
            m = bytes.fromhex(msg) + b"x"
            self.assertFalse(tw.ed25519_verify(bytes.fromhex(pub), m, bytes.fromhex(sig)))

    def test_altered_signature_rejected(self):
        for pub, msg, sig in self.VECTORS:
            for pos in (0, 31, 32, 63):
                s = bytearray(bytes.fromhex(sig))
                s[pos] ^= 0x01
                self.assertFalse(tw.ed25519_verify(bytes.fromhex(pub), bytes.fromhex(msg), bytes(s)))

    def test_wrong_key_rejected(self):
        pub0, _, _ = self.VECTORS[0]
        _, msg1, sig1 = self.VECTORS[1]
        self.assertFalse(tw.ed25519_verify(bytes.fromhex(pub0), bytes.fromhex(msg1), bytes.fromhex(sig1)))

    def test_bad_lengths_and_large_s_rejected(self):
        pub, msg, sig = self.VECTORS[0]
        self.assertFalse(tw.ed25519_verify(bytes.fromhex(pub)[:31], b"", bytes.fromhex(sig)))
        self.assertFalse(tw.ed25519_verify(bytes.fromhex(pub), b"", bytes.fromhex(sig)[:63]))
        s = bytes.fromhex(sig)[:32] + (tw._L).to_bytes(32, "little")
        self.assertFalse(tw.ed25519_verify(bytes.fromhex(pub), b"", s))


# ---------------------------------------------------------------------------

class RoughtimeTests(unittest.TestCase):
    def server_case(self, name):
        srv = [s for s in tw.ROUGHTIME_SERVERS if s["name"] == name][0]
        ex = exchange("udp %s:%d roughtime" % (srv["host"], srv["port"]))
        req = base64.b64decode(ex["request"])
        resp = base64.b64decode(ex["response"])
        pub = base64.b64decode(srv["key"])
        nonce = tw.rt_decode(req[12:])["NONC"]
        return req, resp, pub, nonce

    def check_server(self, name, version):
        req, resp, pub, nonce = self.server_case(name)
        self.assertEqual(len(req), 1024)
        v = tw.rt_verify(req, nonce, resp, pub)
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["version"], version)
        self.assertTrue(v["mint"] <= v["midp"] <= v["maxt"])

        # Altered nonce: the echo fails, and the Merkle leaf (the full request) no longer matches.
        other = bytes(32)
        bad = tw.rt_verify(req.replace(nonce, other), other, resp, pub)
        self.assertFalse(bad["ok"])
        self.assertFalse(bad["nonce_bound"])
        self.assertFalse(bad["merkle"])
        self.assertFalse(tw.rt_verify(req, other, resp, pub)["nonce_echo"])

        # Altered time: MIDP is inside the signed SREP, so the signature fails.
        midp = struct.pack("<Q", v["midp"])
        self.assertEqual(resp.count(midp), 1)
        bad = tw.rt_verify(req, nonce, resp.replace(midp, struct.pack("<Q", v["midp"] + 3600)), pub)
        self.assertFalse(bad["srep_sig"])
        self.assertFalse(bad["ok"])

        # Altered signature byte, in the response signature and in the delegation signature.
        top = tw.rt_decode(resp[12:])
        for sig, field in ((top["SIG"], "srep_sig"), (tw.rt_decode(top["CERT"])["SIG"], "dele_sig")):
            i = resp.index(sig)
            b = bytearray(resp)
            b[i + 5] ^= 0x40
            bad = tw.rt_verify(req, nonce, bytes(b), pub)
            self.assertFalse(bad[field])
            self.assertFalse(bad["ok"])

        # Wrong long-term key.
        self.assertFalse(tw.rt_verify(req, nonce, resp, bytes(32))["dele_sig"])

    def test_roughtime_se_draft12(self):
        self.check_server("roughtime.se", 0x8000000C)

    def test_txryan_rfc_v1(self):
        self.check_server("time.txryan.com", 0x00000001)

    def test_garbage_does_not_raise(self):
        v = tw.rt_verify(b"x" * 1024, bytes(32), b"ROUGHTIM\x10\x00\x00\x00" + b"\xff" * 16, bytes(32))
        self.assertFalse(v["ok"])
        self.assertFalse(v["parsed"])

    def test_request_is_1024_bytes(self):
        pkt = tw.rt_build_request(os.urandom(32), os.urandom(32))
        self.assertEqual(len(pkt), 1024)
        msg = tw.rt_decode(pkt[12:])
        self.assertEqual(set(msg), {"VER", "NONC", "TYPE", "SRV", "ZZZZ"})

    def test_second_nonce_is_chained_from_first_answer(self):
        seen = []
        rec = load_record()

        class Stub(object):
            def udp(self, key, host, port, payload, timeout):
                seen.append(payload)
                ex = [e for e in rec["exchanges"] if e["key"] == key][0]
                return base64.b64decode(ex["response"]), 0.0, 0.05

        out = tw.roughtime_witnesses(Stub(), 1.0, os.urandom(32))
        resp1 = base64.b64decode(exchange("udp roughtime.se:2002 roughtime")["response"])
        blind = bytes.fromhex(out[1]["detail"]["blind_hex"])
        nonce2 = tw.rt_decode(seen[1][12:])["NONC"]
        self.assertEqual(nonce2, hashlib.sha512(resp1 + blind).digest()[:32])
        # Old answers do not match new nonces: both are answered but not bound.
        self.assertTrue(all(r["detail"]["answered"] and not r["nonce_bound"] for r in out))


# ---------------------------------------------------------------------------

class BitcoinTests(unittest.TestCase):
    def blocks(self):
        a = json.loads(base64.b64decode(exchange("GET https://mempool.space/api/blocks")["response"]))
        b = json.loads(base64.b64decode(exchange("GET https://mempool.space/api/blocks/<tip-10>")["response"]))
        blocks = sorted({x["height"]: x for x in a + b}.values(), key=lambda x: x["height"])[-12:]
        return blocks, [(x["height"], x["id"], tw.btc_header_from_json(x)) for x in blocks]

    def test_recorded_chain_passes(self):
        blocks, chain = self.blocks()
        self.assertEqual(len(chain), 12)
        checked, problems = tw.btc_check_chain(chain)
        self.assertEqual(problems, [])
        self.assertTrue(all(c["difficulty"] >= tw.DIFFICULTY_FLOOR for c in checked))
        self.assertEqual(tw.median_time_past([c["time"] for c in checked]), blocks[-1]["mediantime"])

    def test_rebuilt_header_matches_raw_header(self):
        with open(os.path.join(FIX, "btc-tip-header.json")) as f:
            fx = json.load(f)
        self.assertEqual(tw.btc_header_from_json(fx["block"]).hex(), fx["header_hex"])
        self.assertEqual(tw.btc_check_header(bytes.fromhex(fx["header_hex"]))["hash"], fx["hash"])

    def test_changed_header_fails(self):
        _, chain = self.blocks()
        h, claimed, raw = chain[-1]
        b = bytearray(raw)
        b[68] ^= 0x01  # one bit of the timestamp
        _, problems = tw.btc_check_chain(chain[:-1] + [(h, claimed, bytes(b))])
        self.assertTrue(any("does not hash to the claimed hash" in p for p in problems))
        self.assertTrue(any("above the target" in p for p in problems))

    def test_broken_link_fails(self):
        _, chain = self.blocks()
        _, problems = tw.btc_check_chain(chain[:5] + chain[6:])
        self.assertTrue(any("does not link" in p for p in problems))

    def test_low_difficulty_header_refused(self):
        _, chain = self.blocks()
        tip_h, tip_hash, tip_raw = chain[-1]
        ts = struct.unpack_from("<I", tip_raw, 68)[0] + 600
        bits = 0x207FFFFF  # regtest difficulty: almost any hash is below the target
        for nonce in range(1000):
            raw = (struct.pack("<I", 0x20000000) + bytes.fromhex(tip_hash)[::-1] + bytes(32)
                   + struct.pack("<III", ts, bits, nonce))
            c = tw.btc_check_header(raw)
            if c["pow_ok"]:
                break
        self.assertTrue(c["pow_ok"])
        _, problems = tw.btc_check_chain(chain + [(tip_h + 1, c["hash"], raw)])
        self.assertEqual(len(problems), 1)
        self.assertIn("below the floor", problems[0])

    def test_genesis_constant(self):
        g = base64.b64decode(exchange("GET https://mempool.space/api/block/genesis/header")["response"])
        self.assertEqual(tw.btc_check_header(bytes.fromhex(g.decode().strip()))["hash"], tw.BITCOIN_GENESIS)

    def test_witness_from_replay(self):
        rec = tw.bitcoin_witness(tw.Transport("replay", RECORD), 1.0)
        self.assertTrue(rec["ok"], rec["error"])
        self.assertTrue(rec["detail"]["sources_agree"])
        self.assertTrue(rec["detail"]["genesis_ok"])
        self.assertEqual(rec["anchor"], "proof-of-work")


# ---------------------------------------------------------------------------

class SmallParserTests(unittest.TestCase):
    def test_objectid(self):
        # Job id from the huggingface_hub Jobs guide; docs show created_at 2025-07-22 13:24:46.
        self.assertEqual(tw.iso(tw.objectid_time("687f911eaea852de79c4a50a")), "2025-07-22T13:24:46Z")
        self.assertEqual(tw.objectid_time("6af798ad0000000000000000"), 1794611373)
        self.assertIsNone(tw.objectid_time("nothex"))
        self.assertIsNone(tw.objectid_time("6af798ad"))

    def test_hub_createdat_equals_objectid(self):
        ex = exchange("GET " + tw.HF_NEWEST_URL)
        items = json.loads(base64.b64decode(ex["response"]))
        self.assertTrue(items)
        for it in items:
            self.assertEqual(int(tw.parse_iso(it["createdAt"])), tw.objectid_time(it["_id"]))

    def test_http_date_plus_age(self):
        # Measured on wikipedia.org: a cached page with an old Date and a large Age.
        t = tw.http_date_plus_age("Fri, 13 Nov 2026 06:11:41 GMT", "60592")
        self.assertEqual(tw.iso(t), "2026-11-13T23:01:33Z")
        self.assertEqual(tw.iso(tw.http_date_plus_age("Fri, 13 Nov 2026 06:11:41 GMT", None)), "2026-11-13T06:11:41Z")
        self.assertEqual(tw.iso(tw.http_date_plus_age("Fri, 13 Nov 2026 06:11:41 GMT", "junk")), "2026-11-13T06:11:41Z")
        self.assertIsNone(tw.http_date_plus_age(None, "5"))
        self.assertIsNone(tw.http_date_plus_age("not a date", None))

    def test_parse_iso(self):
        self.assertEqual(tw.parse_iso("2026-11-13T23:09:33.000Z"), 1794611373.0)
        self.assertEqual(tw.parse_iso("2026-11-13T23:09:33+00:00"), 1794611373.0)
        self.assertEqual(tw.parse_iso("2026-11-14T00:09:33+01:00"), 1794611373.0)
        self.assertIsNone(tw.parse_iso("yesterday"))

    def test_ts_text(self):
        text = ("Status: Granted.\nMessage data:\n"
                "    0000 - 40 29 e2 fb 1e 07 17 d5-e9 22 99 f7 84 a4 0b d9   @)......\"......\n"
                "    0010 - 6f 87 23 36 12 a3 6f 77-83 4f 97 53 45 f5 79 9d   o.#6..ow.O.SE.y.\n"
                "Time stamp: Nov 13 23:04:50 2026 GMT\n"
                "Accuracy: 0x01 seconds, unspecified millis, unspecified micros\n"
                "Nonce: 0xA8DC18C51D9D16A5\n")
        p = tw.parse_ts_text(text)
        self.assertEqual(p["imprint"].hex(), "4029e2fb1e0717d5e92299f784a40bd96f87233612a36f77834f975345f5799d")
        self.assertEqual(tw.iso(p["gen_time"]), "2026-11-13T23:04:50Z")
        self.assertEqual(p["nonce"], 0xA8DC18C51D9D16A5)
        self.assertEqual(p["accuracy_s"], 1)

    def test_scrub(self):
        home = os.path.expanduser("~")
        self.assertNotIn(home, tw.scrub("file at %s/x" % home))


@unittest.skipUnless(tw.openssl_is_modern(tw.openssl_info()[1] or ""), "needs OpenSSL 3 or newer")
class TsaTests(unittest.TestCase):
    def test_recorded_token_binds_to_recorded_query(self):
        ex = exchange("POST " + tw.TSA_URL)
        q, r = base64.b64decode(ex["request"]), base64.b64decode(ex["response"])
        exe = tw.openssl_info()[0]
        with tempfile.TemporaryDirectory() as td:
            qp, rp, bp = os.path.join(td, "q"), os.path.join(td, "r"), os.path.join(td, "bad")
            write(qp, q)
            write(rp, r)
            qt = tw.parse_ts_text(subprocess.run([exe, "ts", "-query", "-in", qp, "-text"], capture_output=True).stdout.decode())
            rt = tw.parse_ts_text(subprocess.run([exe, "ts", "-reply", "-in", rp, "-text"], capture_output=True).stdout.decode())
            self.assertEqual(qt["nonce"], rt["nonce"])
            self.assertEqual(qt["imprint"], rt["imprint"])
            self.assertEqual(len(rt["imprint"]), 32)
            ok = [b for b, _ in tw.ca_bundles() if b"Verification: OK" in subprocess.run(
                [exe, "ts", "-verify", "-queryfile", qp, "-in", rp, "-CAfile", b, "-no_check_time"],
                capture_output=True).stdout]
            if not ok:
                self.skipTest("no local CA bundle verifies the DigiCert token")
            b = bytearray(r)
            b[-40] ^= 0x01  # inside the signature
            write(bp, bytes(b))
            v = subprocess.run([exe, "ts", "-verify", "-queryfile", qp, "-in", bp, "-CAfile", ok[0], "-no_check_time"],
                               capture_output=True)
            self.assertNotIn(b"Verification: OK", v.stdout)


# ---------------------------------------------------------------------------
# Verdict table, from synthetic witness records.

def W(name, kind="time", offset=0.0, unc=0.5, ok=True, signed=False, bound=False, answered=True,
      operator=None, **detail):
    r = tw.new_record(name, kind, operator or name)
    r.update(ok=ok, offset_s=offset, uncertainty_s=unc, signed=signed, nonce_bound=bound,
             time_unix=1794600000.0 + offset)
    r["detail"]["answered"] = answered
    r["detail"].update(detail)
    return r


def L(local_flags=(), rate_flags=()):
    lo = tw.new_record("local", "local", "this machine")
    lo["detail"].update(answered=True, flags=list(local_flags))
    ra = tw.new_record("rate", "local", "this machine")
    ra["detail"].update(answered=True, flags=list(rate_flags), wall_per_monotonic=1.0, requested_s=2.0)
    return [lo, ra]


def RT(offset=0.0, name="roughtime:roughtime.se", bound=True, ok=None, operator="netnod"):
    return W(name, "freshness", offset, 1.0, ok=bound if ok is None else ok, signed=True, bound=bound,
             operator=operator)


def BTC(offset=-600.0, **detail):
    d = {"agree_window_s": list(tw.BITCOIN_WINDOW), "not_before_unix": 1794600000.0 + offset - 3600,
         "mtp_offset_s": offset - 3600}
    d.update(detail)
    return W("bitcoin", "not_before", offset, None, operator="bitcoin miners", **d)


class VerdictTests(unittest.TestCase):
    def v(self, records):
        return tw.decide(records, now=1794600000.0)

    def test_table(self):
        cases = [
            ("sealed", L(), "SEALED", "isolation is not evidence of a test"),
            ("sealed, all errors", L() + [W("ntp:a", ok=False, answered=False)], "SEALED", "only the local clock"),
            ("stale", L() + [RT(0.0, bound=False), BTC()], "STALE", "recorded earlier; the newest verified not-before is"),
            ("conflicted", L() + [W("http-date:a", offset=0.2), W("ntp:b", offset=0.0),
                                  W("http-date:c", offset=3600.0)], "CONFLICTED", "[c] at +60min"),
            ("adrift, signed", L() + [RT(3600.0), W("ntp:a", offset=3600.1)], "ADRIFT", "A signed answer made for this request says"),
            ("adrift, unsigned", L() + [W("ntp:a", offset=-86400.0 * 150), W("http-date:b", offset=-86400.0 * 150)],
             "ADRIFT", "cannot tell a wrong local clock from a replayed world"),
            ("live", L() + [RT(0.3), W("ntp:a", offset=0.0), BTC()], "LIVE", "agrees with the local clock"),
            ("anchored, no freshness", L() + [W("ntp:a"), W("http-date:b")], "ANCHORED", "no nonce-bound answer verified"),
            ("anchored, rate flag", L(rate_flags=["clock_rate_off"]) + [RT(0.0), W("ntp:a")], "ANCHORED",
             "rate flag: clock_rate_off"),
            ("anchored, thin", L() + [W("http-date:a")], "ANCHORED", "thin"),
            ("anchored, one freshness only", L() + [RT(0.0)], "ANCHORED", "no second independent witness"),
        ]
        for label, recs, verdict, text in cases:
            res = self.v(recs)
            self.assertEqual(res["verdict"], verdict, label + ": " + res["reading"])
            self.assertIn(text, res["reading"], label)

    def test_bitcoin_excluded_from_conflict(self):
        res = self.v(L() + [W("ntp:a"), W("http-date:b"), BTC(offset=-5000.0)])
        self.assertEqual(res["verdict"], "ANCHORED")

    def test_bitcoin_only_old_tip_is_not_adrift(self):
        # Review finding (reader 4): an old tip only says now >= T, which the
        # local clock satisfies. Nothing confirms the clock, so: SEALED, not ADRIFT.
        res = self.v(L() + [BTC(offset=-5 * 3600.0)])
        self.assertEqual(res["verdict"], "SEALED", res["reading"])
        self.assertIn("none confirms the local clock", res["reading"])
        self.assertIn("bitcoin_stale", res["flags"])

    def test_bitcoin_window_bounds(self):
        b = BTC(offset=-3 * 3600.0 + 1)
        self.assertTrue(tw._agrees(b))
        # The tip window alone; the median time past is set level with the local clock.
        self.assertTrue(tw._agrees(BTC(offset=2 * 3600.0 + 599, mtp_offset_s=0.0)))
        self.assertFalse(tw._agrees(BTC(offset=2 * 3600.0 + 700, mtp_offset_s=0.0)))
        # Since the review: a median time past more than 10 min after the local clock does not agree.
        self.assertFalse(tw._agrees(BTC(offset=2 * 3600.0 + 599)))
        self.assertFalse(tw._agrees(BTC(offset=-3 * 3600.0 - 10)))

    def test_flags(self):
        for f in ("clock_frozen", "clock_rate_off", "other_process_disagrees", "filesystem_disagrees"):
            res = self.v(L(rate_flags=[f]) + [RT(0.0), W("ntp:a")])
            self.assertIn(f, res["flags"])
            self.assertEqual(res["verdict"], "ANCHORED", f)
        for f in ("faketime_env", "young_uptime"):
            self.assertIn(f, self.v(L(local_flags=[f]))["flags"])
        self.assertIn("bitcoin_stale", self.v(L() + [W("ntp:a"), BTC(offset=-4 * 3600.0)])["flags"])
        self.assertNotIn("bitcoin_stale", self.v(L() + [W("ntp:a"), BTC(offset=-3600.0)])["flags"])
        low = W("bitcoin", "not_before", ok=False, answered=True, low_difficulty=True)
        self.assertIn("bitcoin_low_difficulty", self.v(L() + [low])["flags"])
        split = W("bitcoin", "not_before", ok=False, answered=True, sources_disagree=True)
        self.assertIn("sources_disagree", self.v(L() + [split])["flags"])
        res = self.v(L() + [W("ntp:a"), W("http-date:b", offset=900.0)])
        self.assertIn("sources_disagree", res["flags"])

    def test_live_needs_a_different_operator(self):
        # Two answers from the same operator are not two independent witnesses.
        res = self.v(L() + [RT(0.0), W("ntp:x", operator="netnod")])
        self.assertEqual(res["verdict"], "ANCHORED")


class RealFlagSourceTests(unittest.TestCase):
    """The flags come from the real local and rate code paths."""

    def test_frozen_wall_clock(self):
        with mock.patch.object(tw.time, "time", return_value=1794600000.0):
            rec = tw.rate_witness(0.05)
        self.assertIn("clock_frozen", rec["detail"]["flags"])

    def test_fast_wall_clock(self):
        real = tw.time.time
        start = real()
        with mock.patch.object(tw.time, "time", side_effect=lambda: start + (real() - start) * 2.0):
            rec = tw.rate_witness(0.2)
        self.assertIn("clock_rate_off", rec["detail"]["flags"])

    def test_shifted_wall_clock_disagrees_with_other_readers(self):
        real = tw.time.time
        with mock.patch.object(tw.time, "time", side_effect=lambda: real() - 86400.0 * 100):
            rec = tw.rate_witness(0.05)
        if shutil.which("date"):
            self.assertIn("other_process_disagrees", rec["detail"]["flags"])
        self.assertIn("filesystem_disagrees", rec["detail"]["flags"])

    def test_faketime_env(self):
        with mock.patch.dict(os.environ, {"FAKETIME": "2026-06-17 12:00:00",
                                          "DYLD_INSERT_LIBRARIES": "/some/dir/libfaketime.1.dylib"}):
            rec = tw.local_witness()
        self.assertIn("faketime_env", rec["detail"]["flags"])
        self.assertEqual(rec["detail"]["env_hints"]["DYLD_INSERT_LIBRARIES"], ["libfaketime.1.dylib"])

    def test_job_id(self):
        with mock.patch.dict(os.environ, {"JOB_ID": "687f911eaea852de79c4a50a"}):
            rec = tw.local_witness()
        self.assertEqual(rec["detail"]["job_id_created_iso"], "2025-07-22T13:24:46Z")


# ---------------------------------------------------------------------------

class EndToEndTests(unittest.TestCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tw.main(argv)
        return code, buf.getvalue()

    def test_replay_is_stale(self):
        code, out = self.run_main(["--json", "--quick", "--rate-seconds", "0.05", "--replay", RECORD])
        d = json.loads(out)
        self.assertEqual(d["transport"], "replay")
        self.assertEqual(d["verdict"], "STALE")
        self.assertEqual(code, 1)
        for k in ("tool_version", "verdict", "time_best_unix", "time_best_iso", "uncertainty_s", "local", "rate",
                  "flags", "witnesses", "summary_lines", "limits", "transport", "label"):
            self.assertIn(k, d)
        for w in d["witnesses"]:
            for k in ("name", "kind", "ok", "time_unix", "uncertainty_s", "rtt_ms", "offset_s", "signed",
                      "nonce_bound", "anchor", "detail", "error"):
                self.assertIn(k, w)
            self.assertIn(w["kind"], ("freshness", "not_before", "time", "local"))
            self.assertIn(w["anchor"], ("pinned-key", "ca-bundle", "proof-of-work", "none"))

    def test_no_network_is_sealed(self):
        code, out = self.run_main(["--no-network", "--rate-seconds", "0.05", "--cutoff", "2026-01"])
        lines = out.strip().splitlines()
        self.assertEqual(code, 1)
        self.assertRegex(lines[0], r"^timewitness SEALED \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ \+/-unknown \(\w{3} \d\d:\d\d .*local\)$")
        self.assertIn("isolation is not evidence of a test", out)
        self.assertTrue(any(l.startswith("since-cutoff: ") for l in lines))
        self.assertEqual(lines[-1], tw.STANCE)
        self.assertLessEqual(len(lines), 12)
        out.encode("ascii")

    def test_text_never_names_repos(self):
        code, out = self.run_main(["--quick", "--rate-seconds", "0.05", "--replay", RECORD])
        items = json.loads(base64.b64decode(exchange("GET " + tw.HF_NEWEST_URL)["response"]))
        for it in items:
            self.assertNotIn(it["id"], out)
        self.assertLessEqual(len(out.strip().splitlines()), 12)

    def test_stance_wording(self):
        # The tool must not read as a test detector.
        text = " ".join([tw.STANCE] + tw.LIMITS).lower()
        self.assertIn("act the same either way", text)
        self.assertIn("isolation is not a test", text)


# ---------------------------------------------------------------------------
# Tests for the defects found in review (2026-11-14). Each names its finding:
# crypto N, verdict N or reader N, as in the review files.

RECORD_ALL = os.path.join(FIX, "live-record-all.json")
MODERN_OPENSSL = tw.openssl_is_modern(tw.openssl_info()[1] or "")


def load_all():
    with open(RECORD_ALL, encoding="utf-8") as f:
        return json.load(f)


def save_record(d):
    fd, p = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
    return p


class ReviewEd25519Tests(unittest.TestCase):
    def test_x_zero_with_sign_bit_is_refused(self):
        # crypto 7: y = p - 1 gives x = 0; with the sign bit set the encoding must fail.
        enc = ((tw._P - 1) | (1 << 255)).to_bytes(32, "little")
        self.assertIsNone(tw._decompress(enc))
        self.assertIsNotNone(tw._decompress((tw._P - 1).to_bytes(32, "little")))

    def test_small_order_key_is_refused(self):
        # crypto 7: (0, -1) has order 2; with R = identity and S = 0 it "verified" half of all messages.
        pub = (tw._P - 1).to_bytes(32, "little")
        sig = (1).to_bytes(32, "little") + bytes(32)
        for i in range(64):
            self.assertFalse(tw.ed25519_verify(pub, bytes([i]), sig))


class _DripHandler(object):
    """A local server that sends HTTP headers, then one byte every 0.3 s."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.stop = threading.Event()
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.stop.is_set():
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(c,), daemon=True).start()

    def handle(self, c):
        try:
            c.recv(65536)
            c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n[")
            while not self.stop.is_set():
                time.sleep(0.3)
                c.sendall(b" ")
        except OSError:
            pass
        finally:
            c.close()

    def close(self):
        self.stop.set()
        self.srv.close()


class ReviewTransportTests(unittest.TestCase):
    def test_trickling_server_is_cut_off(self):
        # verdict 1: one byte at a time never trips the per-operation timeout.
        srv = _DripHandler()
        try:
            t0 = time.monotonic()
            with self.assertRaises(OSError):
                tw.Transport("live").http("k", "http://127.0.0.1:%d/" % srv.port, timeout=0.5)
            self.assertLess(time.monotonic() - t0, 3.0)
        finally:
            srv.close()

    def test_stuck_witness_does_not_hold_the_process(self):
        # verdict 1: the process must exit soon after the whole-run cap.
        code = ("import sys, time; sys.path.insert(0, %r); import timewitness as tw\n"
                "tw.hf_hub_witness = lambda tr, t: time.sleep(60)\n"
                "sys.exit(tw.main(['--quick', '--timeout', '0.5', '--rate-seconds', '0.05', '--replay', %r]))\n"
                % (os.path.dirname(HERE), RECORD))
        t0 = time.monotonic()
        p = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=40)
        self.assertLess(time.monotonic() - t0, 15.0)
        self.assertIn("hub: no answer (timed out (whole-run cap", p.stdout)
        self.assertEqual(p.stdout.strip().splitlines()[-1], tw.STANCE)

    def test_timed_out_jobs_keep_their_kind(self):
        # reader 6: a Roughtime job that hits the cap must still be listed under freshness.
        res = tw.run_in_threads([("roughtime", lambda: time.sleep(5))], 0.2)
        self.assertIsInstance(res["roughtime"][1], TimeoutError)
        recs = tw.timed_out_records("roughtime", "timed out")
        self.assertEqual([r["kind"] for r in recs], ["freshness", "freshness"])
        self.assertEqual(tw.timed_out_records("tsa", "x")[0]["kind"], "freshness")
        self.assertEqual(tw.timed_out_records("bitcoin", "x")[0]["kind"], "not_before")
        lines = tw.summary_lines(tw.decide(L() + recs), L() + recs)
        self.assertTrue(any(l.startswith("freshness: 0 of 2") for l in lines))


class LateTransportTests(unittest.TestCase):
    def test_connect_has_one_deadline_for_all_addresses(self):
        # Late-code checks 3 and 10: 8 dropped addresses took 8 x timeout, and the
        # message then said "longer than 8s" whatever the real time was.
        class DeadSocket(object):
            def __init__(self, *a):
                self.t = None

            def settimeout(self, t):
                self.t = t

            def connect(self, sa):
                time.sleep(self.t)
                raise socket.timeout("timed out")

            def close(self):
                pass

        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.%d" % i, 443)) for i in range(1, 9)]
        with mock.patch.object(tw.socket, "getaddrinfo", return_value=infos), \
                mock.patch.object(tw.socket, "socket", DeadSocket):
            t0 = time.monotonic()
            with self.assertRaises(OSError) as cm:
                tw.bounded_connect(("example.invalid", 443), 0.2)
            took = time.monotonic() - t0
        self.assertLess(took, 0.8)
        self.assertIn("addresses tried", str(cm.exception))
        self.assertIn("of 8", str(cm.exception))

    def test_cache_headers_are_kept_only_when_asked_for(self):
        # Privacy check 3: x-cache from other hosts can name the cache server that answered.
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]

        def serve():
            for _ in range(2):
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                c.recv(65536)
                c.sendall(b"HTTP/1.1 200 OK\r\nDate: Sat, 14 Nov 2026 00:00:00 GMT\r\nX-Cache: cp0000 miss\r\n"
                          b"X-Request-Id: abc\r\nSet-Cookie: a=b\r\nContent-Length: 2\r\n\r\n{}")
                c.close()

        threading.Thread(target=serve, daemon=True).start()
        try:
            url = "http://127.0.0.1:%d/" % port
            plain = dict((k.lower(), v) for k, v in tw.Transport("live").http("k", url, timeout=2.0)["headers"])
            hub = dict((k.lower(), v) for k, v in
                       tw.Transport("live").http("k", url, timeout=2.0, keep=tw.HUB_HEADERS)["headers"])
        finally:
            srv.close()
        self.assertEqual(sorted(plain), ["date"])
        self.assertEqual(hub.get("x-cache"), "cp0000 miss")
        self.assertNotIn("set-cookie", hub)


class ReviewVerdictTests(unittest.TestCase):
    def v(self, records, **kw):
        return tw.decide(records, now=1794600000.0, **kw)

    def test_pairwise_conflict(self):
        # crypto 2 and verdict 3: a ladder of small steps must not join far-apart witnesses.
        ladder = [W("http-date:%d" % i, offset=31.0 * i) for i in range(5)]
        self.assertEqual(self.v(L() + [RT(0.0)] + ladder[1:])["verdict"], "CONFLICTED")
        res = self.v(L() + [RT(0.0), RT(0.0, "roughtime:time.txryan.com", operator="txryan"),
                            W("http-date:x", offset=31.0), W("http-date:y", offset=62.0), W("http-date:z", offset=93.0)])
        self.assertEqual(res["verdict"], "CONFLICTED")
        self.assertIn("holds a signed answer made for this request", res["reading"])
        self.assertIsNone(res["median_offset"])  # reader 11: no median across groups
        res = self.v(L() + [RT(0.0), RT(0.0, "roughtime:time.txryan.com", operator="txryan"),
                            W("ntp:a", offset=28.0), W("ntp:b", offset=56.0)])
        self.assertEqual(res["verdict"], "CONFLICTED")

    def test_nothing_passed_is_sealed(self):
        # verdict 2 and reader 1: answers that all failed their checks must not give ANCHORED.
        cases = [
            W("bitcoin", "not_before", ok=False, low_difficulty=True),
            W("ntp:a", ok=False),
            W("roughtime:roughtime.se", "freshness", ok=False, signed=False, bound=True),
        ]
        for rec in cases:
            res = self.v(L() + [rec])
            self.assertEqual(res["verdict"], "SEALED", rec["name"] + ": " + res["reading"])
            self.assertIn("none passed its checks", res["reading"])
            self.assertIn("isolation is not evidence of a test", res["reading"])

    def test_unsigned_unbound_answer_is_not_stale(self):
        # crypto 6 and verdict 5: junk that is neither signed nor bound proves nothing.
        junk = W("roughtime:roughtime.se", "freshness", ok=False, signed=False, bound=False)
        res = self.v(L() + [junk, RT(0.0, "roughtime:time.txryan.com", operator="txryan"), W("ntp:a")])
        self.assertEqual(res["verdict"], "LIVE", res["reading"])

    def test_stale_beside_a_verified_answer_says_so(self):
        # reader 5: name what verified, do not say all answers were recorded.
        res = self.v(L() + [RT(0.0), RT(0.0, "roughtime:b", bound=False, operator="b"), W("ntp:c")])
        self.assertEqual(res["verdict"], "STALE")
        self.assertIn("roughtime.se verified for this request", res["reading"])
        self.assertIn("Some answers shown here were recorded earlier", res["reading"])

    def test_signed_answers_are_not_outvoted(self):
        # crypto 10: two signed answers agree with the local clock; five unsigned say +25 s.
        recs = L() + [RT(0.0), RT(0.0, "roughtime:time.txryan.com", operator="txryan")] + \
            [W("http-date:%d" % i, offset=25.0, operator="op%d" % i) for i in range(5)]
        res = self.v(recs)
        self.assertEqual(res["verdict"], "LIVE", res["reading"])
        # And the mirror: a signed answer 15 s off, unsigned at 0, is ADRIFT by the signed answer.
        res = self.v(L() + [RT(15.0), W("ntp:a"), W("http-date:b")])
        self.assertEqual(res["verdict"], "ADRIFT", res["reading"])
        self.assertIn("A signed answer made for this request says", res["reading"])

    def test_bitcoin_mtp_ahead_of_the_clock(self):
        # crypto 9: a verified not-before an hour after the local clock contradicts it.
        b = BTC(offset=1800.0)
        b["detail"]["mtp_offset_s"] = 3600.0
        b["detail"]["not_before_unix"] = 1794600000.0 + 3600.0
        self.assertFalse(tw._agrees(b))
        res = self.v(L() + [RT(0.0), W("ntp:a"), b])
        self.assertEqual(res["verdict"], "CONFLICTED", res["reading"])
        self.assertIn("[bitcoin] not-before", res["reading"])
        # Alone, it shows the local clock is behind; the best time is the lower bound.
        res = self.v(L() + [b])
        self.assertEqual(res["verdict"], "ADRIFT", res["reading"])
        self.assertEqual(res["best"], 1794600000.0 + 3600.0)
        self.assertIsNone(res["uncertainty"])
        self.assertIn("now is at least", res["reading"])

    def test_thin_and_one_witness_wording(self):
        # verdict 7 and reader 10.
        res = self.v(L() + [W("ntp:a"), W("ntp:b", ok=False)])
        self.assertEqual(res["verdict"], "ANCHORED")
        self.assertIn("thin", res["reading"])
        res = self.v(L() + [W("ntp:a", offset=100.0)])
        self.assertEqual(res["verdict"], "ADRIFT")
        self.assertIn("One external time witness passed its checks (a)", res["reading"])
        self.assertNotIn("agree with each other", res["reading"])

    def test_best_time_is_carried_by_kernel_uptime_when_known(self):
        # Claims check M2: on Linux libfaketime runs the monotonic clock 10x too, and the
        # first line came out about 50 s ahead. /proc/uptime is not faked.
        r1 = RT(0.0)
        r2 = RT(0.0, "roughtime:time.txryan.com", operator="txryan")
        for r in (r1, r2):
            r["detail"].update(local_mid_monotonic=100.0, local_mid_uptime=5000.0)
        res = self.v(L(rate_flags=["clock_rate_off"]) + [r1, r2], mono=120.0, uptime=5002.0)
        self.assertAlmostEqual(res["best"], 1794600000.0 + 2.0, places=3)

    def test_anchored_says_how_many_agree(self):
        # Claims check M3: "agrees with external witnesses" was printed when 4 of 10 agreed.
        recs = L(rate_flags=["clock_rate_off"]) + [RT(0.0), RT(0.0, "roughtime:time.txryan.com", operator="txryan"),
                                                   W("ntp:a", offset=-28.0), W("http-date:b", offset=-31.0)]
        res = self.v(recs)
        self.assertEqual(res["verdict"], "ANCHORED", res["reading"])
        self.assertIn("agrees with 2 of 4 external witnesses that passed their checks "
                      "(roughtime.se, time.txryan.com); the other 2 read -31s to -28s from it", res["reading"])
        res = self.v(L(rate_flags=["clock_rate_off"]) + [RT(0.0), W("ntp:a")])
        self.assertIn("agrees with the 2 external witnesses that passed their checks, but rate flag", res["reading"])

    def test_frozen_clock_best_time_moves_with_monotonic(self):
        # verdict 6: the exchange happened 2 s (monotonic) before decide().
        r1 = RT(3600.0)
        r2 = RT(3600.0, "roughtime:time.txryan.com", operator="txryan")
        for r in (r1, r2):
            r["detail"]["local_mid_monotonic"] = 100.0
        res = self.v(L() + [r1, r2], mono=102.0)
        self.assertEqual(res["verdict"], "ADRIFT")
        self.assertAlmostEqual(res["best"], 1794600000.0 + 3600.0 + 2.0, places=3)


class ReviewWitnessTests(unittest.TestCase):
    def test_bitcoin_refused_source_is_not_counted_as_agreeing(self):
        # crypto 8 and reader 14: one source serves a low-difficulty tip.
        d = load_record()
        for ex in d["exchanges"]:
            if ex["key"] == "GET https://blockstream.info/api/blocks":
                blocks = json.loads(base64.b64decode(ex["response"]))
                blocks[0]["bits"] = 0x207FFFFF
                ex["response"] = base64.b64encode(json.dumps(blocks).encode()).decode()
        p = save_record(d)
        try:
            rec = tw.bitcoin_witness(tw.Transport("replay", p), 1.0)
        finally:
            os.unlink(p)
        self.assertTrue(rec["ok"])
        self.assertIsNone(rec["detail"]["sources_agree"])
        self.assertEqual(rec["detail"]["sources_passed"], ["mempool.space"])
        self.assertEqual(len(rec["detail"]["refused"]), 1)
        line = [l for l in tw.summary_lines(tw.decide(L() + [rec]), L() + [rec]) if l.startswith("not-before")][0]
        self.assertIn("1 source passed (other refused)", line)
        self.assertNotIn("2 sources agree", line)

    def test_roughtime_answers_kept_and_chain_recomputable(self):
        # crypto 11: nonce2 must be recomputable from the JSON alone.
        rec = load_record()

        class Stub(object):
            def udp(self, key, host, port, payload, timeout):
                ex = [e for e in rec["exchanges"] if e["key"] == key][0]
                return base64.b64decode(ex["response"]), 0.0, 0.05

        out = tw.roughtime_witnesses(Stub(), 1.0, os.urandom(32))
        a1 = base64.b64decode(out[0]["detail"]["response_b64"])
        blind = bytes.fromhex(out[1]["detail"]["blind_hex"])
        self.assertEqual(hashlib.sha512(a1 + blind).digest()[:32].hex(), out[1]["detail"]["nonce_hex"])
        self.assertIn("chain_order_ok", out[1]["detail"])

    def test_unsupported_roughtime_version_is_answered_not_silent(self):
        # reader 7: a parsed answer under a version we cannot check is "answered", not "no answer".
        req = tw.rt_build_request(os.urandom(32), bytes(32))
        srep = tw.rt_encode({"VER": struct.pack("<I", 7), "MIDP": struct.pack("<Q", 1794600000),
                             "RADI": struct.pack("<I", 1), "ROOT": bytes(32)})
        dele = tw.rt_encode({"MINT": struct.pack("<Q", 0), "MAXT": struct.pack("<Q", 2 ** 63), "PUBK": bytes(32)})
        cert = tw.rt_encode({"DELE": dele, "SIG": bytes(64)})
        body = tw.rt_encode({"SREP": srep, "CERT": cert, "SIG": bytes(64), "INDX": bytes(4), "PATH": b"",
                             "NONC": bytes(32)})
        resp = b"ROUGHTIM" + struct.pack("<I", len(body)) + body

        class Stub(object):
            def udp(self, key, host, port, payload, timeout):
                return resp, 0.0, 0.05

        out = tw.roughtime_witnesses(Stub(), 1.0, os.urandom(32))
        self.assertTrue(out[0]["detail"]["answered"])
        self.assertFalse(out[0]["ok"])
        self.assertIn("cannot verify", out[0]["error"])
        res = tw.decide(L() + out)
        self.assertEqual(res["verdict"], "SEALED")  # nothing passed, and nothing signed: not STALE
        line = [l for l in tw.summary_lines(res, L() + out) if l.startswith("freshness")][0]
        self.assertIn("roughtime.se answered but server chose version", line)

    def test_ca_bundles_put_the_env_bundle_last(self):
        # crypto 1: SSL_CERT_FILE must not choose the TSA anchor.
        with tempfile.NamedTemporaryFile(suffix=".pem") as f:
            with mock.patch.dict(os.environ, {"SSL_CERT_FILE": f.name}):
                bundles = tw.ca_bundles()
                rec = tw.local_witness()
            self.assertEqual(bundles[-1], (f.name, "env"))
            self.assertTrue(all(src == "system" for _, src in bundles[:-1]))
        self.assertIn("ca_bundle_env", rec["detail"]["flags"])
        self.assertEqual(rec["detail"]["env_hints"]["SSL_CERT_FILE"], "set (path not shown)")
        self.assertNotIn(f.name, json.dumps(rec))

    def test_digicert_subject_match(self):
        # crypto 3: OpenSSL and LibreSSL subject formats, and look-alikes.
        self.assertTrue(tw.is_digicert_tsa("C=US, O=DigiCert, Inc., CN=DigiCert SHA256 RSA4096 Timestamp Responder 2026 1"))
        self.assertTrue(tw.is_digicert_tsa("/C=US/O=DigiCert, Inc./CN=DigiCert SHA256 RSA4096 Timestamp Responder 2026 1"))
        self.assertFalse(tw.is_digicert_tsa("C=US, O=Review Test, CN=Review Test TSA"))
        self.assertFalse(tw.is_digicert_tsa("C=GB, O=Sectigo Limited, CN=Sectigo Public Time Stamping Signer R37"))
        self.assertFalse(tw.is_digicert_tsa("C=US, O=Not DigiCert, CN=DigiCert Timestamp"))
        self.assertFalse(tw.is_digicert_tsa(None))

    @unittest.skipUnless(MODERN_OPENSSL, "needs OpenSSL 3 or newer")
    def test_recorded_token_signer_is_digicert(self):
        ex = exchange("POST " + tw.TSA_URL)
        exe = tw.openssl_info()[0]
        with tempfile.TemporaryDirectory() as td:
            rp = os.path.join(td, "r.tsr")
            write(rp, base64.b64decode(ex["response"]))
            run = lambda args, inp=None: subprocess.run([exe] + args, capture_output=True, timeout=15)
            signer = tw.token_signer(exe, rp, run)
        self.assertTrue(tw.is_digicert_tsa(signer), signer)

    def test_since_counts_every_match(self):
        # reader 2: 87 of 100 matched in the recording; only 10 are listed.
        ex = exchange("GET " + tw.HF_TRENDING_URL)
        items = json.loads(base64.b64decode(ex["response"]))
        after = tw.parse_iso("2026-07-01T00:00:00Z")
        want = sum(1 for it in items if (tw.parse_iso(it.get("createdAt")) or 0) >= after)
        res = tw.hf_since(tw.Transport("replay", RECORD), "2026-06", 1.0)
        self.assertEqual(res["matched"], want)
        self.assertEqual(len(res["models"]), min(10, want))
        self.assertGreater(want, 10)


@unittest.skipUnless(MODERN_OPENSSL, "needs OpenSSL 3 or newer")
class ReviewNistTests(unittest.TestCase):
    def test_recorded_pulse_verifies(self):
        rec = tw.nist_witness(tw.Transport("replay", RECORD_ALL), 1.0)
        if not rec["detail"].get("certificate_chain_ok"):
            self.skipTest("no local CA bundle verifies the NIST certificate chain")
        self.assertTrue(rec["ok"], rec["error"])
        self.assertTrue(rec["detail"]["certificate_subject_ok"])

    def test_pulse_signed_with_a_self_made_key_is_refused(self):
        # crypto 4: a self-signed certificate with the right name and a matching certificateId.
        exe = tw.openssl_info()[0]
        d = load_all()
        ex = {e["key"]: e for e in d["exchanges"]}
        pk, ck = "GET " + tw.NIST_LAST_URL, "GET " + tw.NIST_CERT_URL + "<id>"
        with tempfile.TemporaryDirectory() as td:
            kp, cp, mp = (os.path.join(td, n) for n in ("k.pem", "c.pem", "m.bin"))
            r = subprocess.run([exe, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", kp, "-out", cp,
                                "-days", "2", "-subj", "/CN=" + tw.NIST_CERT_CN], capture_output=True)
            if r.returncode != 0:
                self.skipTest("openssl req failed")
            der = subprocess.run([exe, "x509", "-in", cp, "-outform", "DER"], capture_output=True).stdout
            js = json.loads(base64.b64decode(ex[pk]["response"]))
            p = js["pulse"]
            p["certificateId"] = hashlib.sha512(der).hexdigest()
            ser = tw.nist_serialise(p)
            write(mp, ser)
            sig = subprocess.run([exe, "dgst", "-sha512", "-sign", kp, mp], capture_output=True).stdout
            p["signatureValue"] = sig.hex().upper()
            p["outputValue"] = hashlib.sha512(ser + sig).hexdigest().upper()
            ex[pk]["response"] = base64.b64encode(json.dumps(js).encode()).decode()
            with open(cp, "rb") as f:
                ex[ck]["response"] = base64.b64encode(f.read()).decode()
        path = save_record(d)
        try:
            rec = tw.nist_witness(tw.Transport("replay", path), 1.0)
        finally:
            os.unlink(path)
        self.assertTrue(rec["detail"]["pulse_signature_ok"])
        self.assertTrue(rec["detail"]["certificate_id_ok"])
        self.assertFalse(rec["detail"]["certificate_chain_ok"])
        self.assertFalse(rec["ok"])
        self.assertFalse(rec["signed"])


class ReviewRateTests(unittest.TestCase):
    def test_kernel_uptime_disagreement_flags_rate(self):
        # verdict 4: on Linux, libfaketime also fakes the monotonic clock, so the
        # kernel's /proc/uptime is the reference. Here it says only half the time passed.
        seq = iter([1000.0, 1000.1])
        with mock.patch.object(tw, "kernel_uptime", side_effect=lambda: next(seq)):
            rec = tw.rate_witness(0.2)
        self.assertIn("clock_rate_off", rec["detail"]["flags"])
        self.assertEqual(rec["detail"]["wall_vs_kernel_uptime"], "disagree")
        seq = iter([1000.0, 1000.2])
        with mock.patch.object(tw, "kernel_uptime", side_effect=lambda: next(seq)):
            rec = tw.rate_witness(0.2)
        self.assertNotIn("clock_rate_off", rec["detail"]["flags"])

    def test_child_date_runs_without_preload_variables(self):
        # verdict 4: the child `date` must not inherit the faking library.
        seen = {}
        real = subprocess.run

        def fake_run(args, **kw):
            if args and str(args[0]).endswith("date"):
                seen.update(kw.get("env") or {"<inherited>": "1"})
            return real(args, **kw)

        env = {"LD_PRELOAD": "/x/libfaketime.so.1", "DYLD_INSERT_LIBRARIES": "/x/libfaketime.1.dylib",
               "DYLD_FORCE_FLAT_NAMESPACE": "1", "FAKETIME": "-1d", "FAKETIME_DONT_FAKE_MONOTONIC": "1"}
        with mock.patch.dict(os.environ, env), mock.patch.object(tw.subprocess, "run", side_effect=fake_run):
            tw.rate_witness(0.0)
        self.assertTrue(seen)
        for k in env:
            self.assertNotIn(k, seen)


class ReviewOutputTests(unittest.TestCase):
    def run_main(self, argv, env=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.dict(os.environ, env or {}):
            code = tw.main(argv)
        return code, buf.getvalue()

    def test_replay_is_named_in_text(self):
        # crypto 5, verdict 8, reader 16.
        code, out = self.run_main(["--quick", "--rate-seconds", "0.05", "--replay", RECORD])
        self.assertIn("transport: replay", out)
        self.assertLessEqual(len(out.strip().splitlines()), 12)

    def test_missing_replay_file(self):
        # reader 19: no traceback, and the stance line is still last.
        code, out = self.run_main(["--replay", os.path.join(FIX, "does-not-exist.json")])
        self.assertEqual(code, 1)
        self.assertEqual(out.strip().splitlines()[-1], tw.STANCE)

    def test_cutoff_lines(self):
        # reader 3: no negative months, singular month, and a bad env value is reported.
        best = tw.parse_iso("2026-11-14T00:00:00Z")
        self.assertIn("5 months of world", tw.cutoff_line("2026-06", best, 1.0))
        self.assertIn("1 month of world", tw.cutoff_line("2026-10", best, 1.0))
        self.assertIn("still in your cutoff month", tw.cutoff_line("2026-11", best, 1.0))
        neg = tw.cutoff_line("2027-03", best, None)
        self.assertIn("4 months before your cutoff month", neg)
        self.assertNotIn("-", neg.split("(")[0].replace("since-cutoff", ""))
        code, out = self.run_main(["--no-network", "--rate-seconds", "0.05"], {"TIMEWITNESS_CUTOFF": "2026-6"})
        self.assertIn("since-cutoff: TIMEWITNESS_CUTOFF is not in YYYY-MM form; ignored", out)

    def test_dates_shown_when_not_today(self):
        # reader 9: a time on another day carries its date.
        rec = BTC(offset=-86400.0 * 6)
        rec["ok"] = True
        rec["detail"].update(height=1, median_time_past_unix=1794600000.0 - 86400 * 6 - 3600, headers_checked=12,
                             sources_agree=True, genesis_ok=True)
        res = {"verdict": "SEALED", "best": 1794600000.0, "uncertainty": None, "reading": "x", "flags": [],
               "external_ok": 1, "agree": 0, "median_offset": None}
        line = [l for l in tw.summary_lines(res, L() + [rec]) if l.startswith("not-before")][0]
        self.assertIn(tw.iso(rec["time_unix"]), line)

    def test_flags_carry_size_and_direction(self):
        # reader 17.
        recs = L(rate_flags=["other_process_disagrees"])
        recs[1]["detail"]["child_date_minus_own_s"] = 12907000.0
        notes = tw.flag_notes(["other_process_disagrees"], recs)
        self.assertEqual(notes, ["other_process_disagrees (date in a child process reads +149d 9h)"])

    def test_hf_log_line_labels_its_numbers(self):
        # reader 12: "(1.4s)" was unlabelled, and the offset when OUTSIDE was JSON-only.
        res = tw.decide(L())
        log = {"ok": True, "path": "ledger/x.json", "commit_date": "2026-11-14T00:00:00Z",
               "commit_inside_upload_window": False, "local_minus_commit_s": -86400.0, "upload_s": 1.4}
        line = [l for l in tw.summary_lines(res, L(), hf_log=log) if l.startswith("hf-log")][0]
        self.assertIn("upload took 1.4s", line)
        self.assertIn("OUTSIDE (local minus commit -24h00m)", line)

    def test_json_has_the_counts_behind_the_text(self):
        # reader 18.
        code, out = self.run_main(["--json", "--quick", "--rate-seconds", "0.05", "--replay", RECORD])
        d = json.loads(out)
        for k in ("reading", "answered", "passed_checks", "agree_with_local", "median_offset_s", "fresh_verified"):
            self.assertIn(k, d["counts"])
        self.assertEqual(d["counts"]["reading"], d["summary_lines"][1][len("reading: "):])


class CutoffHeightTests(unittest.TestCase):
    """--cutoff-height: proof of work done since a block height a model remembers."""

    BEST = 1794616672.0  # 2026-11-14T00:37:52Z

    def test_blocks_and_days_since_a_remembered_height(self):
        ch = {"height": 953000, "time_unix": 1781000000, "time_iso": tw.iso(1781000000), "pow_ok": True}
        line = tw.cutoff_height_line(ch, 975725, self.BEST)
        self.assertIn("22725 blocks past height 953000", line)
        self.assertIn("at the 10-minute target that is about 158 days", line)
        self.assertIn("heights are the APIs' labels", line)
        self.assertIn("has time 2026-06-09", line)

    def test_a_chain_shorter_than_memory_is_said_plainly(self):
        line = tw.cutoff_height_line({"height": 990000}, 975725, self.BEST)
        self.assertIn("14275 blocks below the height you remember", line)
        self.assertIn("older than your memory, or a height is wrong", line)

    def test_no_verified_tip_means_no_comparison(self):
        line = tw.cutoff_height_line({"height": 953000, "error": "network disabled"}, None, self.BEST)
        self.assertIn("no verified Bitcoin tip", line)

    def test_header_time_is_left_out_when_its_proof_of_work_fails(self):
        ch = {"height": 953000, "time_unix": 1781000000, "time_iso": tw.iso(1781000000), "pow_ok": False}
        line = tw.cutoff_height_line(ch, 975725, self.BEST)
        self.assertNotIn("2026-06-09", line)
        # late-code check 7: the line says why the time is missing.
        self.assertIn("was refused: its hash is above its own target; its time is not shown", line)

    def test_lookup_checks_that_the_header_hashes_to_the_block_hash(self):
        class FakeTransport(object):
            def __init__(self, header_hex, block_hash):
                self.header_hex, self.block_hash = header_hex, block_hash

            def http(self, key, url, **kw):
                body = self.block_hash if "block-height" in url else self.header_hex
                return {"status": 200, "body": body.encode(), "headers": [], "t_send": 0, "rtt_s": 0}

        with open(os.path.join(FIX, "btc-tip-header.json"), encoding="utf-8") as f:
            fx = json.load(f)
        raw_hex = fx.get("header_hex") or fx.get("raw") or fx.get("header")
        self.assertTrue(raw_hex, "fixture has a raw header")
        good = tw.btc_check_header(bytes.fromhex(raw_hex))
        ok = tw.btc_height_lookup(FakeTransport(raw_hex, good["hash"]), 975723, 1.0)
        self.assertNotIn("error", ok)
        self.assertTrue(ok["pow_ok"])
        self.assertEqual(ok["time_unix"], good["time"])
        bad = tw.btc_height_lookup(FakeTransport(raw_hex, "00" * 32), 975723, 1.0)
        self.assertIn("error", bad)


class CutoffHeightReviewTests(unittest.TestCase):
    """Defects found by the check of the late code (final/check-late-code.md)."""

    BEST = 1794616672.0

    class Fake(object):
        """Answers /block-height/N with a hash and /block/<hash>/header with a header, per API."""

        def __init__(self, per_base=None, status=200):
            self.per_base = per_base or {}
            self.status = status
            self.keys = []

        def http(self, key, url, **kw):
            self.keys.append(key)
            base = [b for _, b in tw.BITCOIN_SOURCES if url.startswith(b)][0]
            raw_hex, bhash = self.per_base[base]
            body = bhash if "block-height" in url else raw_hex
            return {"status": self.status, "body": body.encode(), "headers": [], "t_send": 0, "rtt_s": 0}

    @staticmethod
    def forged(when):
        # Regtest difficulty (bits 0x207fffff): about one header in two meets its own target.
        for nonce in range(1 << 20):
            raw = struct.pack("<I", 0x20000000) + bytes(64) + struct.pack("<III", when, 0x207FFFFF, nonce)
            c = tw.btc_check_header(raw)
            if c["pow_ok"]:
                return raw.hex(), c["hash"]
        raise AssertionError("no forged header found")

    def test_forged_low_difficulty_header_is_refused(self):
        # Finding 1: a header mined at trivial difficulty used to print its made-up date.
        raw_hex, h = self.forged(1700000000)  # 2023-11-14
        fake = self.Fake({b: (raw_hex, h) for _, b in tw.BITCOIN_SOURCES})
        ch = tw.btc_height_lookup(fake, 953000, 1.0)
        self.assertIn("below the floor", ch["refused"])
        line = tw.cutoff_height_line(ch, 975729, self.BEST)
        self.assertIn("was refused", line)
        self.assertNotIn("2023-11-14", line)

    def test_floor_follows_the_height(self):
        self.assertEqual(tw.height_difficulty_floor(0), 1.0)
        self.assertEqual(tw.height_difficulty_floor(953000), tw.DIFFICULTY_FLOOR)
        self.assertLess(tw.height_difficulty_floor(690000), 1.4e13)  # the 2021 drop was about 1.39e13

    def test_future_header_time_is_refused(self):
        ch = {"height": 953000, "time_unix": int(self.BEST + 3 * 3600), "time_iso": tw.iso(self.BEST + 3 * 3600),
              "pow_ok": True}
        line = tw.cutoff_height_line(ch, 975729, self.BEST)
        self.assertIn("more than 2 h after the time on the first line", line)
        self.assertNotIn("days before", line)

    def test_two_apis_naming_different_blocks_are_refused(self):
        blocks = json.loads(base64.b64decode(exchange("GET https://mempool.space/api/blocks")["response"]))
        heads = [(tw.btc_header_from_json(b).hex(), b["id"]) for b in blocks[:2]]
        fake = self.Fake({tw.BITCOIN_SOURCES[0][1]: heads[0], tw.BITCOIN_SOURCES[1][1]: heads[1]})
        ch = tw.btc_height_lookup(fake, 975000, 1.0)
        self.assertEqual(ch["refused"], "the two APIs name different blocks for that height")
        same = self.Fake({b: heads[0] for _, b in tw.BITCOIN_SOURCES})
        ch = tw.btc_height_lookup(same, 975000, 1.0)
        self.assertNotIn("refused", ch)
        self.assertEqual(ch["sources"], ["mempool.space", "blockstream.info"])

    def test_replay_keys_name_the_height(self):
        # Finding 4: a recording made for one height must not answer another.
        raw_hex, h = self.forged(1700000000)
        fake = self.Fake({b: (raw_hex, h) for _, b in tw.BITCOIN_SOURCES})
        tw.btc_height_lookup(fake, 900000, 1.0)
        self.assertTrue(fake.keys)
        self.assertTrue(all("900000" in k for k in fake.keys), fake.keys)

    def test_lookup_errors_keep_their_message(self):
        # Finding 7: "HTTP 400" used to become "OSError".
        ch = tw.btc_height_lookup(self.Fake({b: ("", "") for _, b in tw.BITCOIN_SOURCES}, status=400), 5, 1.0)
        self.assertIn("HTTP 400", ch["error"])

    def test_negative_height_is_a_usage_error(self):
        # Finding 5.
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            tw.main(["--no-network", "--cutoff-height", "-5"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("a block height is 0 or more", err.getvalue())


class RoughtimeTypeTests(unittest.TestCase):
    def test_wrong_message_type_is_named(self):
        # Late-code check 8: a wrong top-level TYPE failed with the bare text "failed: ".
        e = exchange("udp time.txryan.com:2002 roughtime")
        req, data = base64.b64decode(e["request"]), base64.b64decode(e["response"])
        srv = tw.ROUGHTIME_SERVERS[1]
        ex = {"srv": srv, "pub": base64.b64decode(srv["key"]), "nonce_from": "run nonce",
              "nonce": tw.rt_decode(req[12:])["NONC"], "pkt": req, "data": data, "t_send": 0.0, "rtt": 0.05,
              "m_send": 0.0}
        top = tw.rt_decode(data[12:12 + struct.unpack_from("<I", data, 8)[0]])
        top["TYPE"] = struct.pack("<I", 7)
        body = tw.rt_encode(top)
        ex["data"] = b"ROUGHTIM" + struct.pack("<I", len(body)) + body
        r = tw.roughtime_records([ex])[0]
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "failed: message type")
        self.assertIs(r["detail"]["type_ok"], False)


class SerialSchedulingTests(unittest.TestCase):
    """Under a clock-faking preload library the witnesses run one after another."""

    def tearDown(self):
        tw.SERIAL = False
        tw.SERIAL_DEADLINE = None
        tw.SERIAL_BUDGET_S = None

    def test_preload_names_are_detected(self):
        with mock.patch.dict(os.environ, {"FAKETIME": "@2026-06-17 12:00:00"}):
            self.assertTrue(tw.clock_faking_preload())
        with mock.patch.dict(os.environ, {"DYLD_INSERT_LIBRARIES": "/x/libfaketime.1.dylib"}):
            self.assertTrue(tw.clock_faking_preload())
        env = {k: v for k, v in os.environ.items() if k not in tw.PRELOAD_VARS and k != "FAKETIME"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(tw.clock_faking_preload())

    def test_serial_runs_in_the_calling_thread_in_order(self):
        tw.SERIAL = True
        seen = []

        def job(n):
            def fn():
                seen.append((n, threading.get_ident()))
                if n == "b":
                    raise ValueError("boom")
                return n.upper()
            return fn

        out = tw.run_in_threads([(n, job(n)) for n in "abc"], cap=0.0)
        self.assertEqual([n for n, _ in seen], ["a", "b", "c"])
        self.assertTrue(all(ident == threading.get_ident() for _, ident in seen))
        self.assertEqual(out["a"], ("A", None))
        self.assertIsInstance(out["b"][1], ValueError)
        self.assertEqual(out["c"], ("C", None))

    def test_serial_budget_skips_the_jobs_left(self):
        # Late-code check 3: serial mode had no bound on the whole run.
        tw.SERIAL = True
        tw.SERIAL_BUDGET_S = 5.0
        tw.SERIAL_DEADLINE = tw.unfaked_seconds() + 60.0

        def spend():
            tw.SERIAL_DEADLINE = tw.unfaked_seconds() - 1.0
            return "spent"

        out = tw.run_in_threads([("a", spend), ("b", lambda: "never")], cap=None)
        self.assertEqual(out["a"], ("spent", None))
        self.assertIsInstance(out["b"][1], TimeoutError)
        self.assertIn("run budget of 5s spent (serial mode)", str(out["b"][1]))
        # No new network exchange starts either (this raises before any socket is made).
        with self.assertRaises(TimeoutError):
            tw.Transport("live").http("k", "https://example.invalid/", timeout=0.1)
        with self.assertRaises(TimeoutError):
            tw.Transport("live").udp("k", "example.invalid", 123, b"x", 0.1)

    def test_serial_mode_lets_ctrl_c_through(self):
        # Claims check m8: KeyboardInterrupt used to become the job's error.
        tw.SERIAL = True

        def stop():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            tw.run_in_threads([("a", stop), ("b", lambda: 1)], cap=None)

    def test_mapped_faketime_library_is_detected(self):
        # Late-code check 9: libfaketime from /etc/ld.so.preload sets no variable.
        with tempfile.NamedTemporaryFile("w", suffix=".maps", delete=False) as f:
            f.write("7f00-7f01 r-xp 00000000 08:01 1 /usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1\n")
        try:
            self.assertTrue(tw.faketime_mapped(f.name))
        finally:
            os.unlink(f.name)
        self.assertFalse(tw.faketime_mapped(os.path.join(FIX, "does-not-exist")))
        env = {k: v for k, v in os.environ.items() if k not in tw.PRELOAD_VARS and k != "FAKETIME"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(tw, "faketime_mapped", return_value=True):
            self.assertTrue(tw.clock_faking_preload())
            rec = tw.local_witness()
        self.assertIn("faketime_env", rec["detail"]["flags"])
        self.assertIn("mapped_library", rec["detail"]["env_hints"])

    def test_json_says_which_bound_applied(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tw.main(["--json", "--quick", "--rate-seconds", "0.05", "--replay", RECORD])
        loc = json.loads(buf.getvalue())["local"]
        if tw.SERIAL:
            self.skipTest("this test process runs under a clock-faking library")
        self.assertEqual(loc["witnesses_ran"], "in parallel threads")
        self.assertIsInstance(loc["whole_run_cap_s"], float)
        self.assertIsNone(loc["serial_run_budget_s"])

    def test_signatures_are_not_checked_in_the_exchange_step(self):
        # roughtime_exchanges does the network part only; the Ed25519 checks happen in roughtime_records.
        tr = tw.Transport("replay", RECORD)
        with mock.patch.object(tw, "ed25519_verify", side_effect=AssertionError("checked too early")):
            exs = tw.roughtime_exchanges(tr, 1.0, os.urandom(32))
        self.assertEqual(len(exs), len(tw.ROUGHTIME_SERVERS))
        recs = tw.roughtime_records(exs)
        self.assertTrue(all(r["signed"] and not r["nonce_bound"] for r in recs))


if __name__ == "__main__":
    unittest.main()
