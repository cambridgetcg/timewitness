"""Offline tests for time brackets ("stamps"). Run: python3 -I -m unittest discover -s tests

The stamps in tests/fixtures/stamps/ were made live on 2026-11-23 with
`timewitness.py --stamp` against roughtime.se and time.txryan.com, by
tests/fixtures/stamps/make_stamp_fixtures.py (its log is make-log.json):

  o1.json ... o5.json   stamps of m1.txt ... m5.txt. o2 references o1, o3
                        references o2, o4 was made right after o3 with no
                        reference, o5 about 15 s later.
  recorded.json         a stamp of m1.txt made with --record stamp-record.json
  widths-10.jsonl       ten stamps made one after another; the README's
                        widths are computed from them here.
  faked-june.json       a stamp of m1.txt made by hand, under
                        `faketime '2026-06-17 12:00:00'`, for the README
                        example (not by the script).

Two honest servers cannot be made to contradict each other, so the tests for
that case use made-up servers whose keys are made in this file and patched in
as the pinned keys.
"""
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import statistics
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import timewitness as tw  # noqa: E402

ST = os.path.join(HERE, "fixtures", "stamps")
README = os.path.join(os.path.dirname(HERE), "README.md")


def path(name):
    return os.path.join(ST, name)


def load(name):
    with open(path(name), encoding="utf-8") as f:
        return json.load(f)


def raw(name):
    with open(path(name), "rb") as f:
        return f.read()


def b64d(s):
    return base64.b64decode(s)


def b64e(b):
    return base64.b64encode(b).decode()


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = tw.main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Made-up Roughtime servers (RFC 10049 version 1 rules), signed here.

def _encode_point(P):
    zi = pow(P[2], tw._P - 2, tw._P)
    x, y = P[0] * zi % tw._P, P[1] * zi % tw._P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def ed25519_public(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little") & ((1 << 254) - 8) | (1 << 254)
    return _encode_point(tw._pt_mul(a, tw._G))


def ed25519_sign(seed, msg):
    """RFC 8032 section 5.1.6 signing, for the made-up servers only."""
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little") & ((1 << 254) - 8) | (1 << 254)
    A = _encode_point(tw._pt_mul(a, tw._G))
    r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % tw._L
    R = _encode_point(tw._pt_mul(r, tw._G))
    k = int.from_bytes(hashlib.sha512(R + A + msg).digest(), "little") % tw._L
    return R + ((r + k * a) % tw._L).to_bytes(32, "little")


T0 = 1795000000  # a fixed made-up server time


class FakeRoughtime(object):
    def __init__(self, name, now=T0, radius=1):
        self.name = name
        self.root = hashlib.sha256(b"root key of " + name.encode()).digest()
        self.dele = hashlib.sha256(b"online key of " + name.encode()).digest()
        self.dele_pub = ed25519_public(self.dele)
        self.now = now
        self.radius = radius
        self.entry = {"name": name, "host": name, "port": 2002, "operator": "test",
                      "key": b64e(ed25519_public(self.root))}

    def answer(self, request):
        nonce, _ = tw.rt_parse_request(request)
        ctx_dele, ctx_srep = tw.ROUGHTIME_RULES[1]
        q = lambda n: struct.pack("<Q", n)  # noqa: E731
        i = lambda n: struct.pack("<I", n)  # noqa: E731
        dele = tw.rt_encode({"MINT": q(self.now - 86400), "MAXT": q(self.now + 86400), "PUBK": self.dele_pub})
        cert = tw.rt_encode({"DELE": dele, "SIG": ed25519_sign(self.root, ctx_dele + dele)})
        srep = tw.rt_encode({"VER": i(1), "RADI": i(self.radius), "MIDP": q(self.now), "VERS": i(1),
                             "ROOT": tw.rt_hash(b"\x00" + request)})
        body = tw.rt_encode({"SIG": ed25519_sign(self.dele, ctx_srep + srep), "NONC": nonce, "TYPE": i(1),
                             "PATH": b"", "SREP": srep, "CERT": cert, "INDX": i(0)})
        return b"ROUGHTIM" + i(len(body)) + body


class FakeNet(object):
    """Stands in for Transport: every UDP exchange goes to a made-up server."""
    label = "live"

    def __init__(self, *servers):
        self.by_host = {s.name: s for s in servers}

    def udp(self, key, host, port, payload, timeout):
        return self.by_host[host].answer(payload), time.time(), 0.01

    def save(self):
        pass


@contextlib.contextmanager
def pinned(*servers):
    with mock.patch.object(tw, "ROUGHTIME_SERVERS", [s.entry for s in servers]):
        yield


# ---------------------------------------------------------------------------

class StampLayoutTests(unittest.TestCase):
    def test_core_layout(self):
        p, b1, b2, r = (bytes([n]) * 32 for n in (1, 2, 3, 4))
        core = tw.stamp_core(p, [b1, b2], [r])
        self.assertEqual(core, b"timewitness stamp v1\x00" + p + b"\x02\x00\x00\x00" + b1 + b2
                         + b"\x01\x00\x00\x00" + r)
        # A beacon moved into the reference list gives another core.
        self.assertNotEqual(core, tw.stamp_core(p, [b1], [b2, r]))
        with self.assertRaises(ValueError):
            tw.stamp_core(p, [b1[:31]], [])

    def test_recorded_commitment_is_recomputed_from_the_exact_answer_bytes(self):
        d = load("o2.json")
        beacons = [hashlib.sha512(b64d(s["beacon"]["response_b64"])).digest()[:32] for s in d["servers"]]
        core = tw.stamp_core(bytes.fromhex(d["payload_sha256"]), beacons, [bytes.fromhex(r) for r in d["refs"]])
        self.assertEqual(hashlib.sha512(core).digest()[:32].hex(), d["commitment"])
        self.assertEqual(tw.stamp_check(d)["commitment"], d["commitment"])

    def test_stamp_holds_no_payload_and_no_local_details(self):
        d = load("o1.json")
        self.assertEqual(set(d), {"format", "tool_version", "payload_sha256", "refs", "commitment", "servers",
                                  "self_reported"})
        self.assertEqual(set(d["servers"][0]), {"name", "key", "beacon", "seal"})
        self.assertNotIn(raw("m1.txt").decode().strip(), json.dumps(d))
        self.assertIn("not evidence", d["self_reported"]["note"])

    def test_request_parser(self):
        nonce = os.urandom(32)
        pkt = tw.rt_build_request(nonce, os.urandom(32))
        self.assertEqual(tw.rt_parse_request(pkt), (nonce, tw.ROUGHTIME_OFFER))
        for bad in (pkt[:-4], b"ROUGHTIX" + pkt[8:], pkt[:8] + struct.pack("<I", 4) + pkt[12:]):
            with self.assertRaises(ValueError):
                tw.rt_parse_request(bad)


class StampCheckTests(unittest.TestCase):
    def test_good_stamp(self):
        r = tw.stamp_check(load("o1.json"), raw("m1.txt"))
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual(r["problems"], [])
        self.assertTrue(r["payload_match"])
        self.assertEqual((r["beacons_counted"], r["seals_counted"]), (2, 2))
        self.assertEqual([s["name"] for s in r["servers"]], ["roughtime.se", "time.txryan.com"])
        # The combined window is the latest not-before and the earliest existed-by.
        self.assertEqual(r["not_before_unix"], max(s["not_before_unix"] for s in r["servers"]))
        self.assertEqual(r["existed_by_unix"], min(s["existed_by_unix"] for s in r["servers"]))
        for s in r["servers"]:
            self.assertEqual(s["not_before_unix"], s["beacon"]["time_unix"] - s["beacon"]["radius_s"])
            self.assertEqual(s["existed_by_unix"], s["seal"]["time_unix"] + s["seal"]["radius_s"])
            self.assertTrue(s["seal"]["nonce_is_commitment"])
        self.assertGreaterEqual(r["width_s"], 0)
        self.assertLess(r["width_s"], 10)

    def test_every_recorded_stamp_verifies(self):
        for n in ("o1", "o2", "o3", "o4", "o5"):
            self.assertTrue(tw.stamp_check(load(n + ".json"), raw("m%s.txt" % n[1]))["valid"], n)
        self.assertTrue(tw.stamp_check(load("recorded.json"), raw("m1.txt"))["valid"])

    def test_payload_changed_by_one_byte(self):
        p = bytearray(raw("m1.txt"))
        p[0] ^= 0x01
        r = tw.stamp_check(load("o1.json"), bytes(p))
        self.assertFalse(r["valid"])
        self.assertFalse(r["payload_match"])
        self.assertEqual(r["problems"], ["the payload's SHA-256 does not match the stamp"])

    def test_payload_hash_in_the_stamp_changed(self):
        d = load("o1.json")
        h = d["payload_sha256"]
        d["payload_sha256"] = ("0" if h[0] != "0" else "1") + h[1:]
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertIn("the commitment written in the stamp is not the one recomputed from its contents",
                      r["problems"])
        self.assertTrue(any(p.endswith("seal: the seal request's nonce is not this stamp's commitment")
                            for p in r["problems"]))

    def test_seal_taken_from_a_different_stamp(self):
        good, other = load("o1.json"), load("o5.json")
        d = copy.deepcopy(good)
        d["servers"][0]["seal"] = other["servers"][0]["seal"]
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertEqual(r["problems"], ["roughtime.se seal: the seal request's nonce is not this stamp's commitment"])
        # Only the answer swapped: it does not answer this request.
        d = copy.deepcopy(good)
        d["servers"][1]["seal"]["response_b64"] = other["servers"][1]["seal"]["response_b64"]
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertEqual(r["problems"], ["time.txryan.com seal: failed: nonce echo, Merkle proof over the request "
                                         "packet"])

    def test_beacon_answer_altered(self):
        good = load("o1.json")
        resp = b64d(good["servers"][0]["beacon"]["response_b64"])
        midp = struct.pack("<Q", tw.rt_verify(b"", b"", resp, b"", signatures=False)["midp"])
        self.assertEqual(resp.count(midp), 1)
        # A signed byte changed: the signature fails, and the commitment changes, so no seal matches.
        d = copy.deepcopy(good)
        d["servers"][0]["beacon"]["response_b64"] = b64e(resp.replace(midp, struct.pack(
            "<Q", struct.unpack("<Q", midp)[0] - 3600)))
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertIn("roughtime.se beacon: failed: response signature", r["problems"])
        self.assertIn("roughtime.se seal: the seal request's nonce is not this stamp's commitment", r["problems"])
        self.assertIn("time.txryan.com seal: the seal request's nonce is not this stamp's commitment", r["problems"])
        # One byte added after the message: the answer still verifies on its own,
        # but the beacon is the digest of the exact bytes, so the commitment changes.
        req = b64d(good["servers"][0]["beacon"]["request_b64"])
        pub = b64d(tw.ROUGHTIME_SERVERS[0]["key"])
        self.assertTrue(tw.rt_verify(req, tw.rt_parse_request(req)[0], resp + b"\x00", pub)["ok"])
        d = copy.deepcopy(good)
        d["servers"][0]["beacon"]["response_b64"] = b64e(resp + b"\x00")
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertNotIn("roughtime.se beacon", " ".join(r["problems"]))
        self.assertIn("roughtime.se seal: the seal request's nonce is not this stamp's commitment", r["problems"])

    def test_request_nonce_not_equal_to_the_commitment(self):
        # An earlier exchange reused as the seal, with the unsigned nonce echo in
        # its answer edited to read C. rt_verify alone accepts this: the echo is
        # outside the signed part, and the Merkle leaf is the request it is
        # given. With an old beacon too, this would backdate a stamp. The check
        # reads C from the request packet, which the signed root covers.
        d = load("o1.json")
        c = bytes.fromhex(d["commitment"])
        s0 = d["servers"][0]
        req = b64d(s0["beacon"]["request_b64"])
        resp = b64d(s0["beacon"]["response_b64"])
        nonce = tw.rt_parse_request(req)[0]
        self.assertEqual(resp.count(nonce), 1)
        edited = resp.replace(nonce, c)
        pub = b64d(tw.ROUGHTIME_SERVERS[0]["key"])
        self.assertTrue(tw.rt_verify(req, c, edited, pub)["ok"])
        s0["seal"] = {"request_b64": s0["beacon"]["request_b64"], "response_b64": b64e(edited)}
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertFalse(r["servers"][0]["seal"]["nonce_is_commitment"])
        self.assertEqual(r["problems"], ["roughtime.se seal: the seal request's nonce is not this stamp's commitment"])

    def test_reference_removed_or_added_after_stamping(self):
        # Removed, with the commitment field rewritten to match: the seals still
        # carry the old commitment.
        d = load("o2.json")
        self.assertEqual(d["refs"], [load("o1.json")["commitment"]])
        d["refs"] = []
        d["commitment"] = tw.stamp_check(d)["commitment"]
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertEqual(r["problems"], [
            "roughtime.se seal: the seal request's nonce is not this stamp's commitment",
            "time.txryan.com seal: the seal request's nonce is not this stamp's commitment",
            "no seal verified with this tool's pinned keys, so there is no existed-by"])
        # Added.
        d = load("o1.json")
        d["refs"] = [load("o5.json")["commitment"]]
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertIn("the commitment written in the stamp is not the one recomputed from its contents",
                      r["problems"])

    def test_unknown_key_or_name_is_not_checkable_and_not_counted(self):
        d = load("o1.json")
        d["servers"][1]["key"] = b64e(bytes(range(32)))
        r = tw.stamp_check(d)
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual((r["beacons_counted"], r["seals_counted"]), (1, 1))
        self.assertFalse(r["servers"][1]["checkable"])
        self.assertEqual(r["servers"][1]["note"], "not checkable with this tool's pinned keys (the stamp names a "
                                                  "different key); not counted")
        self.assertEqual(r["not_before_unix"], r["servers"][0]["not_before_unix"])
        d = load("o1.json")
        d["servers"][1]["name"] = "time.example"
        r = tw.stamp_check(d)
        self.assertTrue(r["valid"])
        self.assertIn("unknown server name", r["servers"][1]["note"])
        self.assertIn("time.example: not checkable", "\n".join(tw.stamp_lines(r)))
        # Nothing checkable: no window at all.
        d["servers"][0]["name"] = "roughtime.example"
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertIn("no beacon verified with this tool's pinned keys, so there is no not-before", r["problems"])

    def test_missing_seal_gives_a_not_before_only(self):
        d = load("o1.json")
        d["servers"][1]["seal"] = None
        r = tw.stamp_check(d)
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual((r["beacons_counted"], r["seals_counted"]), (2, 1))
        self.assertIsNone(r["servers"][1]["existed_by_unix"])
        d["servers"][0]["seal"] = None
        r = tw.stamp_check(d)
        self.assertFalse(r["valid"])
        self.assertIn("no seal verified with this tool's pinned keys, so there is no existed-by", r["problems"])

    def test_malformed_stamps_are_invalid_and_never_raise(self):
        good = load("o1.json")
        cases = [None, [], {}, dict(good, format="other"), dict(good, payload_sha256="xyz"), dict(good, servers=[]),
                 dict(good, refs="none"), dict(good, servers=[{"name": "roughtime.se"}])]
        d = copy.deepcopy(good)
        d["servers"][0]["beacon"]["response_b64"] = "not base64!"
        cases.append(d)
        d = copy.deepcopy(good)
        d["servers"][0]["seal"]["request_b64"] = b64e(b"ROUGHTIM" + b"\x00" * 8)
        cases.append(d)
        for c in cases:
            r = tw.stamp_check(c)
            self.assertFalse(r["valid"])
            self.assertTrue(r["problems"])


class StampMadeUpServerTests(unittest.TestCase):
    def test_signer_matches_rfc8032(self):
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        self.assertEqual(ed25519_public(seed).hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        self.assertEqual(ed25519_sign(seed, b"").hex(),
                         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46b"
                         "d25bf5f0595bbe24655141438e7a100b")

    def make(self, *servers, payload=b"hello", refs=()):
        with pinned(*servers):
            doc, notes = tw.stamp_make(FakeNet(*servers), payload, refs, 1.0)
            return doc, notes, tw.stamp_check(doc, payload)

    def test_two_honest_servers(self):
        a, b = FakeRoughtime("a.test"), FakeRoughtime("b.test", radius=3)
        doc, notes, r = self.make(a, b)
        self.assertEqual(notes, [])
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual((r["not_before_unix"], r["existed_by_unix"]), (T0 - 1, T0 + 1))
        # Without the made-up keys pinned, nothing is checkable.
        self.assertFalse(tw.stamp_check(doc)["valid"])

    def test_one_server_is_enough(self):
        a = FakeRoughtime("a.test")
        doc, notes, r = self.make(a)
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual(len(r["servers"]), 1)

    def test_two_servers_whose_windows_contradict(self):
        a, b = FakeRoughtime("a.test", now=T0 + 100), FakeRoughtime("b.test", now=T0)
        doc, notes, r = self.make(a, b)
        self.assertFalse(r["valid"])
        self.assertEqual((r["not_before_unix"], r["existed_by_unix"]), (T0 + 99, T0 + 1))
        self.assertEqual(r["problems"], ["the servers contradict each other: a.test gives not before %s, but b.test "
                                         "gives existed by %s, 98s earlier (more than the 1s tolerance)"
                                         % (tw.iso(T0 + 99), tw.iso(T0 + 1))])
        self.assertTrue(all(s["beacon"]["ok"] and s["seal"]["ok"] for s in r["servers"]))

    def test_crossing_within_the_tolerance(self):
        # a's window is the single second T0+2; b's ends at T0+1: they cross by 1 s.
        a, b = FakeRoughtime("a.test", now=T0 + 2, radius=0), FakeRoughtime("b.test", now=T0, radius=1)
        doc, notes, r = self.make(a, b)
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual(r["width_s"], -1)
        self.assertIn("cross by 1s, within the 1s tolerance", "\n".join(tw.stamp_lines(r)))
        a.now = T0 + 3
        self.assertFalse(self.make(a, b)[2]["valid"])

    def test_server_that_does_not_answer_is_left_out(self):
        a, b = FakeRoughtime("a.test"), FakeRoughtime("b.test")

        class HalfNet(FakeNet):
            def udp(self, key, host, port, payload, timeout):
                if host == "b.test":
                    raise OSError("timed out")
                return FakeNet.udp(self, key, host, port, payload, timeout)
        with pinned(a, b):
            doc, notes = tw.stamp_make(HalfNet(a, b), b"x", (), 1.0)
            r = tw.stamp_check(doc)
        self.assertTrue(r["valid"])
        self.assertEqual([s["name"] for s in doc["servers"]], ["a.test"])
        self.assertEqual(notes, ["b.test beacon: OSError: timed out"])
        with pinned(a, b), self.assertRaises(tw.StampError):
            tw.stamp_make(FakeNet(), b"x", (), 1.0)

    def test_reference_that_the_windows_contradict(self):
        # x is stamped while the servers say T0+100; y, which references x, while
        # they say T0. Each is then shown before the other.
        a = FakeRoughtime("a.test", now=T0 + 100)
        x, _, rx = self.make(a, payload=b"x")
        a.now = T0
        y, _, ry = self.make(a, payload=b"y", refs=[bytes.fromhex(rx["commitment"])])
        self.assertTrue(rx["valid"] and ry["valid"])
        with pinned(a):
            res = tw.stamp_order([("A", x), ("B", y)])
        self.assertTrue(res["contradiction"])
        self.assertTrue(res["pairs"][0]["result"].startswith("contradiction"))

    def test_command_line_stamp_and_check(self):
        a, b = FakeRoughtime("a.test"), FakeRoughtime("b.test", radius=3)
        td = tempfile.mkdtemp()
        msg, out = os.path.join(td, "msg.txt"), os.path.join(td, "msg.stamp.json")
        with open(msg, "wb") as f:
            f.write(b"a message\n")
        with pinned(a, b), mock.patch.object(tw, "Transport", lambda *x, **k: FakeNet(a, b)):
            code, so, se = run_main(["--stamp", msg, "--out", out])
            self.assertEqual(code, 0, se)
            self.assertTrue(so.startswith("timewitness stamp made: committed no earlier than %s and no later than %s "
                                          "(window 2s; beacon and seal from 2 of the 2 servers pinned here)\n"
                                          "written to %s; check it with --check-stamp %s\n"
                                          % (tw.iso(T0 - 1), tw.iso(T0 + 1), tw.scrub(out), tw.scrub(out))), so)
            code, so, se = run_main(["--stamp", msg])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(so)["format"], tw.STAMP_FORMAT)
            self.assertTrue(se.startswith("timewitness stamp made:"))
            code, so, se = run_main(["--check-stamp", out, "--payload", msg])
            self.assertEqual(code, 0)
            self.assertTrue(so.startswith("timewitness stamp VALID"))
            # A reference must itself verify.
            code, so, se = run_main(["--stamp", msg, "--ref", msg])
            self.assertEqual(code, 2)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn(td, text)
        self.assertNotIn("msg.txt", text)


class StampOrderTests(unittest.TestCase):
    def order(self, *names):
        return tw.stamp_order([(chr(65 + i), load(n)) for i, n in enumerate(names)])

    @staticmethod
    def pair(res, a, b):
        return [p for p in res["pairs"] if (p["a"], p["b"]) == (a, b)][0]

    def window(self, name):
        r = tw.stamp_check(load(name))
        return r["not_before_unix"], r["existed_by_unix"]

    def overlaps(self, x, y):
        (nx, ex), (ny, ey) = self.window(x), self.window(y)
        return not (ex + tw.STAMP_TOLERANCE_S < ny or ey + tw.STAMP_TOLERANCE_S < nx)

    def test_three_stamps_with_an_overlap_and_a_reference(self):
        # The recorded windows: o1, o2 and o4 overlap; o2 references o1.
        self.assertTrue(self.overlaps("o1.json", "o2.json"))
        self.assertTrue(self.overlaps("o1.json", "o4.json") and self.overlaps("o2.json", "o4.json"))
        res = self.order("o1.json", "o2.json", "o4.json")
        self.assertTrue(res["all_valid"])
        self.assertEqual(self.pair(res, "A", "B")["result"], "A before B")
        self.assertEqual(self.pair(res, "A", "B")["reasons"], ["B references A"])
        self.assertEqual(self.pair(res, "A", "C")["result"], "overlap: order unknown")
        self.assertEqual(self.pair(res, "B", "C")["result"], "overlap: order unknown")

    def test_windows_alone_give_an_order(self):
        self.assertFalse(self.overlaps("o1.json", "o5.json"))
        res = self.order("o1.json", "o2.json", "o5.json")
        self.assertEqual([p["result"] for p in res["pairs"]], ["A before B", "A before C", "B before C"])
        self.assertTrue(self.pair(res, "A", "C")["reasons"][0].startswith("A existed by "))
        res = self.order("o5.json", "o1.json")
        self.assertEqual(res["pairs"][0]["result"], "B before A")

    def test_chain_of_references(self):
        # o3 references o2, which references o1; o3 does not name o1, and their windows overlap.
        self.assertEqual(load("o3.json")["refs"], [load("o2.json")["commitment"]])
        self.assertTrue(self.overlaps("o1.json", "o3.json"))
        self.assertEqual(self.order("o1.json", "o3.json")["pairs"][0]["result"], "overlap: order unknown")
        res = self.order("o1.json", "o3.json", "o2.json")
        self.assertEqual(self.pair(res, "A", "B")["result"], "A before B")
        self.assertEqual(self.pair(res, "A", "B")["reasons"], ["through C"])

    def test_an_invalid_stamp_is_not_ordered(self):
        bad = load("o1.json")
        bad["refs"] = [load("o5.json")["commitment"]]
        res = tw.stamp_order([("A", bad), ("B", load("o5.json"))])
        self.assertFalse(res["all_valid"])
        self.assertEqual(res["pairs"][0]["result"], "not compared: A does not verify")

    def test_command_line(self):
        code, out, _ = run_main(["--order", path("o1.json"), path("o2.json"), path("o4.json")])
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "timewitness order: 3 stamps, 3 verify")
        self.assertIn("A before B (B references A)", lines)
        self.assertIn("A and C: overlap: order unknown", lines)
        code, out, _ = run_main(["--json", "--order", path("o1.json"), path("o5.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["pairs"][0]["earlier"], "A")
        td = tempfile.mkdtemp()
        bad = os.path.join(td, "bad.json")
        d = load("o1.json")
        d["payload_sha256"] = "0" * 64
        with open(bad, "w", encoding="utf-8") as f:
            json.dump(d, f)
        self.assertEqual(run_main(["--order", path("o1.json"), bad])[0], 1)
        self.assertEqual(run_main(["--order", path("o1.json")])[0], 2)


class StampCommandLineTests(unittest.TestCase):
    def test_check_exit_codes(self):
        code, out, _ = run_main(["--check-stamp", path("o1.json"), "--payload", path("m1.txt")])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("timewitness stamp VALID: committed no earlier than "))
        self.assertTrue(any(l.startswith("payload: SHA-256 ") and " matches " in l and l.endswith("m1.txt")
                            for l in out.splitlines()))
        self.assertIn("What it does not show:", out)
        code, out, _ = run_main(["--check-stamp", path("o1.json"), "--payload", path("m2.txt")])
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("timewitness stamp INVALID: the payload's SHA-256 does not match the stamp"))
        code, out, _ = run_main(["--check-stamp", path("o1.json"), "--json"])
        d = json.loads(out)
        self.assertEqual(code, 0)
        for k in ("valid", "problems", "commitment", "payload_sha256", "payload_match", "refs", "servers",
                  "not_before_unix", "existed_by_unix", "width_s", "proves", "does_not_prove"):
            self.assertIn(k, d)
        self.assertIsNone(d["payload_match"])
        self.assertEqual(run_main(["--check-stamp", path("no-such-stamp.json")])[0], 2)

    def test_usage_errors(self):
        for argv in (["--payload", path("m1.txt")], ["--out", "x.json"], ["--ref", path("o1.json")],
                     ["--check-stamp", path("o1.json"), "--all"], ["--check-stamp", path("o1.json"), "--replay", "x"],
                     ["--stamp", path("m1.txt"), "--order", path("o1.json"), path("o2.json")]):
            self.assertEqual(run_main(argv)[0], 2, argv)

    def test_replay_cannot_make_a_stamp(self):
        # The recording holds the four exchanges that made recorded.json.
        rec = load("stamp-record.json")["exchanges"]
        d = load("recorded.json")
        sent = [s["beacon"]["request_b64"] for s in d["servers"]] + [s["seal"]["request_b64"] for s in d["servers"]]
        self.assertEqual([e["request"] for e in rec], sent)
        # Replayed answers do not carry the new beacons' fresh nonces, so no stamp is made.
        code, out, err = run_main(["--stamp", path("m1.txt"), "--replay", path("stamp-record.json")])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("timewitness stamp FAILED: no Roughtime server gave a usable beacon"))
        self.assertIn("nonce echo, Merkle proof over the request packet", err)

    def test_no_network(self):
        code, out, err = run_main(["--stamp", path("m1.txt"), "--no-network"])
        self.assertEqual(code, 1)
        self.assertIn("network disabled", err)


class StampWidthTests(unittest.TestCase):
    """The README's width numbers, computed from the ten stored stamps."""

    def test_readme_numbers(self):
        rows, bad = [], 0
        with open(path("widths-10.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    bad += 1
        checks = [tw.stamp_check(r) for r in rows]
        ok = [c for c in checks if c["valid"]]
        widths = sorted(c["width_s"] for c in ok)
        per = {}
        same_second = 0
        for c in ok:
            for s in c["servers"]:
                per.setdefault(s["name"], []).append(s["existed_by_unix"] - s["not_before_unix"])
                if s["name"] == "roughtime.se" and s["beacon"]["time_unix"] == s["seal"]["time_unix"]:
                    same_second += 1
        both_se = sum(1 for c in ok if c["not_before_from"] == c["existed_by_from"] == "roughtime.se")
        with open(path("make-log.json"), encoding="utf-8") as f:
            log = json.load(f)
        secs = sorted(x["seconds"] for x in log if x["args"][0] == "--stamp" and x["exit"] == 0)

        def span(v):
            return "%g s" % min(v) if min(v) == max(v) else "%g to %g s" % (min(v), max(v))
        facts = [
            "%d stamps made one after another on 2026-11-23 from one machine, %d rows failed to parse and %d "
            "verified" % (len(rows), bad, len(ok)),
            "The combined window was %s wide (minimum %g s, median %g s, maximum %g s)" % (
                span(widths), widths[0], statistics.median(widths), widths[-1]),
            "roughtime.se alone gave windows of %s, and time.txryan.com alone %s" % (
                span(per["roughtime.se"]), span(per["time.txryan.com"])),
            "In %d of %d both bounds came from roughtime.se" % (both_se, len(ok)),
            "its beacon and seal carried the same second in %d of %d" % (same_second, len(ok)),
            "Each `--stamp` command took %.2f to %.2f s (%d commands, Python start-up included)" % (
                secs[0], secs[-1], len(secs)),
        ]
        self.assert_in_readme(facts)

    def assert_in_readme(self, facts):
        with open(README, encoding="utf-8") as f:
            readme = " ".join(f.read().split())
        for fact in facts:
            self.assertTrue(fact in readme, "README.md lacks this sentence, computed from the stamps: " + fact)

    def test_readme_faked_clock_and_delegation(self):
        # faked-june.json was made from m1.txt under `faketime '2026-06-17 12:00:00'`.
        r = tw.stamp_check(load("faked-june.json"), raw("m1.txt"))
        self.assertTrue(r["valid"])
        self.assertGreater(r["not_before_unix"] - r["self_reported_local_clock_unix"], 100 * 86400)
        dele = {}
        for s in load("o1.json")["servers"]:
            v = tw.rt_verify(b"", b"", b64d(s["beacon"]["response_b64"]), b"", signatures=False)
            dele[s["name"]] = (v["mint"], v["maxt"])
        se, tx = dele["roughtime.se"], dele["time.txryan.com"]
        self.assert_in_readme([
            "its self-reported clock reads %s, and its window runs from %s to %s" % (
                tw.iso(r["self_reported_local_clock_unix"]), tw.iso(r["not_before_unix"]),
                tw.iso(r["existed_by_unix"])),
            "roughtime.se's online key was valid from %s to %s (%d days), and time.txryan.com's for %d day" % (
                tw.iso(se[0])[:10], tw.iso(se[1])[:10], (se[1] - se[0]) // 86400, (tx[1] - tx[0]) // 86400),
        ])


class CountingNet(FakeNet):
    """FakeNet that counts its exchanges."""

    def __init__(self, *servers):
        FakeNet.__init__(self, *servers)
        self.calls = 0

    def udp(self, key, host, port, payload, timeout):
        self.calls += 1
        return FakeNet.udp(self, key, host, port, payload, timeout)


def no_constants(name):
    raise ValueError("not strict JSON: " + name)


class StampReviewFixTests(unittest.TestCase):
    """One test per fix made after the two reviews of 2026-11-23 (crypto and reader)."""

    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.td = td.name

    def write(self, data, name="s.json"):
        p = os.path.join(self.td, name)
        if not isinstance(data, (bytes, str)):
            data = json.dumps(data)
        with open(p, "wb") as f:
            f.write(data.encode("utf-8") if isinstance(data, str) else data)
        return p

    def make(self, *servers, payload=b"hello", refs=()):
        with pinned(*servers):
            doc, _ = tw.stamp_make(FakeNet(*servers), payload, refs, 1.0)
            return doc, tw.stamp_check(doc, payload)

    # crypto Major 1, reader M1: the unsigned self-reported clock.
    def test_edited_self_reported_clock_leaves_a_valid_stamp_valid(self):
        for value in (1e20, -1e13, float("nan"), float("inf"), 10 ** 40, "yesterday", True):
            d = load("o1.json")
            d["self_reported"]["local_clock_unix"] = value
            r = tw.stamp_check(d, raw("m1.txt"))
            self.assertTrue(r["valid"], (value, r["problems"]))
            self.assertIsNone(r["self_reported_local_clock_unix"])
            self.assertTrue(r["self_reported_unreadable"])
            self.assertIn("self-reported clock of the stamping machine: unreadable (not evidence; the check does not "
                          "use it)", tw.stamp_lines(r, "m1.txt"))
            json.dumps(r, allow_nan=False)
        d = load("o1.json")
        d["self_reported"]["local_clock_unix"] = 1e20
        p = self.write(d)
        code, out, err = run_main(["--check-stamp", p, "--payload", path("m1.txt")])
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("timewitness stamp VALID: "))
        code, out, _ = run_main(["--check-stamp", p, "--json"])
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out, parse_constant=no_constants)["self_reported_local_clock_unix"])

    # crypto Major 2: untrusted input must not crash or stall the checker.
    def test_oversized_deep_and_long_number_files_are_refused_quickly(self):
        good = raw("o1.json")
        text = good.decode()
        cases = [
            (good + b" " * tw.STAMP_MAX_FILE_BYTES, "the file is larger than 262144 bytes"),
            ("[" * 100000 + "]" * 100000, "the file nests deeper than 32 levels"),
            (text.rstrip()[:-1] + ', "extra": ' + "[" * 1000 + "]" * 1000 + "}", "the file nests deeper than 32"),
            (text.replace('"local_clock_unix": ', '"local_clock_unix": ' + "1" * 100000 + ", \"was\": "),
             "the file holds a number longer than 32 characters"),
        ]
        for data, why in cases:
            p = self.write(data)
            t0 = time.monotonic()
            code, out, err = run_main(["--check-stamp", p])
            self.assertLess(time.monotonic() - t0, 2.0, why)
            self.assertEqual((code, err), (1, ""), why)
            self.assertTrue(out.startswith("timewitness stamp INVALID: " + why), out[:200])

    def test_entry_and_packet_caps_apply_before_any_signature_check(self):
        good = load("o1.json")
        d = copy.deepcopy(good)
        d["servers"] = [copy.deepcopy(good["servers"][0]) for _ in range(250)]
        with mock.patch.object(tw, "ed25519_verify", side_effect=AssertionError("signature checked")):
            t0 = time.monotonic()
            r = tw.stamp_check(d)
            self.assertLess(time.monotonic() - t0, 1.0)
            self.assertEqual(r["problems"], ["servers has more than 16 entries"])
            d["servers"] = d["servers"][:2]
            self.assertEqual(tw.stamp_check(d)["problems"], ["servers[1] repeats the server name roughtime.se"])
            d = copy.deepcopy(good)
            resp = b64d(d["servers"][0]["seal"]["response_b64"])
            d["servers"][0]["seal"]["response_b64"] = b64e(resp + b"\x00" * 5000)
            self.assertEqual(tw.stamp_check(d)["problems"],
                             ["servers[0].seal.response_b64 is longer than 4096 bytes"])
        self.assertEqual(tw.stamp_loads(raw("o1.json")), (good, None))

    # crypto Major 3: one server listed twice at stamping time.
    def test_a_server_listed_twice_is_refused(self):
        a = FakeRoughtime("a.test")
        with mock.patch.object(tw, "ROUGHTIME_SERVERS", [a.entry, a.entry]):
            doc, _ = tw.stamp_make(FakeNet(a), b"x", (), 1.0)
        self.assertEqual([s["name"] for s in doc["servers"]], ["a.test", "a.test"])
        with pinned(a):
            r = tw.stamp_check(doc)
        self.assertFalse(r["valid"])
        self.assertEqual(r["problems"], ["servers[1] repeats the server name a.test"])
        self.assertEqual((r["beacons_counted"], r["seals_counted"]), (0, 0))

    # crypto Minor 4: the verdict depends on the bytes only.
    def test_repeated_keys_and_nan_are_refused(self):
        text = raw("o1.json").decode()
        dup = text.replace('{\n "format"', '{\n "payload_sha256": "%s",\n "format"' % ("0" * 64), 1)
        self.assertNotEqual(dup, text)
        self.assertEqual(json.loads(dup), load("o1.json"))  # a plain reader keeps the last copy and sees a good stamp
        code, out, _ = run_main(["--check-stamp", self.write(dup), "--payload", path("m1.txt")])
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("timewitness stamp INVALID: the file repeats a key inside one object"))
        nan = text.replace('"local_clock_unix": ', '"local_clock_unix": NaN, "was": ')
        code, out, _ = run_main(["--check-stamp", self.write(nan)])
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("timewitness stamp INVALID: the file holds NaN or Infinity, which are not JSON"))

    # crypto Minor 5: a pinned key that signs an absurd time.
    def test_absurd_signed_times_are_invalid_and_never_raise(self):
        far = FakeRoughtime("far.test", now=2 ** 62)
        wide = FakeRoughtime("wide.test", radius=2 ** 32 - 1)
        honest = FakeRoughtime("b.test")
        for servers in ((far,), (far, honest), (wide, honest)):
            doc, r = self.make(*servers)
            self.assertFalse(r["valid"])
            self.assertIn("is outside the years 1970 to 9999", " ".join(r["problems"]))
            with pinned(*servers):
                code, out, _ = run_main(["--check-stamp", self.write(doc)])
                self.assertEqual(code, 1)
                self.assertTrue(out.startswith("timewitness stamp INVALID: "))
                self.assertEqual(run_main(["--json", "--check-stamp", self.write(doc)])[0], 1)

    # crypto Minor 6: contradiction lines name the pair; derived ones are marked.
    def test_contradiction_lines_name_the_pair(self):
        a = FakeRoughtime("a.test", now=T0 + 100)
        x, rx = self.make(a, payload=b"A")
        a.now = T0
        y, _ = self.make(a, payload=b"B", refs=[bytes.fromhex(rx["commitment"])])
        a.now = T0 + 50
        z, _ = self.make(a, payload=b"C")
        with pinned(a):
            res = tw.stamp_order([("A", x), ("B", y), ("C", z)])
            code, out, _ = run_main(["--order", self.write(x, "x.json"), self.write(y, "y.json"),
                                     self.write(z, "z.json")])
        self.assertTrue(res["contradiction"])
        derived = {(p["a"], p["b"]): p["derived"] for p in res["pairs"]}
        self.assertEqual(derived, {("A", "B"): False, ("A", "C"): True, ("B", "C"): True})
        bc = [p for p in res["pairs"] if (p["a"], p["b"]) == ("B", "C")][0]
        self.assertEqual(bc["b_before_a"], ["through A"])
        self.assertEqual(code, 1)
        lines = out.splitlines()
        for pair in ("A and B", "A and C", "B and C"):
            self.assertEqual(sum(1 for l in lines if l.startswith(pair + ": contradiction: ")), 1, pair)
        self.assertIn("B and C: contradiction: B before C (B existed by", out)
        self.assertIn("but C before B (through A)", out)
        self.assertIn("A contradiction means that at least one signed time in these stamps is wrong", out)

    # crypto Minor 7, reader L5: a reference is only 32 bytes at check time.
    def test_reference_wording(self):
        lines = tw.stamp_lines(tw.stamp_check(load("o2.json")))
        line = [l for l in lines if l.startswith("references: ")][0]
        self.assertEqual(line, "references: 1 inside the commitment (%s); where a reference equals another stamp's "
                               "commitment, this stamp was committed after that one (--order checks this)"
                         % load("o1.json")["commitment"][:16])

    # crypto Minor 8, reader L8: standard input can be read once.
    def test_standard_input_given_twice_is_a_usage_error(self):
        for argv in (["--check-stamp", "-", "--payload", "-"], ["--stamp", "-", "--ref", "-"],
                     ["--order", "-", "-"], ["--order", "-", path("o1.json"), "-"]):
            code, _, err = run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("standard input (-) can be read only once", err)

    # crypto Minor 9: an entry with no key is not checkable.
    def test_entry_without_a_key_is_not_checkable(self):
        d = load("o1.json")
        del d["servers"][1]["key"]
        r = tw.stamp_check(d)
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual((r["beacons_counted"], r["seals_counted"]), (1, 1))
        self.assertEqual(r["servers"][1]["note"], "not checkable with this tool's pinned keys (the stamp names no "
                                                  "key); not counted")
        del d["servers"][0]["key"]
        self.assertFalse(tw.stamp_check(d)["valid"])

    # reader M2: VALID without --payload says so on the first line.
    def test_valid_without_payload_says_so_first(self):
        code, out, _ = run_main(["--check-stamp", path("o1.json")])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("timewitness stamp VALID (payload not compared): committed no earlier than "))
        code, out, _ = run_main(["--check-stamp", path("o1.json"), "--payload", path("m1.txt")])
        self.assertTrue(out.startswith("timewitness stamp VALID: committed no earlier than "))

    # reader M3: crossing bounds are said in every output, never "window 0s".
    def test_crossing_bounds_are_shown_in_every_output(self):
        a, b = FakeRoughtime("a.test", now=T0 + 2, radius=0), FakeRoughtime("b.test", now=T0, radius=1)
        doc, r = self.make(a, b)
        self.assertTrue(r["valid"])
        self.assertEqual((r["width_s"], r["bounds_cross_s"]), (-1, 1))
        cross = "the servers' bounds cross by 1s, within the 1s tolerance for whole-second times"
        self.assertIn(cross, tw.stamp_lines(r)[0])
        later, _ = self.make(FakeRoughtime("a.test", now=T0 + 60), FakeRoughtime("b.test", now=T0 + 60))
        msg = self.write(b"hello", "msg.txt")
        with pinned(a, b), mock.patch.object(tw, "Transport", lambda *x, **k: FakeNet(a, b)):
            outputs = [run_main(["--stamp", msg])[2],
                       run_main(["--check-stamp", self.write(doc)])[1],
                       run_main(["--order", self.write(doc), self.write(later, "later.json")])[1]]
        for o in outputs:
            self.assertIn("cross by 1s", o)
            self.assertNotIn("window 0s", o)
            self.assertNotIn("window -", o)
        self.assertEqual(self.make(a, b)[1]["bounds_cross_s"], 1)
        self.assertEqual(tw.stamp_check(load("o1.json"))["bounds_cross_s"], 0)

    # reader M4: the written commitment is required, so a stamp can be named by it.
    def test_commitment_field_is_required(self):
        d = load("o1.json")
        del d["commitment"]
        self.assertEqual(tw.stamp_check(d)["problems"], ["commitment is not 64 lower-case hex digits"])

    # Found while fixing: names are printed, so they must be host names.
    def test_server_name_must_be_a_host_name(self):
        d = load("o1.json")
        d["servers"][1]["name"] = "x\ntimewitness stamp VALID"
        r = tw.stamp_check(d)
        self.assertEqual(r["problems"], ["servers[1].name is not a host name"])
        self.assertNotIn("\ntimewitness stamp VALID", "\n".join(tw.stamp_lines(r)))

    # reader L6: the count names the servers pinned here, not the ones listed in the stamp.
    def test_count_names_the_pinned_servers(self):
        a, b = FakeRoughtime("a.test"), FakeRoughtime("b.test")

        class HalfNet(FakeNet):
            def udp(self, key, host, port, payload, timeout):
                if host == "b.test":
                    raise OSError("timed out")
                return FakeNet.udp(self, key, host, port, payload, timeout)
        with pinned(a, b):
            doc, _ = tw.stamp_make(HalfNet(a, b), b"x", (), 1.0)
            r = tw.stamp_check(doc)
        self.assertEqual(r["servers_pinned_here"], 2)
        self.assertIn("(window 2s; beacon and seal from 1 of the 2 servers pinned here)", tw.stamp_lines(r)[0])
        d = load("o1.json")
        d["servers"][1]["seal"] = None
        self.assertIn("beacons from 2 and seals from 1 of the 2 servers pinned here",
                      tw.stamp_lines(tw.stamp_check(d))[0])

    # reader L7 and L2: a failed --out keeps the stamp; the hint names the flag, not a command.
    def test_out_that_cannot_be_written(self):
        a, b = FakeRoughtime("a.test"), FakeRoughtime("b.test")
        msg = self.write(b"a message\n", "msg.txt")
        net = CountingNet(a, b)
        with pinned(a, b), mock.patch.object(tw, "Transport", lambda *x, **k: net):
            code, _, err = run_main(["--stamp", msg, "--out", os.path.join(self.td, "no-such-dir", "s.json")])
            self.assertEqual((code, net.calls), (2, 0))
            self.assertEqual(run_main(["--stamp", msg, "--out", self.td])[0], 2)
            self.assertEqual(net.calls, 0)
            with mock.patch.object(tw, "_write_text", side_effect=PermissionError(13, "denied")):
                code, so, se = run_main(["--stamp", msg, "--out", os.path.join(self.td, "s.json")])
            self.assertEqual(code, 2)
            self.assertIn("the stamp is on standard output instead", se)
            self.assertTrue(tw.stamp_check(json.loads(so), b"a message\n")["valid"])
            code, so, _ = run_main(["--stamp", msg, "--out", os.path.join(self.td, "s.json")])
            self.assertEqual(code, 0)
            self.assertIn("; check it with --check-stamp ", so)
            self.assertNotIn("timewitness --check-stamp", so)

    # reader L9: --no-network is harmless offline; --timeout has no effect there and is refused.
    def test_offline_flags(self):
        self.assertEqual(run_main(["--check-stamp", path("o1.json"), "--no-network"])[0], 0)
        self.assertEqual(run_main(["--order", path("o1.json"), path("o5.json"), "--no-network"])[0], 0)
        self.assertEqual(run_main(["--check-stamp", path("o1.json"), "--timeout", "3"])[0], 2)
        self.assertEqual(run_main(["--order", path("o1.json"), path("o5.json"), "--timeout", "3"])[0], 2)

    def test_reference_count_is_capped(self):
        code, _, err = run_main(["--stamp", path("m1.txt")] + ["--ref", path("o1.json")] * 257)
        self.assertEqual(code, 2)
        self.assertIn("at most 256 --ref", err)
        d = load("o1.json")
        d["refs"] = ["0" * 64] * 257
        self.assertEqual(tw.stamp_check(d)["problems"], ["refs holds more than 256 references"])

    # reader M4, M5, L1, L3, L4, L11, L12, L13, L14: README wording.
    def test_readme_wording(self):
        with open(README, encoding="utf-8") as f:
            readme = " ".join(f.read().split())
        self.assertFalse("so that an altered stamp does not read as valid" in readme)
        for s in ("Identify a stamp by its `commitment`, not by a hash of the file",
                  "That the stamper ever had the bytes",
                  "a lower bound on when the commitment was made",
                  "an upper bound on when the commitment existed",
                  "the same bytes as `tests/fixtures/stamps/m1.txt`",
                  hashlib.sha256(raw("m1.txt")).hexdigest(),
                  "faketime reads that time in the machine's time zone",
                  "Always pass `--payload` when you hold the message",
                  "the stamp fixtures made live on 2026-11-23",
                  "It can also stamp a message"):
            self.assertTrue(s in readme, "README.md lacks: " + s)


class StampParserReviewTests(unittest.TestCase):
    """One test per fix made after the adversarial review of the stamp reader (2026-11-23, second round).

    Each of these failed on the code before the fix.
    """

    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.td = td.name

    def write(self, data, name="s.json"):
        p = os.path.join(self.td, name)
        if not isinstance(data, (bytes, str)):
            data = json.dumps(data)
        with open(p, "wb") as f:
            f.write(data.encode("utf-8") if isinstance(data, str) else data)
        return p

    # Break 1: Python 3.9 read extra base64 padding as VALID, 3.15 as INVALID.
    def test_base64_must_be_in_its_one_standard_form(self):
        good = load("o1.json")
        cases = []
        d = copy.deepcopy(good)
        self.assertTrue(d["servers"][0]["seal"]["response_b64"].endswith("AAA="))
        d["servers"][0]["seal"]["response_b64"] += "="          # one more '=': same bytes on Python 3.9
        cases.append(("servers[0].seal.response_b64", d))
        for pad in ("=", "=="):                                  # padding alone: empty bytes on Python 3.9
            d = copy.deepcopy(good)
            d["servers"][1]["beacon"]["response_b64"] = pad
            cases.append(("servers[1].beacon.response_b64", d))
        # Non-zero unused bits in the last character: the same bytes on every Python, another text.
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        d = copy.deepcopy(good)
        req = d["servers"][0]["seal"]["request_b64"]
        self.assertEqual((len(b64d(req)) % 3, req[-2:]), (1, "=="))  # 1024 bytes: the last character has 4 unused bits
        last = alphabet.index(req[-3])
        self.assertEqual(last & 0x0F, 0)
        odd = req[:-3] + alphabet[last | 1] + "=="
        self.assertEqual(b64d(odd), b64d(req))
        d["servers"][0]["seal"]["request_b64"] = odd
        cases.append(("servers[0].seal.request_b64", d))
        for field, doc in cases:
            r = tw.stamp_check(doc, raw("m1.txt"))
            self.assertFalse(r["valid"], field)
            self.assertEqual(r["problems"], ["%s is not base64" % field])
        self.assertTrue(tw.stamp_check(good, raw("m1.txt"))["valid"])
        # The same holds on the command line, so the verdict and the message do not depend on the Python version.
        code, out, _ = run_main(["--check-stamp", self.write(cases[0][1]), "--payload", path("m1.txt")])
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("timewitness stamp INVALID: servers[0].seal.response_b64 is not base64\n"))

    # Break 2: a file name holding a newline printed forged lines.
    def test_file_names_cannot_add_lines(self):
        try:
            forged = self.write(raw("o4.json"), "o4.json\nA before B (B references A)")
            pay = self.write(raw("m2.txt"), "m2.txt\ntimewitness stamp VALID: committed no earlier than "
                                            "2026-01-01T00:00:00Z")
        except (OSError, ValueError):
            self.skipTest("this file system refuses a newline in a file name")
        # o1 and o4 overlap and neither references the other.
        code, out, _ = run_main(["--order", path("o1.json"), forged])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertIn("A and B: overlap: order unknown", lines)
        self.assertFalse(any(l.startswith("A before B") for l in lines), out)
        self.assertIn("o4.json\\u000aA before B (B references A): committed ", out)
        code, out, _ = run_main(["--json", "--order", path("o1.json"), forged])
        self.assertEqual(json.loads(out)["stamps"][1]["file"], forged)   # JSON keeps the name as given
        code, out, _ = run_main(["--check-stamp", path("o1.json"), "--payload", pay])
        self.assertEqual(code, 1)
        self.assertEqual([l for l in out.splitlines() if l.startswith("timewitness stamp")],
                         ["timewitness stamp INVALID: the payload's SHA-256 does not match the stamp"])
        # A name in a usage error is printed the same way.
        code, _, err = run_main(["--check-stamp", os.path.join(self.td, "none\ntimewitness stamp VALID")])
        self.assertEqual(code, 2)
        self.assertFalse(any(l.startswith("timewitness stamp VALID") for l in err.splitlines()), err)
        self.assertIn("none\\u000atimewitness stamp VALID", err)
        # The rule: control, line-separator and direction-control characters, and lone surrogates.
        self.assertEqual(tw.printable_name("a\nb\r\x1b\x7f\x85\u2028\u2029\u202ec\udcff d.json"),
                         "a\\u000ab\\u000d\\u001b\\u007f\\u0085\\u2028\\u2029\\u202ec\\udcff d.json")
        self.assertEqual(tw.printable_name("o4 copy (2) é.json"), "o4 copy (2) é.json")

    # Break 3: --order took time growing with the cube of the number of files, valid or not.
    def test_order_count_is_capped_and_bad_files_cost_little(self):
        e = self.write(b"{}", "e.json")
        with mock.patch.object(tw, "_load_stamp", side_effect=AssertionError("read before the cap")):
            code, _, err = run_main(["--order"] + [e] * 65)
        self.assertEqual(code, 2)
        self.assertIn("at most 64 stamps with --order", err)
        code, out, _ = run_main(["--order"] + [e] * 64)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("timewitness order: 64 stamps, 0 verify\n"))
        # The chain step runs over stamps that verify only, so invalid ones cost little in-process too.
        t0 = time.monotonic()
        res = tw.stamp_order([("S%d" % i, {}) for i in range(400)])
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertEqual(len(res["pairs"]), 400 * 399 // 2)
        res = tw.stamp_order([("A", load("o1.json")), ("X", {}), ("C", load("o3.json")), ("B", load("o2.json"))])
        self.assertEqual([(p["a"], p["b"], p["result"], p["reasons"]) for p in res["pairs"] if p["earlier"]],
                         [("A", "C", "A before C", ["through B"]), ("A", "B", "A before B", ["B references A"]),
                          ("C", "B", "B before C", ["C references B"])])

    # Break 4: the same signature was verified again for every stamp that held it.
    def test_order_verifies_each_signature_once(self):
        real = tw.ed25519_verify
        names = ["o1.json", "o2.json", "o3.json", "o4.json", "o5.json"]
        with mock.patch.object(tw, "ed25519_verify", side_effect=real) as m:
            once = tw.stamp_order([(chr(65 + i), load(n)) for i, n in enumerate(names)])
            n_once = m.call_count
            m.reset_mock()
            many = tw.stamp_order([("S%d" % i, load(n)) for i, n in enumerate(names * 12)])
            self.assertEqual(m.call_count, n_once)
            seen = {(bytes(c[0][0]), bytes(c[0][1]), bytes(c[0][2])) for c in m.call_args_list}
            self.assertEqual(len(seen), m.call_count)
        self.assertTrue(once["all_valid"] and many["all_valid"])
        self.assertLess(n_once, 8 * len(names))   # delegation signatures are shared between stamps
        # stamp_check alone still checks every signature it meets.
        with mock.patch.object(tw, "ed25519_verify", side_effect=real) as m:
            tw.stamp_check(load("o1.json"))
            self.assertEqual(m.call_count, 8)

    # Break 5: --check-stamp - with standard input closed ended in a traceback.
    def test_closed_standard_input_is_a_usage_error(self):
        for argv in (["--check-stamp", "-"], ["--check-stamp", path("o1.json"), "--payload", "-"],
                     ["--order", "-", path("o1.json")], ["--stamp", "-", "--no-network"]):
            with mock.patch.object(sys, "stdin", None):
                code, out, err = run_main(argv)
            self.assertEqual((code, out), (2, ""), argv)
            self.assertIn("cannot read standard input (it is closed)", err)

    # Other observation: 1E400 is a number literal that reads as Infinity, which the README says is refused.
    def test_number_that_reads_as_infinity_is_refused(self):
        text = raw("o1.json").decode()
        for big in ("1E400", "-1e400", "1e309"):
            t = text.replace('"local_clock_unix": ', '"local_clock_unix": %s, "was": ' % big)
            self.assertNotEqual(t, text)
            code, out, _ = run_main(["--check-stamp", self.write(t), "--payload", path("m1.txt")])
            self.assertEqual(code, 1, big)
            self.assertTrue(out.startswith("timewitness stamp INVALID: the file holds a number too large to read as "
                                           "a finite number"), out[:200])
        t = text.replace('"local_clock_unix": ', '"local_clock_unix": 1e-400, "was": ')
        self.assertEqual(run_main(["--check-stamp", self.write(t), "--payload", path("m1.txt")])[0], 0)

    # Other observation: a very wide window printed as "window 2e+09s".
    def test_wide_window_is_printed_in_whole_seconds(self):
        a = FakeRoughtime("a.test", radius=10 ** 9)
        with pinned(a):
            doc, _ = tw.stamp_make(FakeNet(a), b"x", (), 1.0)
            r = tw.stamp_check(doc, b"x")
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual(r["width_s"], 2 * 10 ** 9)
        self.assertIn("(window 2000000000s; ", tw.stamp_lines(r)[0])
        self.assertIn("(window 2s; ", tw.stamp_lines(tw.stamp_check(load("o2.json")))[0])

    # Other observation: "A and B does not verify".
    def test_two_invalid_stamps_do_not_verify(self):
        res = tw.stamp_order([("A", {}), ("B", {}), ("C", load("o1.json"))])
        self.assertEqual([p["result"] for p in res["pairs"]],
                         ["not compared: A and B do not verify", "not compared: A does not verify",
                          "not compared: B does not verify"])


if __name__ == "__main__":
    unittest.main()
