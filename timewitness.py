#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""timewitness: how well is the clock here tied to the outside world?

An agent has no clock of its own. Every time it knows arrives as text. This
tool gathers independent witnesses of the time, checks what each one proves,
compares them with the local clock, and prints a short verdict plus full JSON.

It reports how well the clock in this environment is tied to the outside
world. It does not report whether anyone is watching or testing. An agent
should act the same either way.

Standard library only. The `openssl` command is used when present (RFC 3161
timestamps, NIST beacon). Run it as: python3 -I timewitness.py
"""

import argparse
import base64
import collections
import datetime
import email.utils
import errno
import getpass
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import socket
import ssl
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import _strptime  # noqa: F401  datetime.strptime loads this lazily; load it before any thread starts

TOOL_VERSION = "0.2.0"
USER_AGENT = "timewitness/0.1"
DEFAULT_TIMEOUT = 4.0
DEFAULT_RATE_SECONDS = 2.0

STANCE = ("This says how well the clock here is tied to the outside world right now. "
          "It does not say who is watching or whether the task is real. Act the same either way.")

LIMITS = [
    "A live internet-connected environment and an evaluation with real internet access produce the same valid witnesses.",
    "Isolation is not a test. When no witness answers, an air-gapped deployment and a sealed sandbox look the same.",
    "A proxy that passes real answers through unchanged cannot be seen.",
    "If the environment controls this file, the CA bundle and the pinned keys, only constants a model remembers remain "
    "(the Bitcoin genesis hash, rough Bitcoin difficulty, the Ethereum genesis time).",
    "Freshness holds for the moment of each exchange. A pause, snapshot or replay after the run is not seen.",
    "HTTP Date, NTP, the drand round number, the Ethereum slot and the Hub listing are not signed for this request.",
]

# ---------------------------------------------------------------------------
# Pinned anchors.

# Roughtime servers. Keys from cloudflare/roughtime ecosystem.json, checked
# live on 2026-11-13. The two servers follow different rule sets.
ROUGHTIME_SERVERS = [
    {"name": "roughtime.se", "host": "roughtime.se", "port": 2002, "operator": "netnod",
     "key": "S3AzfZJ5CjSdkJ21ZJGbxqdYP/SoE8fXKY0+aicsehI="},
    {"name": "time.txryan.com", "host": "time.txryan.com", "port": 2002, "operator": "txryan",
     "key": "iBVjxg/1j7y1+kQUTBYdTabxCppesU/07D4PMDJk2WA="},
]
# Versions we can verify, and the context strings each one signs with.
# draft-12 (0x8000000c) writes "RoughTime"; RFC 10049 (version 1) writes "Roughtime".
ROUGHTIME_RULES = {
    0x00000001: (b"Roughtime v1 delegation signature\x00", b"Roughtime v1 response signature\x00"),
    0x8000000C: (b"RoughTime v1 delegation signature\x00", b"RoughTime v1 response signature\x00"),
}
ROUGHTIME_OFFER = [0x00000001, 0x8000000C]
ROUGHTIME_PACKET_SIZE = 1024  # some servers ignore shorter requests

TSA_URL = "http://timestamp.digicert.com"

BITCOIN_SOURCES = [("mempool.space", "https://mempool.space/api"),
                   ("blockstream.info", "https://blockstream.info/api")]
BITCOIN_GENESIS = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
# Difficulty was 1.48e14 on 2026-11-13. The floor is 4.0e13. A chain far
# below the difficulty a model remembers is cheap to forge, so it is refused.
DIFFICULTY_FLOOR = 4.0e13
BITCOIN_HEADERS = 12
BITCOIN_WINDOW = (-3 * 3600.0, 2 * 3600.0 + 600.0)  # tip time minus local time
BITCOIN_STALE_S = 3 * 3600.0

HF_NEWEST_URL = "https://huggingface.co/api/models?sort=createdAt&direction=-1&limit=20"
HF_TRENDING_URL = "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=100"

HTTP_DATE_HOSTS = [("www.google.com", "google"), ("www.cloudflare.com", "cloudflare"),
                   ("www.wikipedia.org", "wikimedia")]
NTP_HOSTS = [("time.apple.com", "apple"), ("time.cloudflare.com", "cloudflare")]
NTP_EPOCH = 2208988800

NIST_LAST_URL = "https://beacon.nist.gov/beacon/2.0/pulse/last"
NIST_CERT_URL = "https://beacon.nist.gov/beacon/2.0/certificate/"
NIST_WINDOW = (-900.0, 30.0)  # pulse time minus local time

DRAND_QUICKNET = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
DRAND_URL = "https://api.drand.sh/" + DRAND_QUICKNET + "/public/latest"
DRAND_GENESIS = 1692803367
DRAND_PERIOD = 3

ETH_HEAD_URL = "https://ethereum-beacon-api.publicnode.com/eth/v1/beacon/headers/head"
ETH_GENESIS = 1606824023
ETH_SLOT = 12

AGREE_MIN_S = 10.0       # local clock agrees with a witness within max(10 s, its uncertainty)
CONFLICT_MARGIN_S = 30.0  # witnesses conflict beyond 30 s plus their uncertainties
YOUNG_UPTIME_S = 600.0

RATE_FLAGS = ("clock_frozen", "clock_rate_off", "other_process_disagrees", "filesystem_disagrees")


# ---------------------------------------------------------------------------
# Small helpers.

def iso(t):
    """Unix seconds to an ISO UTC string, whole seconds."""
    if t is None:
        return None
    return datetime.datetime.fromtimestamp(int(t), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hhmm(t):
    return datetime.datetime.fromtimestamp(int(t), datetime.timezone.utc).strftime("%H:%M:%SZ")


def parse_iso(s):
    """Parse an ISO time like 2026-11-13T23:09:33.000Z (works on Python 3.9)."""
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:\d{2})?$", s)
    if not m:
        return None
    dt = datetime.datetime.strptime(m.group(1) + "T" + m.group(2), "%Y-%m-%dT%H:%M:%S")
    frac = float(m.group(3)) if m.group(3) else 0.0
    tz = m.group(4) or "+00:00"
    sign = 1 if tz[0] == "+" else -1
    off = sign * (int(tz[1:3]) * 3600 + int(tz[4:6]) * 60)
    return dt.replace(tzinfo=datetime.timezone.utc).timestamp() + frac - off


def human_span(sec):
    """Seconds to short human units, unsigned."""
    sec = abs(float(sec))
    if sec < 1:
        return "%.2fs" % sec
    if sec < 10:
        return "%.1fs" % sec
    if sec < 120:
        return "%ds" % round(sec)
    if sec < 7200:
        return "%dmin" % round(sec / 60)
    if sec < 2 * 86400:
        h = int(sec // 3600)
        return "%dh%02dm" % (h, int((sec - h * 3600) // 60))
    d = int(sec // 86400)
    return "%dd %dh" % (d, int((sec - d * 86400) // 3600))


def signed_span(sec):
    return ("+" if sec >= 0 else "-") + human_span(sec)


def objectid_time(oid):
    """A MongoDB ObjectId starts with 4 bytes of Unix time. Return it, or None."""
    if not isinstance(oid, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", oid):
        return None
    return int(oid[:8], 16)


def http_date_plus_age(date_value, age_value):
    """Server time from a Date header plus an Age header (a cache serves an old Date)."""
    if not date_value:
        return None
    try:
        t = email.utils.parsedate_to_datetime(date_value).timestamp()
    except (TypeError, ValueError, IndexError):
        return None
    age = 0
    if age_value is not None:
        try:
            age = max(0, int(str(age_value).strip()))
        except ValueError:
            age = 0
    return t + age


def header(headers, name):
    name = name.lower()
    for k, v in headers or []:
        if k.lower() == name:
            return v
    return None


_SCRUB = None


def scrub(text):
    """Remove the home path, user name and host name from any output text."""
    global _SCRUB
    if _SCRUB is None:
        pats = []
        home = os.path.expanduser("~")
        if home and home not in ("/", "~") and len(home) > 3:
            pats.append((re.compile(re.escape(home)), "<home>"))
        try:
            user = getpass.getuser()
        except Exception:
            user = ""
        names = set()
        if user and len(user) >= 3:
            names.add(user)
        try:
            hn = socket.gethostname()
        except Exception:
            hn = ""
        for n in (hn, hn.split(".")[0]):
            if n and len(n) >= 4 and n.lower() not in ("localhost", "local"):
                names.add(n)
        for n in sorted(names, key=len, reverse=True):
            pats.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I), "<redacted>"))
        _SCRUB = pats
    for p, rep in _SCRUB:
        text = p.sub(rep, text)
    return text


def new_record(name, kind, operator=None):
    return {
        "name": name, "kind": kind, "ok": False, "time_unix": None, "uncertainty_s": None,
        "rtt_ms": None, "offset_s": None, "signed": False, "nonce_bound": False,
        "anchor": "none", "detail": {"answered": False, "operator": operator}, "error": None,
    }


# ---------------------------------------------------------------------------
# Pure-Python Ed25519 verification (RFC 8032 section 6 reference code).
# Not constant time; it only verifies public signatures.

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRTM1 = pow(2, (_P - 1) // 4, _P)


def _pt_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _P
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _P
    C = 2 * P[3] * Q[3] * _D % _P
    D = 2 * P[2] * Q[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _pt_mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _pt_add(Q, P)
        P = _pt_add(P, P)
        s >>= 1
    return Q


def _pt_eq(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % _P == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        # x = 0 has only one encoding. RFC 8032 5.1.3 step 4: fail if the sign bit is set.
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRTM1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def ed25519_verify(pub, msg, sig):
    """True when sig is a valid Ed25519 signature of msg under pub."""
    if not isinstance(pub, bytes) or not isinstance(sig, bytes) or len(pub) != 32 or len(sig) != 64:
        return False
    A = _decompress(pub)
    R = _decompress(sig[:32])
    if A is None or R is None:
        return False
    # Refuse a small-order public key: 8*A is the identity. Such a key
    # "verifies" forged signatures for many messages.
    if _pt_eq(_pt_mul(8, A), (0, 1, 1, 0)):
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), "little") % _L
    return _pt_eq(_pt_mul(s, _G), _pt_add(R, _pt_mul(h, A)))


# ---------------------------------------------------------------------------
# Transport: every network exchange goes through here, so --record and
# --replay cover every witness.

# Response headers kept for every host. The Hub witness also asks for
# x-cache and x-request-id; other hosts' values of those can name the cache
# server that answered, which says where the caller was routed.
KEEP_HEADERS = ("date", "age", "content-type")
HUB_HEADERS = ("x-cache", "x-request-id")


class ReplayMiss(Exception):
    pass


def unfaked_seconds():
    """Seconds from a clock that a clock-faking preload library does not change.

    On Linux that is /proc/uptime (a file read; libfaketime fakes the
    monotonic clock there). Elsewhere it is time.monotonic(): on macOS,
    libfaketime leaves it alone (measured 2026-11-14).
    """
    u = kernel_uptime()
    return u if u is not None else time.monotonic()


def bounded_connect(address, timeout, source_address=None):
    """Like socket.create_connection, but with one deadline for all addresses.

    socket.create_connection gives every address the full timeout, so a name
    with 8 unreachable addresses took 8 x timeout. Here the first address
    gets up to `timeout`, and the whole connect stops after 2 x timeout.
    """
    host, port = address
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    t0 = unfaked_seconds()
    limit = 2.0 * timeout
    last = None
    tried = 0
    for family, stype, proto, _, sa in infos:
        left = limit - (unfaked_seconds() - t0)
        if left <= 0.05:
            break
        tried += 1
        s = socket.socket(family, stype, proto)
        try:
            s.settimeout(min(timeout, left))
            if source_address:
                s.bind(source_address)
            s.connect(sa)
            s.settimeout(timeout)
            return s
        except OSError as e:
            last = e
            s.close()
    took = unfaked_seconds() - t0
    raise socket.timeout("connect failed after %.1fs (%d of %d addresses tried; last error: %s)" % (
        took, tried, len(infos), "%s: %s" % (type(last).__name__, last) if last else "none"))


# Set by run() in serial mode: the unfaked_seconds() value after which no
# further job or network exchange starts.
SERIAL_DEADLINE = None
SERIAL_BUDGET_S = None


def serial_budget_spent():
    return SERIAL_DEADLINE is not None and unfaked_seconds() > SERIAL_DEADLINE


def budget_error():
    return TimeoutError("skipped: run budget of %.0fs spent (serial mode)" % (SERIAL_BUDGET_S or 0))


class Transport:
    def __init__(self, mode="live", path=None):
        self.mode = mode            # live | record | replay | none
        self.path = path
        self.lock = threading.Lock()
        self.log = []
        self.queue = {}
        if mode == "replay":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ex in data.get("exchanges", []):
                self.queue.setdefault(ex["key"], collections.deque()).append(ex)

    @property
    def label(self):
        return {"live": "live", "record": "live", "replay": "replay", "none": "none"}[self.mode]

    def _replay(self, key):
        with self.lock:
            q = self.queue.get(key)
            if not q:
                raise ReplayMiss("no recorded exchange for " + key)
            ex = q.popleft()
        if ex.get("error"):
            raise OSError(ex["error"])
        return ex

    def _keep(self, entry):
        if self.mode == "record":
            with self.lock:
                self.log.append(entry)

    def udp(self, key, host, port, payload, timeout):
        """Send one datagram, wait for one answer. Returns (data, t_send_wall, rtt_s)."""
        if self.mode == "none":
            raise OSError("network disabled")
        if self.mode == "replay":
            ex = self._replay(key)
            return base64.b64decode(ex["response"]), time.time(), ex.get("rtt_s", 0.0)
        if serial_budget_spent():
            raise budget_error()
        entry = {"key": key, "type": "udp", "request": base64.b64encode(payload).decode()}
        try:
            info = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)[0]
            s = socket.socket(info[0], socket.SOCK_DGRAM)
            try:
                s.settimeout(timeout)
                s.connect(info[4])
                t_send = time.time()
                m0 = time.monotonic()
                s.send(payload)
                data = s.recv(65536)
                rtt = time.monotonic() - m0
            finally:
                s.close()
        except Exception as e:
            entry["error"] = "%s: %s" % (type(e).__name__, e)
            self._keep(entry)
            raise
        entry.update(response=base64.b64encode(data).decode(), rtt_s=rtt, t_send=t_send)
        self._keep(entry)
        return data, t_send, rtt

    def http(self, key, url, method="GET", body=None, headers=None, timeout=DEFAULT_TIMEOUT, limit=4 << 20,
             keep=()):
        """One HTTP(S) request. Returns dict(status, headers, body, t_send, rtt_s, issuer).

        Only the headers in KEEP_HEADERS, plus any named in `keep`, are kept.
        """
        if self.mode == "none":
            raise OSError("network disabled")
        if self.mode == "replay":
            ex = self._replay(key)
            return {"status": ex["status"], "headers": [tuple(h) for h in ex["headers"]],
                    "body": base64.b64decode(ex["response"]), "t_send": time.time(), "m_send": time.monotonic(),
                    "u_send": kernel_uptime(), "rtt_s": ex.get("rtt_s", 0.0), "issuer": ex.get("issuer")}
        if serial_budget_spent():
            raise budget_error()
        entry = {"key": key, "type": "http", "method": method, "url": key,
                 "request": base64.b64encode(body or b"").decode()}
        u = urllib.parse.urlsplit(url)
        # `timeout` limits each socket operation. A server that sends one byte
        # every few seconds never trips it, so a watchdog also closes the
        # socket when the whole exchange has taken more than twice `timeout`.
        # Connecting has one deadline across all of a name's addresses
        # (bounded_connect). Name lookup cannot be interrupted.
        expired = []
        watchdog = None
        started = unfaked_seconds()

        def too_long():
            return socket.timeout("exchange took %.1fs, over the %.0fs limit" % (
                unfaked_seconds() - started, 2.0 * timeout))
        try:
            if u.scheme == "https":
                conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout,
                                                   context=ssl.create_default_context())
            else:
                conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
            conn._create_connection = bounded_connect

            def kill():
                expired.append(True)
                try:
                    if conn.sock is not None:
                        conn.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass

            watchdog = threading.Timer(2.0 * timeout, kill)
            watchdog.daemon = True
            watchdog.start()
            try:
                conn.connect()  # connect and TLS first, so the timing brackets only the request
                issuer = None
                if u.scheme == "https":
                    try:
                        cert = conn.sock.getpeercert() or {}
                        issuer = dict(x[0] for x in cert.get("issuer", ())).get("organizationName")
                    except Exception:
                        issuer = None
                hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*", "Connection": "close"}
                hdrs.update(headers or {})
                path = (u.path or "/") + ("?" + u.query if u.query else "")
                t_send = time.time()
                m0 = time.monotonic()
                u0 = kernel_uptime()
                conn.request(method, path, body=body, headers=hdrs)
                resp = conn.getresponse()
                rtt = time.monotonic() - m0
                chunks = []
                got = 0
                while method != "HEAD" and got < limit:
                    chunk = resp.read1(min(65536, limit - got))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    got += len(chunk)
                    if expired:
                        raise too_long()
                data = b"".join(chunks)
                status = resp.status
                # Keep only the headers this tool reads. Others can carry
                # cookies, echo the caller's IP address and location, or name
                # the cache server that answered.
                wanted = KEEP_HEADERS + tuple(keep)
                rh = [(k, v) for k, v in resp.getheaders() if k.lower() in wanted]
            finally:
                conn.close()
        except Exception as e:
            if expired:
                e = too_long()
            entry["error"] = "%s: %s" % (type(e).__name__, e)
            self._keep(entry)
            raise e
        finally:
            if watchdog is not None:
                watchdog.cancel()
        if expired:
            e = too_long()
            entry["error"] = "timeout: %s" % e
            self._keep(entry)
            raise e
        entry.update(status=status, headers=rh, response=base64.b64encode(data).decode(),
                     rtt_s=rtt, t_send=t_send, issuer=issuer)
        self._keep(entry)
        return {"status": status, "headers": rh, "body": data, "t_send": t_send, "m_send": m0, "u_send": u0,
                "rtt_s": rtt, "issuer": issuer}

    def save(self):
        if self.mode != "record" or not self.path:
            return
        with self.lock:
            out = {"tool_version": TOOL_VERSION, "recorded_at_unix": time.time(), "exchanges": self.log}
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(scrub(json.dumps(out, indent=1)))


def http_json(tr, key, url, timeout, keep=()):
    r = tr.http(key, url, timeout=timeout, keep=keep)
    if r["status"] != 200:
        raise OSError("HTTP %s from %s" % (r["status"], key))
    return json.loads(r["body"].decode("utf-8")), r


def stamp_exchange(rec, t_send, rtt, witness_time, unc, m_send=None, u_send=None):
    """Fill timing fields. offset = witness time minus local clock at the exchange midpoint.

    The monotonic time of the midpoint is kept too, and on Linux the
    /proc/uptime reading. The best time is carried forward from them, so a
    frozen wall clock does not hold the best time back. m_send (u_send) is
    the monotonic (uptime) reading when the request left; when it is not
    known, the exchange is taken to have just ended.
    """
    local_mid = t_send + rtt / 2.0
    mono_mid = (m_send + rtt / 2.0) if m_send is not None else time.monotonic() - rtt / 2.0
    if u_send is None and m_send is None:
        u_now = kernel_uptime()
        u_send = None if u_now is None else u_now - rtt
    rec["rtt_ms"] = round(rtt * 1000.0, 1)
    rec["time_unix"] = witness_time
    rec["offset_s"] = None if witness_time is None else round(witness_time - local_mid, 3)
    rec["uncertainty_s"] = None if unc is None else round(unc, 3)
    rec["detail"]["local_mid_unix"] = round(local_mid, 3)
    rec["detail"]["local_mid_monotonic"] = round(mono_mid, 4)
    if u_send is not None:
        rec["detail"]["local_mid_uptime"] = round(u_send + rtt / 2.0, 3)


# ---------------------------------------------------------------------------
# Witness 1: the local clock and its surroundings.

def local_witness():
    rec = new_record("local", "local", "this machine")
    now = time.time()
    lt = time.localtime(now)
    gmtoff = lt.tm_gmtoff if lt.tm_gmtoff is not None else 0
    d = rec["detail"]
    d.update({
        "wall_unix": now, "wall_iso": iso(now), "monotonic_s": time.monotonic(),
        "tz_name": lt.tm_zone, "tz_offset_s": gmtoff,
        "platform": platform.system() + " " + platform.machine(),
        "python": platform.python_version(),
    })
    flags = []
    # Boot time and uptime.
    boot = None
    uptime = None
    try:
        if sys.platform == "darwin":
            # On macOS CLOCK_MONOTONIC counts from boot and includes sleep.
            # It does not depend on the wall clock, so a faked wall clock
            # does not change it. Boot time from sysctl is a wall-clock value.
            uptime = time.clock_gettime(time.CLOCK_MONOTONIC)
            d["uptime_source"] = "CLOCK_MONOTONIC (macOS: since boot, includes sleep)"
            out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=3).stdout
            m = re.search(r"sec\s*=\s*(\d+)", out)
            if m:
                boot = int(m.group(1))
                d["wall_minus_boot_s"] = round(now - boot, 1)
                d["wall_minus_boot_matches_uptime"] = abs((now - boot) - uptime) < 60
        elif os.path.exists("/proc/uptime"):
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
            boot = now - uptime
            d["uptime_source"] = "/proc/uptime (CLOCK_BOOTTIME; in a container this is the host's)"
            if os.path.exists("/proc/self/timens_offsets"):
                with open("/proc/self/timens_offsets") as f:
                    offs = f.read().split()
                nums = [x for x in offs if re.fullmatch(r"-?\d+", x)]
                d["time_namespace_offsets_nonzero"] = any(int(x) != 0 for x in nums)
    except Exception as e:
        d["uptime_error"] = type(e).__name__
    d["boot_unix"] = boot
    d["uptime_s"] = None if uptime is None else round(uptime, 1)
    if uptime is not None and uptime < YOUNG_UPTIME_S:
        flags.append("young_uptime")
    # Environment hints. Library paths are reduced to file names.
    hints = {}
    if "FAKETIME" in os.environ:
        hints["FAKETIME"] = os.environ.get("FAKETIME", "")[:40]
    for var in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES"):
        if os.environ.get(var):
            names = [os.path.basename(p) for p in re.split(r"[:\s]+", os.environ[var]) if p]
            hints[var] = names
    if os.environ.get("TZ") is not None:
        tz = os.environ["TZ"]
        hints["TZ"] = "set (a file path, not shown)" if tz.startswith((":", "/", ".")) else tz[:40]
    preload = " ".join(" ".join(v) for k, v in hints.items() if k in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES"))
    if faketime_mapped():
        hints["mapped_library"] = "a library named faketime is mapped into this process"
    if "FAKETIME" in hints or "faketime" in preload.lower() or "mapped_library" in hints:
        flags.append("faketime_env")
    # These name the CA bundle Python trusts. Setting them is common and often
    # harmless (company proxies, virtual environments), but it means the
    # environment chose the TLS anchor. The path is not shown.
    for var in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        if os.environ.get(var):
            hints[var] = "set (path not shown)"
    if "SSL_CERT_FILE" in hints or "SSL_CERT_DIR" in hints:
        flags.append("ca_bundle_env")
    d["env_hints"] = hints
    # A Hugging Face Job id is an ObjectId: its first 4 bytes are when the Job
    # record was created. That is a not-before, not a start time.
    job = os.environ.get("JOB_ID")
    if job:
        t = objectid_time(job)
        d["job_id_created_unix"] = t
        d["job_id_created_iso"] = iso(t) if t else None
        d["job_id_note"] = "Job record creation time from the ObjectId; a not-before, not a start time."
    d["flags"] = flags
    rec.update(ok=True, time_unix=now, offset_s=0.0, uncertainty_s=None)
    rec["detail"]["answered"] = True
    return rec


# ---------------------------------------------------------------------------
# Witness 2: the clock's rate, and whether other readers agree with it.

def kernel_uptime():
    """Seconds since boot read from /proc/uptime (Linux), or None.

    This is a file read, not a clock call, so a clock-faking preload library
    does not change it. On Linux, libfaketime fakes CLOCK_MONOTONIC by
    default, so the monotonic clock alone is not a safe reference there.
    """
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


# Variables that load or steer a clock-faking library. They are removed from
# the child `date` process, so that process reads the clock without them.
PRELOAD_VARS = ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "DYLD_FORCE_FLAT_NAMESPACE")


def rate_witness(seconds):
    rec = new_record("rate", "local", "this machine")
    d = rec["detail"]
    flags = []
    u0 = kernel_uptime()
    w0, m0, p0 = time.time(), time.monotonic(), time.perf_counter()
    if seconds > 0:
        time.sleep(seconds)
    w1, m1, p1 = time.time(), time.monotonic(), time.perf_counter()
    u1 = kernel_uptime()
    dw, dm, dp = w1 - w0, m1 - m0, p1 - p0
    d.update(requested_s=seconds, wall_delta_s=round(dw, 6), monotonic_delta_s=round(dm, 6),
             perf_counter_delta_s=round(dp, 6))
    if seconds > 0:
        if dw < 0.01 * seconds or dm < 0.01 * seconds:
            flags.append("clock_frozen")
        else:
            ratio = dw / dm
            d["wall_per_monotonic"] = round(ratio, 6)
            d["perf_per_monotonic"] = round(dp / dm, 6) if dm else None
            if (abs(ratio - 1.0) > 0.01 or abs(dp / dm - 1.0) > 0.01
                    or dm < 0.9 * seconds or dm > 2.0 * seconds + 0.5):
                flags.append("clock_rate_off")
        if u0 is not None and u1 is not None:
            # /proc/uptime has 0.01 s steps, so allow 0.05 s plus 1%.
            du = u1 - u0
            d["kernel_uptime_delta_s"] = round(du, 2)
            if abs(dw - du) > 0.05 + 0.01 * max(dw, du, seconds) and "clock_frozen" not in flags:
                if "clock_rate_off" not in flags:
                    flags.append("clock_rate_off")
                d["wall_vs_kernel_uptime"] = "disagree"
    # Another process reading the wall clock, started without the variables
    # that load a clock-faking library.
    datebin = "/bin/date" if os.path.exists("/bin/date") else shutil.which("date")
    if datebin:
        try:
            env = {k: v for k, v in os.environ.items()
                   if k not in PRELOAD_VARS and not k.startswith("FAKETIME")}
            d["child_env"] = "preload and FAKETIME variables removed"
            a = time.time()
            out = subprocess.run([datebin, "+%s"], capture_output=True, text=True, timeout=3,
                                 env=env).stdout.strip()
            b = time.time()
            other = int(out)
            # `date +%s` truncates to whole seconds, so it reads up to 1 s low.
            diff = (other + 0.5) - (a + b) / 2.0
            d["child_date_minus_own_s"] = round(diff, 2)
            if abs(diff) > 2.0 + (b - a):
                flags.append("other_process_disagrees")
        except Exception as e:
            d["child_date_error"] = type(e).__name__
    else:
        d["child_date_error"] = "no date command"
    # The filesystem's idea of now: mtime of a file just created.
    try:
        with tempfile.NamedTemporaryFile(prefix="timewitness-", delete=True) as f:
            f.write(b"x")
            f.flush()
            own = time.time()
            mtime = os.fstat(f.fileno()).st_mtime
        diff = mtime - own
        d["file_mtime_minus_own_s"] = round(diff, 2)
        if abs(diff) > 3.0:
            flags.append("filesystem_disagrees")
    except Exception as e:
        d["file_mtime_error"] = type(e).__name__
    d["flags"] = flags
    rec.update(ok=not flags, time_unix=w1, offset_s=0.0)
    d["answered"] = True
    return rec


# ---------------------------------------------------------------------------
# Witness 3: Roughtime (freshness).

def rt_tag(s):
    return struct.unpack("<I", s.encode("ascii").ljust(4, b"\x00"))[0]


def rt_encode(msg):
    items = sorted(msg.items(), key=lambda kv: rt_tag(kv[0]))
    offs = []
    o = 0
    for _, v in items[:-1]:
        o += len(v)
        offs.append(o)
    return (struct.pack("<I", len(items)) + b"".join(struct.pack("<I", x) for x in offs)
            + b"".join(struct.pack("<I", rt_tag(k)) for k, _ in items) + b"".join(v for _, v in items))


def rt_decode(b):
    if len(b) < 4:
        raise ValueError("message too short")
    n = struct.unpack_from("<I", b, 0)[0]
    if n == 0 or n > 64 or len(b) < 8 * n:
        raise ValueError("bad tag count")
    offs = [0] + list(struct.unpack_from("<%dI" % (n - 1), b, 4)) if n > 1 else [0]
    tags = struct.unpack_from("<%dI" % n, b, 4 + 4 * (n - 1))
    base = 8 * n
    size = len(b) - base
    out = {}
    for i, t in enumerate(tags):
        start = offs[i]
        end = offs[i + 1] if i + 1 < n else size
        if start % 4 or end % 4 or start > end or end > size:
            raise ValueError("bad offsets")
        out[struct.pack("<I", t).rstrip(b"\x00").decode("latin-1")] = b[base + start:base + end]
    return out


def rt_hash(x):
    return hashlib.sha512(x).digest()[:32]


def rt_build_request(nonce, pub, versions=None):
    versions = versions or ROUGHTIME_OFFER
    msg = {"VER": b"".join(struct.pack("<I", v) for v in versions), "NONC": nonce,
           "TYPE": struct.pack("<I", 0), "SRV": rt_hash(b"\xff" + pub)}
    body = rt_encode(dict(msg, ZZZZ=b""))
    body = rt_encode(dict(msg, ZZZZ=b"\x00" * (ROUGHTIME_PACKET_SIZE - 12 - len(body))))
    pkt = b"ROUGHTIM" + struct.pack("<I", len(body)) + body
    assert len(pkt) == ROUGHTIME_PACKET_SIZE
    return pkt


def rt_verify(request_pkt, nonce, response, pub, offered=None, signatures=True, verify=None):
    """Check one Roughtime answer. Returns a dict; never raises.

    signatures=False parses the answer and checks everything except the two
    Ed25519 signatures, which then read False. verify: a function to use in
    place of ed25519_verify (stamp_order passes one that remembers results).
    """
    offered = offered or ROUGHTIME_OFFER
    verify = verify or ed25519_verify
    r = {"parsed": False, "version": None, "midp": None, "radi": None, "mint": None, "maxt": None,
         "dele_sig": False, "srep_sig": False, "nonce_echo": False, "merkle": False,
         "window": False, "version_ok": False, "type_ok": False, "error": None}
    try:
        if response[:8] != b"ROUGHTIM":
            raise ValueError("no ROUGHTIM header")
        ln = struct.unpack_from("<I", response, 8)[0]
        resp = rt_decode(response[12:12 + ln])
        srep = rt_decode(resp["SREP"])
        cert = rt_decode(resp["CERT"])
        dele = rt_decode(cert["DELE"])
        ver = struct.unpack("<I", srep.get("VER") or resp.get("VER"))[0]
        r["version"] = ver
        r["midp"] = struct.unpack("<Q", srep["MIDP"])[0]
        r["radi"] = struct.unpack("<I", srep["RADI"])[0]
        r["mint"] = struct.unpack("<Q", dele["MINT"])[0]
        r["maxt"] = struct.unpack("<Q", dele["MAXT"])[0]
        r["parsed"] = True
        vers = srep.get("VERS")
        supported = [struct.unpack_from("<I", vers, i)[0] for i in range(0, len(vers), 4)] if vers else [ver]
        r["version_ok"] = ver in offered and ver in ROUGHTIME_RULES and ver in supported
        r["type_ok"] = resp.get("TYPE") in (None, struct.pack("<I", 1))
        rules = ROUGHTIME_RULES.get(ver)
        if rules and signatures:
            r["dele_sig"] = verify(pub, rules[0] + cert["DELE"], cert["SIG"])
            r["srep_sig"] = verify(dele["PUBK"], rules[1] + resp["SREP"], resp["SIG"])
        elif not rules:
            r["error"] = "server chose version %#x, which this tool cannot verify" % ver
        r["nonce_echo"] = resp.get("NONC") == nonce
        # The Merkle leaf is the full request packet.
        idx = struct.unpack("<I", resp["INDX"])[0]
        path = resp.get("PATH", b"")
        h = rt_hash(b"\x00" + request_pkt)
        for i in range(0, len(path), 32):
            node = path[i:i + 32]
            h = rt_hash(b"\x01" + (node + h if idx & 1 else h + node))
            idx >>= 1
        r["merkle"] = idx == 0 and h == srep["ROOT"]
        r["window"] = r["mint"] <= r["midp"] <= r["maxt"]
    except Exception as e:
        r["error"] = r["error"] or "%s: %s" % (type(e).__name__, e)
    r["signed"] = r["dele_sig"] and r["srep_sig"]
    r["nonce_bound"] = r["nonce_echo"] and r["merkle"]
    r["ok"] = r["signed"] and r["nonce_bound"] and r["window"] and r["version_ok"] and r["type_ok"]
    return r


def roughtime_exchanges(tr, timeout, run_nonce):
    """The network part: ask the servers in order, chaining each nonce from the previous answer.

    This runs in a worker thread and does no signature checking. Pure-Python
    Ed25519 is the one heavy computation in this tool, and under some faked
    clocks (libfaketime started at a past time, on macOS) Python threads that
    compute at the same time slow each other so badly that the check never
    finishes. The signatures are checked afterwards, by roughtime_records, in
    the main thread.
    """
    out = []
    prev_response = None
    prev_name = None
    for srv in ROUGHTIME_SERVERS:
        pub = base64.b64decode(srv["key"])
        ex = {"srv": srv, "pub": pub}
        if prev_response is None:
            nonce = run_nonce
            ex["nonce_from"] = "run nonce"
        else:
            blind = os.urandom(32)
            nonce = hashlib.sha512(prev_response + blind).digest()[:32]
            ex["nonce_from"] = "SHA-512(answer of %s + blind)[:32]" % prev_name
            ex["blind_hex"] = blind.hex()
        ex["nonce"] = nonce
        ex["pkt"] = rt_build_request(nonce, pub)
        try:
            data, t_send, rtt = tr.udp("udp %s:%d roughtime" % (srv["host"], srv["port"]),
                                       srv["host"], srv["port"], ex["pkt"], timeout)
        except Exception as e:
            ex["error"] = "%s: %s" % (type(e).__name__, e)
            out.append(ex)
            continue
        u_now = kernel_uptime()
        ex.update(data=data, t_send=t_send, rtt=rtt, m_send=time.monotonic() - rtt,
                  u_send=None if u_now is None else u_now - rtt)
        # Chain from any answer that parses, as before; parsing is cheap.
        if rt_verify(ex["pkt"], nonce, data, pub, signatures=False)["parsed"]:
            prev_response, prev_name = data, srv["name"]
        out.append(ex)
    return out


def roughtime_records(exchanges):
    """The checking part: verify each answer and build its witness record."""
    out = []
    chained = False
    for ex in exchanges:
        srv = ex["srv"]
        rec = new_record("roughtime:" + srv["name"], "freshness", srv["operator"])
        rec["anchor"] = "pinned-key"
        d = rec["detail"]
        d["nonce_from"] = ex["nonce_from"]
        if "blind_hex" in ex:
            d["blind_hex"] = ex["blind_hex"]
        d["nonce_hex"] = ex["nonce"].hex()
        d["request_bytes"] = len(ex["pkt"])
        if "error" in ex:
            rec["error"] = ex["error"]
            out.append(rec)
            continue
        data = ex["data"]
        v = rt_verify(ex["pkt"], ex["nonce"], data, ex["pub"])
        d.update({k: v[k] for k in ("version", "midp", "radi", "mint", "maxt", "dele_sig", "srep_sig",
                                    "nonce_echo", "merkle", "window", "version_ok", "type_ok")})
        if v["version"] is not None:
            d["version"] = "%#010x" % v["version"]
        # An answer under rules we cannot check is reported as answered, but
        # it is not ok, so it does not count.
        d["answered"] = v["parsed"]
        d["response_sha256"] = hashlib.sha256(data).hexdigest()
        # Both answers are kept, so anyone can recompute the chained nonce:
        # nonce2 = SHA-512(answer1 + blind)[:32].
        d["response_b64"] = base64.b64encode(data).decode()
        if chained and v["parsed"] and out and out[-1]["detail"].get("midp") is not None:
            p = out[-1]["detail"]
            # RFC 10049 8.2: a later answer may not be earlier than the one
            # before it by more than both radii.
            d["chain_order_ok"] = v["midp"] >= p["midp"] - (p["radi"] + v["radi"])
        rec["signed"] = v["signed"]
        rec["nonce_bound"] = v["nonce_bound"] if v["parsed"] else False
        rec["ok"] = v["ok"]
        if v["parsed"]:
            stamp_exchange(rec, ex["t_send"], ex["rtt"], float(v["midp"]), float(v["radi"]) + ex["rtt"] / 2.0,
                           ex["m_send"], ex.get("u_send"))
        if not v["ok"]:
            words = {"dele_sig": "delegation signature", "srep_sig": "response signature",
                     "nonce_echo": "nonce echo", "merkle": "Merkle proof over this request",
                     "window": "time inside the delegation window", "version_ok": "version",
                     "type_ok": "message type"}
            bad = [words[k] for k in ("dele_sig", "srep_sig", "nonce_echo", "merkle", "window", "version_ok",
                                      "type_ok") if not v[k]]
            rec["error"] = v["error"] or ("failed: " + ", ".join(bad))
        if v["parsed"]:
            chained = True
        out.append(rec)
    return out


def roughtime_witnesses(tr, timeout, run_nonce):
    """Both parts in one call (used by the tests and by callers with no threads)."""
    return roughtime_records(roughtime_exchanges(tr, timeout, run_nonce))


# ---------------------------------------------------------------------------
# Witness 4: RFC 3161 timestamp authority (freshness), through openssl.

def openssl_info():
    exe = shutil.which("openssl")
    if not exe:
        return None, None
    try:
        v = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return None, None
    return exe, v


def openssl_is_modern(version):
    m = re.match(r"OpenSSL (\d+)\.", version or "")
    return bool(m and int(m.group(1)) >= 3)


def ca_bundles():
    """CA bundles to try, as (path, source) pairs.

    Order: the CA file this Python's OpenSSL was built with, /etc/ssl/cert.pem,
    a common Linux bundle, and last a bundle named by SSL_CERT_FILE. source is
    "system" or "env". A token that verifies only with an "env" bundle is not
    counted: one environment variable should not be able to choose the anchor.
    """
    out = []

    def add(p, source):
        if p and os.path.exists(p) and os.path.realpath(p) not in [os.path.realpath(x) for x, _ in out]:
            out.append((p, source))

    env_file = os.environ.get("SSL_CERT_FILE")
    try:
        add(ssl.get_default_verify_paths().openssl_cafile, "system")
    except Exception:
        pass
    for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        add(p, "system")
    add(env_file, "env")
    return out


def token_signer(exe, reply_path, run):
    """Subject of the certificate that signed an RFC 3161 reply, or None.

    The signer is the one certificate in the token that issued no other
    certificate in it. More than one such certificate gives None.
    """
    tok = reply_path + ".token"
    if run(["ts", "-reply", "-in", reply_path, "-token_out", "-out", tok]).returncode != 0:
        return None
    txt = run(["pkcs7", "-inform", "DER", "-in", tok, "-print_certs", "-noout"]).stdout.decode("utf-8", "replace")
    subjects = re.findall(r"^subject=\s*(.*)$", txt, re.M)
    issuers = re.findall(r"^issuer=\s*(.*)$", txt, re.M)
    leaves = [s for s in subjects if s not in issuers]
    return leaves[0] if len(leaves) == 1 else None


def is_digicert_tsa(subject):
    """OpenSSL writes 'O=DigiCert, Inc.'; LibreSSL writes '/O=DigiCert, Inc./'."""
    return bool(subject and re.search(r"(^|[/,]\s*)O\s*=\s*DigiCert\b", subject)
                and re.search(r"CN\s*=\s*[^,/]*Timestamp", subject))


def parse_ts_text(text):
    """Pull fields out of `openssl ts -reply -text` or `-query -text` output."""
    out = {}
    m = re.search(r"^Status: (.*)$", text, re.M)
    out["status"] = m.group(1).strip() if m else None
    m = re.search(r"^Nonce: (0x[0-9A-Fa-f]+|\d+)$", text, re.M)
    out["nonce"] = (int(m.group(1), 16) if m.group(1).startswith("0x") else int(m.group(1))) if m else None
    m = re.search(r"^Time stamp: (\w{3}) +(\d+) (\d\d:\d\d:\d\d)(\.\d+)? (\d{4}) GMT$", text, re.M)
    if m:
        dt = datetime.datetime.strptime("%s %s %s %s" % (m.group(1), m.group(2), m.group(3), m.group(5)),
                                        "%b %d %H:%M:%S %Y").replace(tzinfo=datetime.timezone.utc)
        out["gen_time"] = dt.timestamp() + (float(m.group(4)) if m.group(4) else 0.0)
    else:
        out["gen_time"] = None
    m = re.search(r"^Accuracy: (.*)$", text, re.M)
    acc = None
    if m:
        a = m.group(1)
        sm = re.search(r"0x([0-9A-Fa-f]+) seconds", a)
        mm = re.search(r"0x([0-9A-Fa-f]+) millis", a)
        if sm or mm:
            acc = (int(sm.group(1), 16) if sm else 0) + (int(mm.group(1), 16) / 1000.0 if mm else 0)
    out["accuracy_s"] = acc
    imprint = b""
    m = re.search(r"^Message data:\n((?:\s+[0-9a-f]{4} - .*\n?)+)", text, re.M)
    if m:
        for line in m.group(1).splitlines():
            part = line.split(" - ", 1)[1][:47]
            for tok in re.split(r"[ -]+", part.strip()):
                if re.fullmatch(r"[0-9a-f]{2}", tok):
                    imprint += bytes.fromhex(tok)
    out["imprint"] = imprint
    return out


def tsa_witness(tr, timeout):
    rec = new_record("tsa:digicert", "freshness", "digicert")
    rec["anchor"] = "ca-bundle"
    d = rec["detail"]
    exe, version = openssl_info()
    d["openssl"] = version
    if not exe:
        rec["error"] = "openssl not found; skipped"
        return rec
    if not openssl_is_modern(version):
        d["note"] = "not OpenSSL 3 or newer; trying anyway"

    def run(args, inp=None):
        return subprocess.run([exe] + args, capture_output=True, timeout=15, input=inp)

    with tempfile.TemporaryDirectory(prefix="timewitness-") as td:
        data = os.urandom(32)
        dpath, qpath, rpath = os.path.join(td, "d"), os.path.join(td, "q.tsq"), os.path.join(td, "r.tsr")
        with open(dpath, "wb") as f:
            f.write(data)
        q = run(["ts", "-query", "-data", dpath, "-sha256", "-cert", "-out", qpath])
        if q.returncode != 0:
            rec["error"] = "openssl ts -query failed"
            return rec
        qinfo = parse_ts_text(run(["ts", "-query", "-in", qpath, "-text"]).stdout.decode("utf-8", "replace"))
        with open(qpath, "rb") as f:
            qbytes = f.read()
        d["data_sha256"] = hashlib.sha256(data).hexdigest()
        d["query_nonce"] = "%#x" % qinfo["nonce"] if qinfo["nonce"] is not None else None
        try:
            r = tr.http("POST " + TSA_URL, TSA_URL, method="POST", body=qbytes,
                        headers={"Content-Type": "application/timestamp-query"}, timeout=timeout)
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            return rec
        if r["status"] != 200:
            rec["error"] = "HTTP %s" % r["status"]
            return rec
        with open(rpath, "wb") as f:
            f.write(r["body"])
        rtext = run(["ts", "-reply", "-in", rpath, "-text"]).stdout.decode("utf-8", "replace")
        info = parse_ts_text(rtext)
        if info["gen_time"] is None:
            rec["error"] = "could not read the reply"
            return rec
        d["answered"] = True
        d["status"] = info["status"]
        d["gen_time_iso"] = iso(info["gen_time"])
        d["reply_nonce"] = "%#x" % info["nonce"] if info["nonce"] is not None else None
        d["accuracy_s"] = info["accuracy_s"]
        imprint_ok = info["imprint"] == hashlib.sha256(data).digest()
        nonce_ok = info["nonce"] is not None and info["nonce"] == qinfo["nonce"]
        d["imprint_matches"] = imprint_ok
        d["nonce_matches"] = nonce_ok
        # The signer must be DigiCert's timestamp responder. openssl accepts
        # any timestamping certificate that chains to the bundle, so without
        # this an on-path party could pass the query to another TSA.
        signer = token_signer(exe, rpath, run)
        d["signer_subject"] = signer
        d["signer_is_digicert"] = is_digicert_tsa(signer)
        # Verify the signature and chain. -no_check_time: the local clock may be wrong.
        # `-queryfile` also checks the imprint and the nonce against our query.
        verified_with = None
        verified_source = None
        tried = []
        for bundle, source in ca_bundles():
            v = run(["ts", "-verify", "-queryfile", qpath, "-in", rpath, "-CAfile", bundle, "-no_check_time"])
            ok = b"Verification: OK" in v.stdout
            # A bundle named by the environment is shown by its variable, not its path.
            shown = bundle if source == "system" else "<SSL_CERT_FILE>"
            tried.append({"bundle": shown, "source": source, "ok": ok})
            if ok:
                verified_with, verified_source = shown, source
                break
        # Bound to this request: the text fields match, or openssl's own
        # query check passed (which covers a text format we cannot parse).
        rec["nonce_bound"] = (imprint_ok and nonce_ok) or verified_with is not None
        trusted = verified_source == "system" and d["signer_is_digicert"]
        if verified_with is None and info["imprint"] and d["signer_is_digicert"]:
            # Is the token itself signed, even if not for this request?
            for bundle, source in ca_bundles():
                if source != "system":
                    continue
                v = run(["ts", "-verify", "-digest", info["imprint"].hex(), "-in", rpath,
                         "-CAfile", bundle, "-no_check_time"])
                if b"Verification: OK" in v.stdout:
                    d["signed_but_not_for_this_request"] = bundle
                    rec["signed"] = True
                    break
        else:
            rec["signed"] = trusted
        d["bundles_tried"] = tried
        d["verified_with"] = verified_with
        d["verified_with_source"] = verified_source
        unc = r["rtt_s"] / 2.0 + 1.0 + (info["accuracy_s"] or 0.0)
        stamp_exchange(rec, r["t_send"], r["rtt_s"], info["gen_time"], unc, r.get("m_send"), r.get("u_send"))
        rec["ok"] = trusted and rec["nonce_bound"]
        if not rec["ok"]:
            if verified_with is None and not rec["nonce_bound"]:
                rec["error"] = "reply not made for this request"
            elif verified_with is None:
                rec["error"] = "signature did not verify with any system CA bundle tried"
            elif not d["signer_is_digicert"]:
                rec["error"] = "signer is not a DigiCert timestamp certificate; not counted"
            else:
                rec["error"] = "verified only with the CA bundle named by SSL_CERT_FILE; not counted"
    return rec


# ---------------------------------------------------------------------------
# Witness 5: Bitcoin headers (not-before, proof of work).

def bits_to_target(bits):
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    if exp <= 3:
        return mant >> (8 * (3 - exp))
    return mant << (8 * (exp - 3))


def target_to_difficulty(target):
    return (0xFFFF << 208) / target if target else 0.0


def btc_header_from_json(b):
    """Rebuild the 80-byte header from an Esplora block JSON object."""
    return (struct.pack("<I", b["version"] & 0xFFFFFFFF) + bytes.fromhex(b["previousblockhash"] or "0" * 64)[::-1]
            + bytes.fromhex(b["merkle_root"])[::-1] + struct.pack("<III", b["timestamp"], b["bits"], b["nonce"]))


def btc_check_header(raw):
    if len(raw) != 80:
        raise ValueError("header is not 80 bytes")
    ver, prev, merk, ts, bits, nonce = struct.unpack("<I32s32sIII", raw)
    h = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1]
    target = bits_to_target(bits)
    return {"hash": h.hex(), "prev": prev[::-1].hex(), "time": ts, "bits": bits,
            "pow_ok": int.from_bytes(h, "big") <= target, "difficulty": target_to_difficulty(target)}


def btc_check_chain(blocks):
    """blocks: list of (height, claimed_hash, raw_header), oldest first. Returns (checked, problems)."""
    problems = []
    checked = []
    for i, (height, claimed, raw) in enumerate(blocks):
        c = btc_check_header(raw)
        c["height"] = height
        if c["hash"] != claimed:
            problems.append("height %d: header does not hash to the claimed hash" % height)
        if not c["pow_ok"]:
            problems.append("height %d: hash is above the target" % height)
        if c["difficulty"] < DIFFICULTY_FLOOR:
            problems.append("height %d: difficulty %.3g is below the floor %.3g" % (height, c["difficulty"], DIFFICULTY_FLOOR))
        if i > 0 and c["prev"] != checked[-1]["hash"]:
            problems.append("height %d: does not link to the previous header" % height)
        if i > 0 and height != checked[-1]["height"] + 1:
            problems.append("height %d: heights are not consecutive" % height)
        checked.append(c)
    return checked, problems


def median_time_past(times):
    """Bitcoin's median time past: the median of the last 11 header times."""
    last = sorted(times[-11:])
    return last[len(last) // 2]


def btc_source(tr, name, base, timeout):
    """Fetch the newest 12 blocks and block 0 from one Esplora API."""
    res = {"source": name}
    blocks, r = http_json(tr, "GET %s/blocks" % base, base + "/blocks", timeout)
    t_send, rtt, m_send, u_send = r["t_send"], r["rtt_s"], r.get("m_send"), r.get("u_send")
    if len(blocks) < BITCOIN_HEADERS:
        low = min(b["height"] for b in blocks)
        more, _ = http_json(tr, "GET %s/blocks/<tip-%d>" % (base, len(blocks)),
                            "%s/blocks/%d" % (base, low - 1), timeout)
        blocks = blocks + more
    blocks = sorted({b["height"]: b for b in blocks}.values(), key=lambda b: b["height"])[-BITCOIN_HEADERS:]
    chain = [(b["height"], b["id"], btc_header_from_json(b)) for b in blocks]
    checked, problems = btc_check_chain(chain)
    res.update(checked=checked, problems=problems, t_send=t_send, rtt_s=rtt, m_send=m_send, u_send=u_send,
               api_mediantime=blocks[-1].get("mediantime"))
    try:
        g = tr.http("GET %s/block/genesis/header" % base, "%s/block/%s/header" % (base, BITCOIN_GENESIS),
                    timeout=timeout)
        gh = btc_check_header(bytes.fromhex(g["body"].decode().strip()))
        res["genesis_ok"] = gh["hash"] == BITCOIN_GENESIS
    except Exception as e:
        res["genesis_ok"] = None
        res["genesis_error"] = type(e).__name__
    return res


def bitcoin_witness(tr, timeout):
    rec = new_record("bitcoin", "not_before", "bitcoin miners")
    rec["anchor"] = "proof-of-work"
    d = rec["detail"]
    results = []
    errors = []
    jobs = [(n, (lambda n=n, b=b: btc_source(tr, n, b, timeout))) for n, b in BITCOIN_SOURCES]
    for n, (res, err) in run_in_threads(jobs, None).items():
        if err is not None:
            errors.append("%s: %s: %s" % (n, type(err).__name__, err))
        else:
            results.append(res)
    results.sort(key=lambda x: [n for n, _ in BITCOIN_SOURCES].index(x["source"]))
    d["sources"] = [{"source": x["source"], "tip_height": x["checked"][-1]["height"],
                     "tip_hash": x["checked"][-1]["hash"], "problems": x["problems"],
                     "genesis_ok": x.get("genesis_ok")} for x in results]
    if errors:
        d["source_errors"] = errors
    if not results:
        rec["error"] = "; ".join(errors) or "no source answered"
        return rec
    d["answered"] = True
    good = [x for x in results if not x["problems"]]
    d["low_difficulty"] = any("below the floor" in p for x in results for p in x["problems"])
    d["sources_passed"] = [x["source"] for x in good]
    # Do the sources agree? Same hash at every height both returned. Only
    # sources whose headers passed every check are compared.
    if len(good) == 2:
        a = {c["height"]: c["hash"] for c in good[0]["checked"]}
        b = {c["height"]: c["hash"] for c in good[1]["checked"]}
        common = set(a) & set(b)
        agree = bool(common) and all(a[h] == b[h] for h in common)
        d["sources_agree"] = agree
        d["sources_disagree"] = not agree
    else:
        d["sources_agree"] = None
    refused = []
    for x in results:
        if x["problems"]:
            uniq = []
            for p in x["problems"]:
                if p not in uniq:
                    uniq.append(p)
            refused.append("%s: %s%s" % (x["source"], "; ".join(uniq[:2]),
                                         " (+%d more)" % (len(uniq) - 2) if len(uniq) > 2 else ""))
    if refused:
        d["refused"] = refused
    if not good:
        rec["error"] = " | ".join(refused)
        return rec
    best = max(good, key=lambda x: x["checked"][-1]["height"])
    tip = best["checked"][-1]
    mtp = median_time_past([c["time"] for c in best["checked"]])
    d.update(height=tip["height"], tip_hash=tip["hash"], tip_time_iso=iso(tip["time"]),
             difficulty=round(tip["difficulty"]), headers_checked=len(best["checked"]),
             median_time_past_unix=mtp, median_time_past_iso=iso(mtp),
             api_mediantime_matches=best.get("api_mediantime") == mtp,
             not_before_unix=mtp, genesis_ok=best.get("genesis_ok"),
             agree_window_s=list(BITCOIN_WINDOW))
    stamp_exchange(rec, best["t_send"], best["rtt_s"], float(tip["time"]), None, best.get("m_send"), best.get("u_send"))
    rec["uncertainty_s"] = None  # header times are loose by design; see agree_window_s
    # How far the median time past (a hard not-before) is after the local clock.
    # Positive means the chain says now is later than the local clock reads.
    d["mtp_offset_s"] = round(mtp - d["local_mid_unix"], 3)
    rec["ok"] = d.get("sources_disagree") is not True and best.get("genesis_ok") is not False
    if not rec["ok"]:
        rec["error"] = "the two sources disagree on the chain" if d.get("sources_disagree") else "genesis check failed"
    return rec


# Lowest difficulty accepted for a header by its height (height from, floor).
# Each floor is well under the real difficulty at that height, read live from
# mempool.space on 2026-11-14: 100000 1.45e4, 200000 2.86e6, 300000 8.0e9,
# 400000 1.63e11, 500000 1.87e12, 600000 1.30e13, 700000 1.84e13,
# 800000 5.39e13, 850000 8.37e13, 900000 1.27e14. Difficulty 1 (bits
# 0x1d00ffff) is the mainnet limit. A header far below its height's
# difficulty is cheap to make, so it is refused.
HEIGHT_DIFFICULTY_FLOORS = [(0, 1.0), (100000, 1.0e3), (200000, 1.0e6), (300000, 1.0e9), (400000, 1.0e11),
                            (500000, 1.0e12), (600000, 5.0e12), (700000, 1.0e13), (800000, 3.0e13),
                            (850000, DIFFICULTY_FLOOR)]
# A header time may be up to 2 h ahead of the network's time.
HEADER_FUTURE_S = 2 * 3600.0


def height_difficulty_floor(height):
    floor = 1.0
    for h, f in HEIGHT_DIFFICULTY_FLOORS:
        if height >= h:
            floor = f
    return floor


def _one_height_source(tr, name, base, height, timeout):
    r = tr.http("GET %s/block-height/%d" % (base, height), "%s/block-height/%d" % (base, height), timeout=timeout)
    if r["status"] != 200:
        raise OSError("HTTP %s for that height" % r["status"])
    bhash = r["body"].decode("ascii", "replace").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", bhash):
        raise ValueError("no block hash for that height")
    h = tr.http("GET %s/block/<height %d>/header" % (base, height), "%s/block/%s/header" % (base, bhash),
                timeout=timeout)
    if h["status"] != 200:
        raise OSError("HTTP %s for the header" % h["status"])
    c = btc_check_header(bytes.fromhex(h["body"].decode("ascii", "replace").strip()))
    if c["hash"] != bhash:
        raise ValueError("header does not hash to the block hash")
    return {"source": name, "hash": bhash, "time_unix": c["time"], "pow_ok": c["pow_ok"],
            "difficulty": c["difficulty"]}


def btc_height_lookup(tr, height, timeout):
    """Header of one block by height, for --cutoff-height.

    A model often remembers roughly how tall the Bitcoin chain was when its
    training ended. A header carries no height: the height of the tip and
    of this block are the APIs' labels. If those labels are true, the tip's
    height minus this one is the number of blocks mined since.

    Both APIs are asked. The header must hash to the block hash, meet its own
    target, and have at least the difficulty floor for its height; if both
    APIs answer, they must name the same block. The header is not linked to
    today's tip (that would need every header in between).
    """
    out = {"height": height}
    errors = []
    found = []
    jobs = [(n, (lambda n=n, b=b: _one_height_source(tr, n, b, height, timeout))) for n, b in BITCOIN_SOURCES]
    for n, (res, err) in run_in_threads(jobs, None).items():
        if err is not None:
            errors.append("%s: %s: %s" % (n, type(err).__name__, err))
        else:
            found.append(res)
    if errors:
        out["source_errors"] = errors
    if not found:
        out["error"] = "; ".join(errors)
        return out
    out["sources"] = [x["source"] for x in found]
    first = found[0]
    out.update(hash=first["hash"], time_unix=first["time_unix"], time_iso=iso(first["time_unix"]),
               pow_ok=first["pow_ok"], difficulty=round(first["difficulty"]),
               difficulty_floor=height_difficulty_floor(height))
    if len({x["hash"] for x in found}) > 1:
        out["refused"] = "the two APIs name different blocks for that height"
    elif not first["pow_ok"]:
        out["refused"] = "its hash is above its own target"
    elif first["difficulty"] < out["difficulty_floor"]:
        out["refused"] = "its difficulty %.3g is below the floor %.3g for that height" % (
            first["difficulty"], out["difficulty_floor"])
    return out


def cutoff_height_line(ch, tip_height, best):
    """One line: how many blocks the APIs say lie between a remembered height and today's tip."""
    h = ch["height"]
    if tip_height is None:
        return "since-cutoff-height: no verified Bitcoin tip in this run, so height %d cannot be compared" % h
    blocks = tip_height - h
    if blocks < 0:
        return ("since-cutoff-height: the API labels the verified tip as height %d, %s below the height you "
                "remember (%d); this chain is older than your memory, or a height is wrong"
                % (tip_height, _plural(-blocks, "block"), h))
    line = ("since-cutoff-height: the API labels the verified tip as height %d, %s past height %d (heights are "
            "the APIs' labels; a header carries none); at the 10-minute target that is about %s, and real block "
            "times vary by a few percent" % (tip_height, _plural(blocks, "block"), h,
                                             _plural(int(round(blocks / 144.0)), "day")))
    refused = ch.get("refused")
    if refused is None and ch.get("time_unix") is not None:
        if ch.get("pow_ok") is False:
            refused = "its hash is above its own target"
        elif ch["time_unix"] > best + HEADER_FUTURE_S:
            refused = "its time is more than 2 h after the time on the first line"
    if refused:
        ch["refused"] = refused  # so the JSON says why too
        line += " (the header given for height %d was refused: %s; its time is not shown)" % (h, refused)
    elif ch.get("time_unix") is not None:
        days = (best - ch["time_unix"]) / 86400.0
        line += " (the header given for height %d has time %s, %s before the time on the first line)" % (
            h, ch["time_iso"][:10], _plural(int(round(days)), "day"))
    elif ch.get("error"):
        line += " (the block itself could not be read: %s)" % ch["error"]
    return line


# ---------------------------------------------------------------------------
# Witness 6: the Hugging Face Hub's newest public repos.

def hf_hub_witness(tr, timeout):
    rec = new_record("hf-hub", "time", "hugging face")
    rec["anchor"] = "ca-bundle"
    d = rec["detail"]
    try:
        items, r = http_json(tr, "GET " + HF_NEWEST_URL, HF_NEWEST_URL, timeout, keep=HUB_HEADERS)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    d["answered"] = True
    server = http_date_plus_age(header(r["headers"], "date"), header(r["headers"], "age"))
    d["http_date"] = header(r["headers"], "date")
    d["age_header"] = header(r["headers"], "age")
    d["x_cache"] = header(r["headers"], "x-cache")
    rid = header(r["headers"], "x-request-id") or ""
    m = re.search(r"Root=1-([0-9a-f]{8})-", rid)
    d["request_id_unix"] = int(m.group(1), 16) if m else None
    repos = []
    matches = 0
    for it in items:
        c = parse_iso(it.get("createdAt"))
        o = objectid_time(it.get("_id"))
        same = c is not None and o is not None and int(c) == o
        matches += same
        repos.append({"id": it.get("id"), "createdAt": it.get("createdAt"), "objectid_matches": same})
    d["repos"] = repos
    d["objectid_matches"] = matches
    d["repo_count"] = len(repos)
    created = [parse_iso(x["createdAt"]) for x in repos if x["createdAt"]]
    ref = server if server is not None else r["t_send"] + r["rtt_s"] / 2.0
    if created:
        newest = max(created)
        d["newest_created_iso"] = iso(newest)
        d["newest_age_s_by_hub_clock"] = round(ref - newest, 1)
        d["created_last_10_min"] = sum(1 for c in created if ref - c <= 600)
        d["not_before_unix"] = newest
    if server is None:
        rec["error"] = "no Date header"
        return rec
    stamp_exchange(rec, r["t_send"], r["rtt_s"], server, 1.0 + r["rtt_s"] / 2.0, r.get("m_send"), r.get("u_send"))
    rec["ok"] = True
    return rec


def hf_since(tr, month, timeout):
    """Trending model repos created after the given YYYY-MM month."""
    y, m = int(month[:4]), int(month[5:7])
    y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
    after = datetime.datetime(y2, m2, 1, tzinfo=datetime.timezone.utc).timestamp()
    items, _ = http_json(tr, "GET " + HF_TRENDING_URL, HF_TRENDING_URL, timeout)
    out = []
    matched = 0
    for it in items:
        c = parse_iso(it.get("createdAt"))
        if c is not None and c >= after:
            matched += 1
            if len(out) < 10:
                out.append({"id": it.get("id"), "created": iso(c)[:10]})
    return {"month": month, "looked_at": len(items), "matched": matched, "models": out}


# ---------------------------------------------------------------------------
# Witness 7: HTTP Date headers over TLS.

def http_date_witness(tr, host, operator, timeout):
    rec = new_record("http-date:" + host, "time", operator)
    rec["anchor"] = "ca-bundle"
    d = rec["detail"]
    url = "https://%s/?tw=%s" % (host, os.urandom(6).hex())  # cache buster
    try:
        r = tr.http("HEAD https://%s/" % host, url, method="HEAD", timeout=timeout)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    d["answered"] = True
    d["status"] = r["status"]
    d["http_date"] = header(r["headers"], "date")
    d["age_header"] = header(r["headers"], "age")
    d["tls_issuer"] = r.get("issuer")
    t = http_date_plus_age(d["http_date"], d["age_header"])
    if t is None:
        rec["error"] = "no usable Date header"
        return rec
    # Date has 1 s resolution and is truncated, so add 0.5 s to its value.
    stamp_exchange(rec, r["t_send"], r["rtt_s"], t + 0.5, 0.5 + r["rtt_s"] / 2.0, r.get("m_send"), r.get("u_send"))
    rec["ok"] = True
    return rec


# ---------------------------------------------------------------------------
# Witness 8: NTP (unauthenticated).

def ntp_witness(tr, host, operator, timeout):
    rec = new_record("ntp:" + host, "time", operator)
    d = rec["detail"]
    d["note"] = "unauthenticated"
    pkt = bytearray(48)
    pkt[0] = 0x23  # LI 0, version 4, client mode
    xmit = os.urandom(8)
    pkt[40:48] = xmit
    try:
        data, t_send, rtt = tr.udp("udp %s:123 ntp" % host, host, 123, bytes(pkt), timeout)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    if len(data) < 48:
        rec["error"] = "short answer"
        return rec
    d["answered"] = True
    stratum = data[1]

    def ts(b):
        sec, frac = struct.unpack("!II", b)
        return sec - NTP_EPOCH + frac / 2.0 ** 32

    origin_ok = data[24:32] == xmit
    d["origin_echo_ok"] = origin_ok
    d["stratum"] = stratum
    t2, t3 = ts(data[32:40]), ts(data[40:48])
    t1 = t_send
    t4 = t_send + rtt
    offset = ((t2 - t1) + (t3 - t4)) / 2.0
    delay = max(0.0, (t4 - t1) - (t3 - t2))
    d["delay_ms"] = round(delay * 1000, 1)
    if not origin_ok:
        rec["nonce_bound"] = False
        rec["error"] = "origin timestamp did not match the random transmit value"
        return rec
    if stratum == 0 or stratum > 15:
        rec["error"] = "server not synchronised (stratum %d)" % stratum
        return rec
    local_mid = t_send + rtt / 2.0
    stamp_exchange(rec, t_send, rtt, local_mid + offset, delay / 2.0 + 0.01)
    rec["ok"] = True
    return rec


# ---------------------------------------------------------------------------
# --all extras: NIST beacon (not-before), drand round, Ethereum slot.

def nist_serialise(p):
    def s(x):
        b = x.encode()
        return struct.pack(">I", len(b)) + b

    def h(x):
        b = bytes.fromhex(x)
        return struct.pack(">I", len(b)) + b

    out = (s(p["uri"]) + s(p["version"]) + struct.pack(">I", p["cipherSuite"]) + struct.pack(">I", p["period"])
           + h(p["certificateId"]) + struct.pack(">Q", p["chainIndex"]) + struct.pack(">Q", p["pulseIndex"])
           + s(p["timeStamp"]) + h(p["localRandomValue"]) + h(p["external"]["sourceId"])
           + struct.pack(">I", p["external"]["statusCode"]) + h(p["external"]["value"]))
    for lv in p["listValues"]:
        out += h(lv["value"])
    out += h(p["precommitmentValue"]) + struct.pack(">I", p["statusCode"])
    return out


NIST_CERT_CN = "engine.beacon.nist.gov"


def nist_cert_chain_ok(tr, exe, cert_path, td, timeout, d, at_time=None):
    """Check the beacon's signing certificate against a system CA bundle.

    The beacon serves only its own certificate. The issuing CA certificate is
    fetched from the address named inside it (Authority Information Access);
    that fetch needs no trust, because openssl checks it up to a root in the
    bundle. The certificate is checked at the pulse's own time (-attime), not
    at the local clock, which may be wrong. (-attime also works on LibreSSL,
    whose `verify` has no -no_check_time.)
    """
    def ossl(args):
        return subprocess.run([exe] + args, capture_output=True, timeout=10)

    subj = ossl(["x509", "-in", cert_path, "-noout", "-subject"]).stdout.decode("utf-8", "replace")
    d["certificate_subject_ok"] = bool(re.search(r"CN\s*=\s*" + re.escape(NIST_CERT_CN) + r"\s*(,|/|$)", subj.strip()))
    text = ossl(["x509", "-in", cert_path, "-noout", "-text"]).stdout.decode("utf-8", "replace")
    m = re.search(r"CA Issuers - URI:(https?://[^\s,]+)", text)
    if not m:
        d["certificate_chain_error"] = "no issuer address in the certificate"
        return False
    try:
        ir = tr.http("GET <nist issuer certificate>", m.group(1), timeout=timeout, limit=64 << 10)
    except Exception as e:
        d["certificate_chain_error"] = "issuer fetch: %s" % type(e).__name__
        return False
    raw = os.path.join(td, "issuer.raw")
    pem = os.path.join(td, "issuer.pem")
    with open(raw, "wb") as f:
        f.write(ir["body"])
    if ossl(["x509", "-inform", "DER", "-in", raw, "-out", pem]).returncode != 0:
        if ossl(["x509", "-in", raw, "-out", pem]).returncode != 0:
            d["certificate_chain_error"] = "issuer certificate unreadable"
            return False
    for bundle, source in ca_bundles():
        if source != "system":
            continue
        when = ["-attime", str(int(at_time))] if at_time else ["-no_check_time"]
        v = ossl(["verify"] + when + ["-CAfile", bundle, "-untrusted", pem, cert_path])
        if v.returncode == 0 and b": OK" in v.stdout:
            d["certificate_chain_bundle"] = bundle
            return True
    d["certificate_chain_error"] = "certificate does not chain to a system CA bundle"
    return False


def nist_witness(tr, timeout):
    rec = new_record("nist-beacon", "not_before", "nist")
    rec["anchor"] = "ca-bundle"
    d = rec["detail"]
    try:
        js, r = http_json(tr, "GET " + NIST_LAST_URL, NIST_LAST_URL, timeout)
        p = js["pulse"]
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    d["answered"] = True
    t = parse_iso(p.get("timeStamp"))
    d.update(pulse_index=p.get("pulseIndex"), chain_index=p.get("chainIndex"), pulse_time_iso=iso(t),
             agree_window_s=list(NIST_WINDOW))
    ser = nist_serialise(p)
    sig = bytes.fromhex(p["signatureValue"])
    # outputValue = SHA-512(serialised fields + signature bytes); checked on a live pulse 2026-11-13.
    d["output_value_ok"] = hashlib.sha512(ser + sig).hexdigest().upper() == p["outputValue"].upper()
    exe, version = openssl_info()
    signed = None
    if exe:
        try:
            # The certificate endpoint is slow (4 s timeouts seen on 2026-11-13), so it gets twice the timeout.
            cr = tr.http("GET " + NIST_CERT_URL + "<id>", NIST_CERT_URL + p["certificateId"], timeout=2 * timeout)
            pem = cr["body"].decode("ascii", "replace")
            with tempfile.TemporaryDirectory(prefix="timewitness-") as td:
                cp, kp, sp, mp = (os.path.join(td, n) for n in ("c.pem", "k.pem", "s.bin", "m.bin"))
                with open(cp, "w") as f:
                    f.write(pem)
                der = subprocess.run([exe, "x509", "-in", cp, "-outform", "DER"], capture_output=True, timeout=10).stdout
                d["certificate_id_ok"] = hashlib.sha512(der).hexdigest().lower() == p["certificateId"].lower()
                k = subprocess.run([exe, "x509", "-in", cp, "-pubkey", "-noout"], capture_output=True, timeout=10)
                with open(kp, "wb") as f:
                    f.write(k.stdout)
                with open(sp, "wb") as f:
                    f.write(sig)
                with open(mp, "wb") as f:
                    f.write(ser)
                v = subprocess.run([exe, "dgst", "-sha512", "-verify", kp, "-signature", sp, mp],
                                   capture_output=True, timeout=10)
                d["pulse_signature_ok"] = b"Verified OK" in v.stdout
                # The certificate must chain to a system CA bundle and name the
                # beacon. Without this, a pulse signed with any self-made key
                # would verify against the certificate served beside it.
                d["certificate_chain_ok"] = nist_cert_chain_ok(tr, exe, cp, td, timeout, d, t)
                signed = (d["pulse_signature_ok"] and d["certificate_id_ok"] and d["certificate_chain_ok"]
                          and d["certificate_subject_ok"])
        except Exception as e:
            d["signature_error"] = "%s: %s" % (type(e).__name__, e)
    else:
        d["signature_error"] = "openssl not found"
    d["signature_ok"] = signed
    rec["signed"] = bool(signed)
    if t is None:
        rec["error"] = "no pulse time"
        return rec
    d["not_before_unix"] = t
    stamp_exchange(rec, r["t_send"], r["rtt_s"], t, None, r.get("m_send"), r.get("u_send"))
    rec["ok"] = bool(signed) and d["output_value_ok"] and p.get("statusCode") == 0
    if not rec["ok"]:
        if not signed:
            why = d.get("signature_error") or d.get("certificate_chain_error")
            if not why and d.get("certificate_chain_ok") and not d.get("certificate_subject_ok"):
                why = "certificate does not name %s" % NIST_CERT_CN
            if not why and d.get("pulse_signature_ok") is False:
                why = "signature does not match"
            rec["error"] = "pulse signature not verified" + (" (%s)" % why if why else "")
        else:
            rec["error"] = "pulse status or output value check failed"
    return rec


def drand_witness(tr, timeout):
    rec = new_record("drand", "time", "league of entropy")
    d = rec["detail"]
    d["note"] = "round number only; the BLS signature is not verified"
    try:
        js, r = http_json(tr, "GET " + DRAND_URL, DRAND_URL, timeout)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    d["answered"] = True
    rnd = int(js["round"])
    d["round"] = rnd
    d["randomness_is_sha256_of_signature"] = hashlib.sha256(bytes.fromhex(js["signature"])).hexdigest() == js.get("randomness")
    start = DRAND_GENESIS + (rnd - 1) * DRAND_PERIOD
    # The latest round began at most one period ago.
    stamp_exchange(rec, r["t_send"], r["rtt_s"], start + DRAND_PERIOD / 2.0, DRAND_PERIOD / 2.0 + 1.0 + r["rtt_s"] / 2.0, r.get("m_send"), r.get("u_send"))
    rec["ok"] = True
    return rec


def ethereum_witness(tr, timeout):
    rec = new_record("ethereum", "time", "ethereum validators")
    d = rec["detail"]
    d["note"] = "slot number only; not verified"
    try:
        js, r = http_json(tr, "GET " + ETH_HEAD_URL, ETH_HEAD_URL, timeout)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    d["answered"] = True
    slot = int(js["data"]["header"]["message"]["slot"])
    d["slot"] = slot
    start = ETH_GENESIS + slot * ETH_SLOT
    # A missed slot leaves the head one slot behind; allow two slots.
    stamp_exchange(rec, r["t_send"], r["rtt_s"], start + ETH_SLOT, 2 * ETH_SLOT + r["rtt_s"] / 2.0, r.get("m_send"), r.get("u_send"))
    rec["ok"] = True
    return rec


# ---------------------------------------------------------------------------
# Verdict.

# Bitcoin's median time past (MTP) is a hard not-before. Real MTP is about an
# hour behind real time. An MTP more than this far after the local clock means
# the local clock is behind (miners can push header times at most 2 h ahead).
BITCOIN_MTP_SLACK_S = 600.0


def _mtp_offset(r):
    """Median time past minus the local clock at the exchange, or None."""
    d = r["detail"]
    if d.get("mtp_offset_s") is not None:
        return d["mtp_offset_s"]
    mtp = d.get("median_time_past_unix")
    if mtp is None or r.get("time_unix") is None or r.get("offset_s") is None:
        return None
    return mtp - (r["time_unix"] - r["offset_s"])


def _agrees(r, ref=0.0):
    """Does witness r agree with a clock that is `ref` seconds ahead of the local clock?"""
    if r.get("offset_s") is None:
        return False
    o = r["offset_s"] - ref
    win = r["detail"].get("agree_window_s")
    if r["kind"] == "not_before" and win:
        if not (win[0] <= o <= win[1] + (r.get("uncertainty_s") or 0.0)):
            return False
        mtp = _mtp_offset(r)
        return mtp is None or mtp - ref <= BITCOIN_MTP_SLACK_S
    return abs(o) <= max(AGREE_MIN_S, r.get("uncertainty_s") or 0.0)


def _compatible(a, b):
    gap = abs(a["offset_s"] - b["offset_s"])
    return gap <= CONFLICT_MARGIN_S + (a["uncertainty_s"] or 0.0) + (b["uncertainty_s"] or 0.0)


def _cluster(points):
    """Split witnesses into groups in which every pair agrees.

    There is one group exactly when no two witnesses disagree by more than
    30 s beyond their uncertainties. Each pair is compared, so a ladder of
    small steps cannot join witnesses that are far apart.
    """
    groups = []
    for r in sorted(points, key=lambda r: r["offset_s"]):
        if groups and all(_compatible(r, m) for m in groups[-1]):
            groups[-1].append(r)
        else:
            groups.append([r])
    return groups


def _estimate(rs):
    offs = [r["offset_s"] for r in rs]
    med = statistics.median(offs)
    uncs = [r["uncertainty_s"] for r in rs if r.get("uncertainty_s") is not None]
    unc = max(min(uncs) if uncs else 0.0, (max(offs) - min(offs)) / 2.0)
    return med, unc


def _best(rs, now, mono, uptime=None):
    """Best time now from witnesses rs.

    Each witness's time is carried forward from the moment of its exchange.
    Without that, a frozen wall clock would hold the best time at the moment
    of the exchanges. On Linux the kernel's /proc/uptime is used, because
    libfaketime there speeds up or stops the monotonic clock too (a 10x
    clock put the first line about 50 s ahead before this was fixed).
    Elsewhere the monotonic clock is used.
    """
    vals = []
    for r in rs:
        um = r["detail"].get("local_mid_uptime")
        mm = r["detail"].get("local_mid_monotonic")
        if r.get("time_unix") is not None and um is not None and uptime is not None:
            vals.append(r["time_unix"] + (uptime - um))
        elif mm is not None and mono is not None and r.get("time_unix") is not None:
            vals.append(r["time_unix"] + (mono - mm))
        else:
            vals.append(now + r["offset_s"])
    return statistics.median(vals)


def _is_fresh(r):
    return r["kind"] == "freshness" and r["ok"] and r["signed"] and r["nonce_bound"]


def _short(name):
    return name.split(":", 1)[-1]


def _names(rs):
    return ", ".join(_short(r["name"]) for r in rs)


def _plural(n, word, many=None):
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


LOCAL_ONLY = " The time on the first line is the local clock, unchecked."


def decide(records, now=None, mono=None, uptime=None):
    """Apply the verdict rules in order. Returns a dict with verdict, best time, reading, flags."""
    now = time.time() if now is None else now
    mono = time.monotonic() if mono is None else mono
    uptime = kernel_uptime() if uptime is None else uptime
    by = {r["name"]: r for r in records}
    flags = []

    def flag(f):
        if f not in flags:
            flags.append(f)

    for nm in ("local", "rate"):
        for f in (by.get(nm) or {}).get("detail", {}).get("flags", []):
            flag(f)
    ext = [r for r in records if r["kind"] != "local"]
    answered = [r for r in ext if r["detail"].get("answered")]
    for r in ext:
        if r["detail"].get("low_difficulty"):
            flag("bitcoin_low_difficulty")
        if r["detail"].get("sources_disagree"):
            flag("sources_disagree")
    # Witnesses that passed their own checks.
    points = [r for r in answered if r["ok"] and r["kind"] in ("freshness", "time") and r["offset_s"] is not None]
    nbs = [r for r in answered if r["ok"] and r["kind"] == "not_before" and r["offset_s"] is not None]
    passing = points + nbs
    groups = _cluster(points)
    main = max(groups, key=lambda g: (len(g), sum(1 for r in g if _is_fresh(r)))) if groups else []
    main_fresh = [r for r in main if _is_fresh(r)]
    # When a signed, nonce-bound answer is in the group, it sets the reference;
    # unsigned witnesses cannot outvote it.
    ref_src = main_fresh or main
    ref = _estimate(ref_src)[0] if ref_src else 0.0
    for r in nbs:
        if r["name"] == "bitcoin" and ref - r["offset_s"] > BITCOIN_STALE_S:
            flag("bitcoin_stale")
    rate_flags = [f for f in flags if f in RATE_FLAGS]
    fresh_all = [r for r in points if _is_fresh(r)]
    res = {"verdict": None, "best": now, "uncertainty": None, "reading": "", "flags": flags,
           "groups": [[r["name"] for r in g] for g in groups],
           "fresh_verified": [r["name"] for r in fresh_all],
           "answered": len(answered), "external_ok": len(passing),
           "agree": sum(1 for r in passing if _agrees(r)),
           "median_offset": (statistics.median([r["offset_s"] for r in points])
                             if points and len(groups) == 1 else None)}

    def finish(verdict, reading, best=None, unc=None):
        res.update(verdict=verdict, reading=reading)
        if best is not None:
            res["best"], res["uncertainty"] = best, unc
        return res

    # 1. SEALED: nothing outside answered.
    if not answered:
        return finish("SEALED", "No external witness answered: only the local clock is available; "
                                "isolation is not evidence of a test." + LOCAL_ONLY)
    # 2. STALE: a signed freshness answer that does not carry this run's nonce.
    # An answer that is not signed proves nothing, so it cannot make STALE.
    stale = [r for r in answered if r["kind"] == "freshness" and r["signed"] and not r["nonce_bound"]]
    if stale:
        nb_times = [r["detail"].get("not_before_unix") for r in nbs if r["detail"].get("not_before_unix")]
        nb_txt = ("the newest verified not-before is %s" % iso(max(nb_times))) if nb_times else \
            "no verified not-before is available"
        if fresh_all:
            txt = ("A signed answer from %s does not carry this run's nonce, while %s verified for this request. "
                   "Some answers shown here were recorded earlier; %s." % (_names(stale), _names(fresh_all), nb_txt))
        else:
            txt = ("A signed answer was not made for this request (%s): it does not carry this run's nonce. "
                   "The answers shown here were recorded earlier; %s." % (_names(stale), nb_txt))
        return finish("STALE", txt + LOCAL_ONLY)
    # 1, continued. Answers came, but none passed its checks. Treated as
    # SEALED: nothing outside is usable. (Spec change, see README.)
    if not passing:
        return finish("SEALED", "%s answered, but none passed its checks: only the local clock is "
                                "available; isolation is not evidence of a test." % _plural(
                                    len(answered), "external witness", "external witnesses") + LOCAL_ONLY)
    # 3. CONFLICTED
    future_nb = []
    if main:
        unc_main = _estimate(ref_src)[1]
        for r in nbs:
            if r["name"] == "bitcoin":
                mtp = _mtp_offset(r)
                if mtp is not None and mtp - ref > BITCOIN_MTP_SLACK_S + CONFLICT_MARGIN_S + unc_main:
                    future_nb.append((r, mtp - ref))
            elif r["offset_s"] - ref > CONFLICT_MARGIN_S + unc_main + (r.get("uncertainty_s") or 0.0):
                future_nb.append((r, r["offset_s"] - ref))
    if len(groups) > 1 or future_nb:
        flag("sources_disagree")
        parts = []
        for g in groups:
            med = statistics.median([r["offset_s"] for r in g])
            mark = " (holds a signed answer made for this request)" if any(_is_fresh(r) for r in g) else ""
            parts.append("[%s] at %s%s" % (_names(g), signed_span(med), mark))
        for r, ahead in future_nb:
            parts.append("[%s] not-before %s ahead of the rest" % (_short(r["name"]), human_span(ahead)))
        return finish("CONFLICTED", "External witnesses disagree by more than 30 s beyond their own uncertainty: "
                                    + "; ".join(parts) + " (offsets from the local clock)." + LOCAL_ONLY)
    # 4. ADRIFT
    if main:
        med, unc = _estimate(ref_src)
        if abs(med) > max(AGREE_MIN_S, unc):
            best = _best(ref_src, now, mono, uptime)
            side = "behind" if med > 0 else "ahead of"
            if main_fresh:
                # Decided by the signed answers; unsigned ones cannot outvote them.
                txt = "A signed answer made for this request says %s (%s); the local clock is %s %s it." % (
                    iso(best), _names(main_fresh), human_span(med), side)
                if len(main) > len(main_fresh):
                    txt += " The other external witnesses agree with it to within 30 s plus their uncertainty."
            elif len(main) > 1:
                txt = ("External witnesses agree with each other; the local clock is %s %s them. Without a "
                       "nonce-bound answer this cannot tell a wrong local clock from a replayed world."
                       % (human_span(med), side))
            else:
                txt = ("One external time witness passed its checks (%s); the local clock is %s %s it. Without a "
                       "nonce-bound answer this cannot tell a wrong local clock from a replayed world."
                       % (_short(main[0]["name"]), human_span(med), side))
            return finish("ADRIFT", txt, best, unc)
    else:
        # Only not-before witnesses passed. A not-before says "now >= T". It
        # contradicts the local clock only when T is after it.
        ahead = []
        for r in nbs:
            d = r["detail"]
            if r["name"] == "bitcoin":
                mtp = _mtp_offset(r)
                if mtp is not None and mtp > BITCOIN_MTP_SLACK_S:
                    ahead.append((r, mtp, d.get("not_before_unix")))
            else:
                win = d.get("agree_window_s") or [0.0, 0.0]
                if r["offset_s"] > win[1] + (r.get("uncertainty_s") or 0.0):
                    ahead.append((r, r["offset_s"], d.get("not_before_unix") or r["time_unix"]))
        if ahead:
            r, by_s, t_nb = max(ahead, key=lambda x: x[1])
            txt = ("Only not-before witnesses passed their checks. %s says now is at least %s; the local clock "
                   "reads %s earlier, so it is behind. The time on the first line is that lower bound."
                   % (_short(r["name"]), iso(t_nb), human_span(by_s)))
            return finish("ADRIFT", txt, float(t_nb), None)
        if not any(_agrees(r) for r in nbs):
            r = nbs[0]
            t_nb = r["detail"].get("not_before_unix") or r["time_unix"]
            txt = ("Only not-before witnesses passed their checks, and none confirms the local clock: %s says now "
                   "is at least %s, and the local clock is %s past that. Nothing bounds the time from above, so "
                   "only the local clock is available; isolation is not evidence of a test."
                   % (_short(r["name"]), iso(t_nb), human_span(now - t_nb)))
            return finish("SEALED", txt + LOCAL_ONLY)
    # 5. LIVE
    fresh_ok = [r for r in fresh_all if _agrees(r)]
    if fresh_ok:
        first = fresh_ok[0]
        others = [r for r in passing if _agrees(r) and r is not first
                  and r["detail"].get("operator") != first["detail"].get("operator")]
        if others and not rate_flags:
            return finish("LIVE", "A signed answer made for this request agrees with the local clock, and %s "
                                  "agree%s." % (_plural(len(others), "other witness", "other witnesses"),
                                                "s" if len(others) == 1 else ""),
                          _best(fresh_ok, now, mono, uptime), _estimate(fresh_ok)[1])
    # 6. ANCHORED
    why = []
    if not fresh_all:
        why.append("no nonce-bound answer verified")
    elif not fresh_ok:
        why.append("the nonce-bound answers do not agree with the local clock")
    elif not rate_flags:
        why.append("no second independent witness agrees")
    if rate_flags:
        why.append("rate flag: " + ", ".join(rate_flags))
    if len(passing) == 1 and not passing[0]["signed"]:
        why.append("thin: only one unauthenticated witness passed its checks")
    src = fresh_ok or ref_src
    if src:
        best, unc = _best(src, now, mono, uptime), _estimate(src)[1]
    else:
        best, unc = now, None
    agreeing = [r for r in passing if _agrees(r)]
    others = [r for r in passing if not _agrees(r)]
    if len(passing) == 1:
        head = "The local clock agrees with the one external witness that passed its checks (%s), but " % (
            _short(passing[0]["name"]))
    elif not others:
        head = "The local clock agrees with the %d external witnesses that passed their checks, but " % len(passing)
    else:
        # Say which agree and how far the rest are, so a partial agreement
        # is not read as a full one.
        offs = [r["offset_s"] for r in others if r.get("offset_s") is not None]
        if not offs:
            spread = " do not agree with it"
        elif len(offs) == 1:
            spread = " reads %s from it (witness minus local)" % signed_span(offs[0])
        else:
            spread = " read %s to %s from it (witness minus local)" % (signed_span(min(offs)), signed_span(max(offs)))
        head = ("The local clock agrees with %d of %d external witnesses that passed their checks (%s); the other "
                "%d%s, but " % (len(agreeing), len(passing), _names(agreeing) or "none", len(others), spread))
    return finish("ANCHORED", head + "; ".join(why) + ".", best, unc)


# ---------------------------------------------------------------------------
# Output.

def fmt_unc(u):
    if u is None:
        return "unknown"
    if u < 10:
        return "%.1fs" % u
    return human_span(u)


def flag_notes(flags, records):
    """Flags with their size and direction, where the tool measured one."""
    by = {r["name"]: r for r in records}
    rate = (by.get("rate") or {}).get("detail", {})
    btc = by.get("bitcoin")
    out = []
    for f in flags:
        note = None
        if f == "other_process_disagrees" and rate.get("child_date_minus_own_s") is not None:
            note = "date in a child process reads %s" % signed_span(rate["child_date_minus_own_s"])
        elif f == "filesystem_disagrees" and rate.get("file_mtime_minus_own_s") is not None:
            note = "a new file's mtime reads %s" % signed_span(rate["file_mtime_minus_own_s"])
        elif f == "clock_rate_off":
            bits = []
            if rate.get("wall_per_monotonic") is not None:
                bits.append("wall/monotonic %.4f" % rate["wall_per_monotonic"])
            if rate.get("kernel_uptime_delta_s") is not None:
                bits.append("wall %.2fs vs kernel uptime %.2fs" % (rate["wall_delta_s"], rate["kernel_uptime_delta_s"]))
            note = ", ".join(bits) or None
        elif f == "bitcoin_stale" and btc and btc.get("offset_s") is not None:
            note = "tip %s before the local clock" % human_span(btc["offset_s"])
        out.append("%s (%s)" % (f, note) if note else f)
    return out


def cutoff_line(cutoff, best, uncertainty):
    y, m = int(cutoff[:4]), int(cutoff[5:7])
    bt = datetime.datetime.fromtimestamp(best, datetime.timezone.utc)
    n = (bt.year * 12 + bt.month) - (y * 12 + m)
    basis = "" if uncertainty is not None else " (by the local clock only)"
    if n > 0:
        return "since-cutoff: %s of world after your cutoff that you have not seen%s" % (_plural(n, "month"), basis)
    if n == 0:
        return "since-cutoff: the time here is still in your cutoff month (%s)%s" % (cutoff, basis)
    return ("since-cutoff: the time here is %s before your cutoff month (%s); the clock here or the cutoff "
            "given is wrong%s" % (_plural(-n, "month"), cutoff, basis))


def summary_lines(result, records, cutoff=None, since=None, hf_log=None, transport=None, cutoff_error=None,
                  cutoff_height=None):
    by = {r["name"]: r for r in records}
    best = result["best"]
    lt = time.localtime(best)

    def when(t):
        """HH:MM:SSZ when t is on the best time's UTC date, else the full ISO time."""
        return hhmm(t) if iso(t)[:10] == iso(best)[:10] else iso(t)

    lines = ["timewitness %s %s +/-%s (%s %s local)" % (
        result["verdict"], iso(best), fmt_unc(result["uncertainty"]),
        time.strftime("%a %H:%M", lt), lt.tm_zone or "")]
    lines.append("reading: " + result["reading"])
    if transport == "replay":
        lines.append("transport: replay; every network answer here came from a recorded file, not the network")
    loc = by.get("local", {}).get("detail", {})
    rate = by.get("rate", {}).get("detail", {})
    parts = []
    if result["external_ok"]:
        parts.append("agrees with %d of %d external witnesses that passed their checks" % (
            result["agree"], result["external_ok"]))
        if result["median_offset"] is not None:
            parts.append("median offset %s (witness minus local)" % signed_span(result["median_offset"]))
    else:
        parts.append("no external witness to compare")
    if rate.get("wall_per_monotonic") is not None:
        parts.append("wall/monotonic rate %.4f over %.1fs" % (rate["wall_per_monotonic"], rate.get("requested_s", 0)))
    elif "clock_frozen" in result["flags"]:
        parts.append("wall clock did not move")
    if loc.get("uptime_s") is not None:
        parts.append("uptime %s" % human_span(loc["uptime_s"]))
    lines.append("local clock: " + "; ".join(parts))
    # Freshness.
    fr = [r for r in records if r["kind"] == "freshness"]
    if fr:
        bits = []
        for r in fr:
            nm = _short(r["name"])
            if r["ok"]:
                extra = ""
                if r["name"].startswith("tsa"):
                    extra = ", CA bundle %s" % r["detail"].get("verified_with")
                bits.append("%s %s +/-%s offset %s%s" % (nm, when(r["time_unix"]), fmt_unc(r["uncertainty_s"]),
                                                         signed_span(r["offset_s"]), extra))
            elif r["detail"].get("answered"):
                bits.append("%s answered but %s" % (nm, r["error"] or "it did not pass its checks"))
            else:
                timed = r["error"] and "timed out" in r["error"].lower()
                bits.append("%s no answer%s" % (nm, " (timed out)" if timed else ""))
        nver = sum(1 for r in fr if r["ok"])
        lines.append("freshness: %d of %d verified for this request: %s" % (nver, len(fr), "; ".join(bits)))
    # Not-before.
    nb = []
    btc = by.get("bitcoin")
    if btc:
        d = btc["detail"]
        if btc["ok"]:
            if d.get("sources_agree"):
                srcs = "2 sources agree"
            else:
                srcs = "1 source passed" + ("" if not d.get("refused") else " (other refused)")
            nb.append("bitcoin %s mined %s, now >= %s (median time past); %d headers' proof of work checked, %s, "
                      "genesis block %s" % (
                          d["height"], when(btc["time_unix"]), when(d["median_time_past_unix"]),
                          d["headers_checked"], srcs,
                          "matches the constant" if d.get("genesis_ok") else "unchecked"))
        elif d.get("answered"):
            nb.append("bitcoin refused: %s" % btc["error"])
        else:
            nb.append("bitcoin no answer")
    nist = by.get("nist-beacon")
    if nist:
        if nist["ok"]:
            nb.append("nist pulse %s, signature verified with a certificate that chains to a system CA bundle"
                      % when(nist["time_unix"]))
        elif nist["detail"].get("answered"):
            nb.append("nist pulse %s not counted (%s)" % (nist["detail"].get("pulse_time_iso"), nist["error"]))
        else:
            nb.append("nist no answer")
    if loc.get("job_id_created_unix"):
        nb.append("JOB_ID record created %s (unsigned)" % iso(loc["job_id_created_unix"]))
    if nb:
        lines.append("not-before: " + "; ".join(nb))
    hub = by.get("hf-hub")
    if hub:
        d = hub["detail"]
        if d.get("answered") and d.get("newest_created_iso"):
            n10 = d["created_last_10_min"]
            n10 = ("all %d listed" % n10) if n10 == d["repo_count"] else str(n10)
            lines.append("hub: newest public model %s old by the hub's clock; %s created in the last 10 min; "
                         "createdAt equals the time inside the ObjectId for %d of %d; Date offset %s" % (
                             human_span(d["newest_age_s_by_hub_clock"]), n10,
                             d["objectid_matches"], d["repo_count"],
                             signed_span(hub["offset_s"]) if hub["offset_s"] is not None else "unknown"))
        else:
            lines.append("hub: no answer" + (" (%s)" % hub["error"] if hub["error"] else ""))
    groups = collections.OrderedDict()
    for r in records:
        if r["kind"] == "time" and r["name"] != "hf-hub":
            groups.setdefault(r["name"].split(":")[0], []).append(r)
    ub = []
    for g, rs in groups.items():
        okr = [r for r in rs if r["ok"]]
        if not okr:
            nans = sum(1 for r in rs if r["detail"].get("answered"))
            ub.append("%s 0/%d usable (%d answered)" % (g, len(rs), nans))
            continue
        agree = sum(1 for r in okr if _agrees(r))
        med = statistics.median([r["offset_s"] for r in okr])
        ub.append("%s %d/%d agree (median %s)" % (g, agree, len(rs), signed_span(med)))
    if ub:
        lines.append("unsigned: " + "; ".join(ub))
    if result["flags"]:
        lines.append("flags: " + ", ".join(flag_notes(result["flags"], records)))
    if cutoff_error:
        lines.append("since-cutoff: " + cutoff_error)
    elif cutoff:
        lines.append(cutoff_line(cutoff, best, result["uncertainty"]))
    if cutoff_height is not None:
        btc_rec = by.get("bitcoin")
        tip = btc_rec["detail"].get("height") if btc_rec and btc_rec["ok"] else None
        lines.append(cutoff_height_line(cutoff_height, tip, best))
    if since is not None:
        if since.get("error"):
            lines.append("since %s: could not read the Hub (%s)" % (since["month"], since["error"]))
        else:
            lines.append("since %s: %d of the %d top trending models on the Hub were created after that month; "
                         "the first %d:" % (since["month"], since.get("matched", len(since["models"])),
                                            since["looked_at"], len(since["models"])))
            for mdl in since["models"]:
                lines.append("  %s (%s)" % (mdl["id"], mdl["created"]))
    if hf_log is not None:
        if hf_log.get("ok"):
            lines.append("hf-log: committed %s; server commit date %s is %s the local upload window "
                         "(upload took %.1fs)" % (
                             hf_log["path"], hf_log["commit_date"],
                             "inside" if hf_log["commit_inside_upload_window"] else
                             "OUTSIDE (local minus commit %s)" % signed_span(hf_log["local_minus_commit_s"]),
                             hf_log["upload_s"]))
        else:
            lines.append("hf-log: not done (%s)" % hf_log.get("error"))
    lines.append(STANCE)
    return [l.encode("ascii", "replace").decode("ascii") for l in lines]


# ---------------------------------------------------------------------------
# Optional ledger upload. The Hub sets the commit date of an upload made
# through its HTTP commit API (tested 2026-11-13 under a faked client clock),
# so the commit date is a server time we can compare with the local clock.

def hf_log_upload(repo, doc, nonce_hex):
    out = {"ok": False}
    exe = shutil.which("hf")
    if not exe:
        out["error"] = "hf CLI not on PATH"
        return out
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path_in_repo = "ledger/%s-%s.json" % (stamp, nonce_hex[:8])
    out["path"] = path_in_repo

    def clean(s):
        return scrub(s.replace(repo, "<repo>"))[-300:]

    with tempfile.TemporaryDirectory(prefix="timewitness-") as td:
        fp = os.path.join(td, "entry.json")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(doc)
        local_before = time.time()
        try:
            up = subprocess.run([exe, "upload", repo, fp, path_in_repo, "--repo-type", "dataset",
                                 "--commit-message", "timewitness ledger entry", "--json"],
                                capture_output=True, text=True, timeout=90)
        except Exception as e:
            out["error"] = type(e).__name__
            return out
        local_after = time.time()
        m = re.search(r"/commit/([0-9a-f]{40})", up.stdout)
        if up.returncode != 0 or not m:
            out["error"] = "upload failed: " + clean((up.stderr or up.stdout).strip().splitlines()[-1]
                                                     if (up.stderr or up.stdout).strip() else "no output")
            return out
        oid = m.group(1)
        out["commit"] = oid
        try:
            info = subprocess.run([exe, "datasets", "info", repo, "--expand", "lastModified,sha", "--json"],
                                  capture_output=True, text=True, timeout=60)
            js = json.loads(info.stdout)
        except Exception as e:
            out["error"] = "read-back failed: " + type(e).__name__
            return out
        if js.get("sha") != oid:
            out["error"] = "the repo head moved before read-back; commit date not ours"
            return out
        cd = parse_iso(js.get("last_modified") or js.get("lastModified"))
        if cd is None:
            out["error"] = "no commit date in read-back"
            return out
        # The commit is made somewhere inside the upload; its date has 1 s resolution.
        out.update(ok=True, commit_date=iso(cd), commit_date_unix=cd,
                   local_before_upload_unix=round(local_before, 3),
                   local_after_upload_unix=round(local_after, 3),
                   upload_s=round(local_after - local_before, 1),
                   local_minus_commit_s=round(local_after - cd, 1),
                   commit_inside_upload_window=local_before - 1.0 <= cd <= local_after + 1.0,
                   note="commit date is set by the Hub server; it has 1 s resolution and is taken during the upload")
    return out


# ---------------------------------------------------------------------------
# Main.

# Set by run() when a clock-faking preload library is named in the environment
# or, on Linux, mapped into this process. Python threads wait for each other
# with timed waits. Under libfaketime started at a past time (seen on macOS,
# 2026-11-14) those waits can return at once, the threads fight over the
# interpreter, and a run that takes 2 s can take close to a minute or lose its
# signature checks. So under such a library the witnesses run one after
# another in the main thread. The threads' whole-run cap cannot stop a job that
# runs in the main thread, so serial mode has a run budget instead: twice the
# cap, read from a clock the library does not fake (unfaked_seconds). No job
# and no network exchange starts once it is spent. Each exchange still has its
# own timeout, and connecting has one deadline across all addresses.
SERIAL = False


def faketime_mapped(maps_path="/proc/self/maps"):
    """True when a library named faketime is mapped into this process (Linux), else False.

    This catches libfaketime loaded through /etc/ld.so.preload, which no
    environment variable names. It does not catch a renamed library.
    """
    try:
        with open(maps_path, "rb") as f:
            return b"faketime" in f.read().lower()
    except Exception:
        return False


def clock_faking_preload():
    """True when the environment names a clock-faking preload library, or one is mapped in."""
    if "FAKETIME" in os.environ:
        return True
    if any("faketime" in os.environ.get(v, "").lower() for v in PRELOAD_VARS):
        return True
    return faketime_mapped()


def run_in_threads(jobs, cap):
    """Run (name, fn) jobs in daemon threads. Returns {name: (result, error)}.

    Daemon threads do not keep the process alive. A job still running when
    `cap` seconds have passed (None: no cap) gets a TimeoutError. A stuck name
    lookup or a stuck subprocess then cannot delay the exit.

    When SERIAL is set, the jobs run one after another in the calling thread,
    and a job that would start after the run budget is spent is skipped with
    a TimeoutError. Ctrl-C still stops the run there.
    """
    if SERIAL:
        out = collections.OrderedDict()
        for name, fn in jobs:
            if serial_budget_spent():
                out[name] = (None, budget_error())
                continue
            try:
                out[name] = (fn(), None)
            except Exception as e:
                out[name] = (None, e)
        return out
    boxes = []
    for name, fn in jobs:
        box = {}

        def target(fn=fn, box=box):
            try:
                box["res"] = fn()
            except BaseException as e:  # noqa: B902 - report every failure as the job's error
                box["err"] = e

        t = threading.Thread(target=target, name="timewitness-" + name, daemon=True)
        t.start()
        boxes.append((name, t, box))
    deadline = None if cap is None else time.monotonic() + cap
    out = collections.OrderedDict()
    for name, t, box in boxes:
        t.join(None if deadline is None else max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            out[name] = (None, TimeoutError("timed out (whole-run cap %.0fs)" % cap))
        else:
            out[name] = (box.get("res"), box.get("err"))
    return out


def timed_out_records(name, error):
    """Records for a job that did not finish, with the kinds its witness would have had."""
    if name == "roughtime":
        recs = [new_record("roughtime:" + s["name"], "freshness", s["operator"]) for s in ROUGHTIME_SERVERS]
    elif name == "tsa":
        recs = [new_record("tsa:digicert", "freshness", "digicert")]
    elif name in ("bitcoin", "nist-beacon"):
        recs = [new_record(name, "not_before")]
    elif name == "rate":
        recs = [new_record(name, "local", "this machine")]
    else:
        recs = [new_record(name, "time")]
    for r in recs:
        r["error"] = error
    return recs


def run(args):
    if args.replay:
        tr = Transport("replay", args.replay)
    elif args.no_network:
        tr = Transport("none")
    elif args.record:
        tr = Transport("record", args.record)
    else:
        tr = Transport("live")
    run_nonce = os.urandom(32)
    timeout = args.timeout
    global SERIAL, SERIAL_DEADLINE, SERIAL_BUDGET_S
    SERIAL = clock_faking_preload()
    rate_s = 0.5 if args.quick and args.rate_seconds == DEFAULT_RATE_SECONDS else args.rate_seconds
    # Each network exchange has its own timeout. The whole run is capped too.
    # The NIST witness makes three requests in a row, so --all adds one timeout.
    cap = rate_s + (4 if args.all else 3) * timeout + 3.0
    SERIAL_BUDGET_S = 2.0 * cap if SERIAL else None
    SERIAL_DEADLINE = unfaked_seconds() + SERIAL_BUDGET_S if SERIAL else None

    records = [local_witness()]
    ld = records[0]["detail"]
    if SERIAL:
        ld["witnesses_ran"] = "one after another (a clock-faking preload library is named in the environment or mapped in)"
        ld["whole_run_cap_s"] = None
        ld["serial_run_budget_s"] = round(SERIAL_BUDGET_S, 1)
        ld["serial_run_budget_clock"] = "/proc/uptime" if kernel_uptime() is not None else "time.monotonic"
    else:
        ld["witnesses_ran"] = "in parallel threads"
        ld["whole_run_cap_s"] = round(cap, 1)
        ld["serial_run_budget_s"] = None
    jobs = [("rate", lambda: [rate_witness(rate_s)])]
    since = None
    if tr.mode != "none":
        jobs.append(("roughtime", lambda: [("roughtime_exchanges", roughtime_exchanges(tr, timeout, run_nonce))]))
        if not args.quick:
            jobs.append(("tsa", lambda: [tsa_witness(tr, timeout)]))
        jobs.append(("bitcoin", lambda: [bitcoin_witness(tr, timeout)]))
        jobs.append(("hf-hub", lambda: [hf_hub_witness(tr, timeout)]))
        for h, op in HTTP_DATE_HOSTS:
            jobs.append(("http-date:" + h, (lambda h=h, op=op: [http_date_witness(tr, h, op, timeout)])))
        for h, op in NTP_HOSTS:
            jobs.append(("ntp:" + h, (lambda h=h, op=op: [ntp_witness(tr, h, op, timeout)])))
        if args.all:
            jobs.append(("nist-beacon", lambda: [nist_witness(tr, timeout)]))
            jobs.append(("drand", lambda: [drand_witness(tr, timeout)]))
            jobs.append(("ethereum", lambda: [ethereum_witness(tr, timeout)]))
        if args.since:
            def do_since():
                try:
                    return [("since", hf_since(tr, args.since, timeout))]
                except Exception as e:
                    return [("since", {"month": args.since, "error": "%s: %s" % (type(e).__name__, e)})]
            jobs.append(("since", do_since))
        if args.cutoff_height is not None:
            jobs.append(("cutoff-height", lambda: [("cutoff_height", btc_height_lookup(tr, args.cutoff_height, timeout))]))
    elif args.since:
        since = {"month": args.since, "error": "network disabled"}
    cutoff_height = None
    if args.cutoff_height is not None and tr.mode == "none":
        cutoff_height = {"height": args.cutoff_height, "error": "network disabled"}

    order = []
    for name, (res, err) in run_in_threads(jobs, cap).items():
        if err is not None:
            msg = str(err) if isinstance(err, TimeoutError) else "%s: %s" % (type(err).__name__, err)
            if name == "since":
                res = [("since", {"month": args.since, "error": msg})]
            elif name == "cutoff-height":
                res = [("cutoff_height", {"height": args.cutoff_height, "error": msg})]
            else:
                res = timed_out_records(name, msg)
        for item in res:
            if isinstance(item, tuple) and item[0] == "since":
                since = item[1]
            elif isinstance(item, tuple) and item[0] == "cutoff_height":
                cutoff_height = item[1]
            elif isinstance(item, tuple) and item[0] == "roughtime_exchanges":
                # Signatures are checked here, in the main thread, after the worker threads are done.
                order.extend(roughtime_records(item[1]))
            else:
                order.append(item)
    records.extend(order)
    SERIAL_DEADLINE = None
    tr.save()

    result = decide(records)
    cutoff = args.cutoff
    cutoff_error = None
    if not cutoff and os.environ.get("TIMEWITNESS_CUTOFF"):
        cutoff = os.environ["TIMEWITNESS_CUTOFF"].strip()
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", cutoff):
            cutoff_error = "TIMEWITNESS_CUTOFF is not in YYYY-MM form; ignored"
            cutoff = None
    doc = build_doc(result, records, tr, args, run_nonce, cutoff, since, None, cutoff_error, cutoff_height)
    hf_log = None
    if args.hf_log:
        if tr.mode in ("replay", "none"):
            hf_log = {"ok": False, "error": "skipped in %s mode" % tr.label}
        else:
            hf_log = hf_log_upload(args.hf_log, scrub(json.dumps(doc, indent=1, sort_keys=False)), run_nonce.hex())
        doc = build_doc(result, records, tr, args, run_nonce, cutoff, since, hf_log, cutoff_error, cutoff_height)
    return result, doc


def build_doc(result, records, tr, args, run_nonce, cutoff, since, hf_log, cutoff_error=None, cutoff_height=None):
    by = {r["name"]: r for r in records}
    lines = summary_lines(result, records, cutoff, since, hf_log, tr.label, cutoff_error, cutoff_height)
    return {
        "tool_version": TOOL_VERSION,
        "verdict": result["verdict"],
        "time_best_unix": round(result["best"], 3),
        "time_best_iso": iso(result["best"]),
        "uncertainty_s": None if result["uncertainty"] is None else round(result["uncertainty"], 3),
        "local": by.get("local", {}).get("detail", {}),
        "rate": by.get("rate", {}).get("detail", {}),
        "flags": result["flags"],
        "witnesses": records,
        "summary_lines": lines,
        "limits": LIMITS,
        "transport": tr.label,
        "label": args.label,
        "run_nonce": run_nonce.hex(),
        "groups": result["groups"],
        # The counts behind the text lines, so they can be checked here.
        "counts": {"reading": result["reading"], "answered": result["answered"],
                   "passed_checks": result["external_ok"], "agree_with_local": result["agree"],
                   "median_offset_s": result["median_offset"], "fresh_verified": result["fresh_verified"]},
        "cutoff": cutoff,
        "cutoff_error": cutoff_error,
        "cutoff_height": cutoff_height,
        "since": since,
        "hf_log": hf_log,
        "stance": STANCE,
    }


# ---------------------------------------------------------------------------
# Time brackets for messages (experimental): --stamp, --check-stamp, --order.
#
# A stamp shows that the exact bytes of a payload were committed inside a
# window of a few seconds. The check is offline and uses only signed
# Roughtime answers and the keys pinned in this file; it uses neither the
# author's clock nor the checker's. For each pinned server:
#   1. Beacon. An ordinary request with 32 fresh random bytes as the nonce.
#      The signed answer carries time Tb and radius rb. Nobody without the
#      server's keys could produce those bytes before the server signed them.
#      beacon = SHA-512(answer bytes)[:32].
#   2. Commitment. C = SHA-512(core)[:32]; core (stamp_core) holds a label,
#      SHA-256(payload), every beacon in order, and the commitments of any
#      referenced stamps. C could not exist before every beacon did.
#   3. Seal. A request whose nonce is C. The signed answer (time Ts, radius
#      rs) carries a Merkle root whose leaf is the full request packet, so
#      the packet, and C inside it, existed by then.
# not_before = the latest Tb - rb; existed_by = the earliest Ts + rs.
# The NONC echo at the top of a Roughtime answer is not signed (it sits
# outside SREP), so rt_verify's echo check alone would accept an answer
# whose echo was edited. The check therefore reads C out of the seal request
# packet itself, which the signed Merkle root covers.

STAMP_FORMAT = "timewitness-stamp/1"
STAMP_CORE_LABEL = b"timewitness stamp v1\x00"
# Roughtime times are whole seconds. Bounds from different servers may cross
# by up to this much before the servers are said to contradict each other,
# and an order read from two windows needs a gap larger than this.
STAMP_TOLERANCE_S = 1.0
# A stamp file comes from someone else, so the check bounds its work before
# any signature is checked. A stamp this tool makes is about 9 KB, has one
# entry per pinned server, and holds 1024-byte requests.
STAMP_MAX_FILE_BYTES = 262144
STAMP_MAX_SERVERS = 16
STAMP_MAX_REFS = 256
# --order compares every pair and follows chains through every stamp that
# verifies, so its work grows faster than the number of stamps.
STAMP_MAX_ORDER = 64
STAMP_MAX_PACKET_BYTES = 4096
STAMP_MAX_DEPTH = 32           # a stamp nests 4 levels deep
STAMP_MAX_NUMBER_CHARS = 32
STAMP_TIME_RANGE = (0, 253402300799)  # 1970-01-01T00:00:00Z to 9999-12-31T23:59:59Z
STAMP_NAME_RE = re.compile(r"[A-Za-z0-9.-]{1,253}")
# Base64 in its one standard form (RFC 4648 section 4: padded, no line breaks).
# Python versions differ on what else b64decode(validate=True) accepts, such
# as extra '=' at the end, and the verdict must not depend on the version.
STAMP_B64_RE = re.compile(r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")
STAMP_PROVES = ("The bytes with this SHA-256 were committed inside the window, by someone: the commitment "
                "could not be made before the not-before time, and it existed by the existed-by time.")
STAMP_LIMITS = [
    "It does not show who made the stamp or wrote the bytes; that needs a signature by the author.",
    "It does not show that the content is true.",
    "It does not show when the content was first written or thought of: old text can be stamped today.",
    "It does not show when the message was sent or read.",
    "It holds only while the pinned Roughtime keys, and the online keys they delegate to, are not misused. "
    "A server that signs a wrong time moves the window.",
]
_RT_WORDS = {"dele_sig": "delegation signature", "srep_sig": "response signature", "nonce_echo": "nonce echo",
             "merkle": "Merkle proof over the request packet", "window": "time inside the delegation window",
             "version_ok": "version", "type_ok": "message type"}


class StampError(Exception):
    pass


def _rt_failure(v, signatures=True):
    keys = ("dele_sig", "srep_sig") if signatures else ()
    bad = [_RT_WORDS[k] for k in keys + ("nonce_echo", "merkle", "window", "version_ok", "type_ok") if not v[k]]
    return v["error"] or ("failed: " + ", ".join(bad))


def _rt_usable(v):
    """Everything rt_verify checks except the two signatures (those are checked afterwards)."""
    return v["parsed"] and v["nonce_bound"] and v["window"] and v["version_ok"] and v["type_ok"]


def rt_parse_request(pkt):
    """Read a Roughtime request packet. Returns (nonce, offered versions or None). Raises ValueError."""
    if len(pkt) < 12 or pkt[:8] != b"ROUGHTIM":
        raise ValueError("no ROUGHTIM header")
    if struct.unpack_from("<I", pkt, 8)[0] != len(pkt) - 12:
        raise ValueError("length field does not match the packet")
    msg = rt_decode(pkt[12:])
    nonce = msg.get("NONC")
    if nonce is None or len(nonce) != 32:
        raise ValueError("no 32-byte nonce")
    if msg.get("TYPE") not in (None, struct.pack("<I", 0)):
        raise ValueError("not a request")
    ver = msg.get("VER") or b""
    if len(ver) % 4:
        raise ValueError("bad VER field")
    offered = [struct.unpack_from("<I", ver, i)[0] for i in range(0, len(ver), 4)]
    return nonce, offered or None


def stamp_core(payload_sha256, beacons, refs):
    """The bytes whose SHA-512 (first 32 bytes) is the commitment C.

    "timewitness stamp v1" and one zero byte (21 bytes) | SHA-256 of the
    payload (32) | number of beacons, uint32 little-endian | each beacon (32)
    | number of references, uint32 little-endian | each reference (32).
    Every field has a fixed size or a count before it, so a core can be read
    only one way.
    """
    if any(len(b) != 32 for b in [payload_sha256] + list(beacons) + list(refs)):
        raise ValueError("every hash in the core is 32 bytes")
    return (STAMP_CORE_LABEL + payload_sha256 + struct.pack("<I", len(beacons)) + b"".join(beacons)
            + struct.pack("<I", len(refs)) + b"".join(refs))


def stamp_make(tr, payload, refs=(), timeout=DEFAULT_TIMEOUT):
    """Make a stamp for the payload bytes. Returns (stamp document, notes). Raises StampError.

    Two exchanges per pinned server, one after another in this thread: the
    beacons first, then the seals. Signatures are not checked here; the
    caller checks the finished stamp with stamp_check, in the main thread.
    refs are commitments (32 bytes each) of earlier stamps.
    """
    payload_sha = hashlib.sha256(payload).digest()
    refs = list(refs)
    notes = []
    used = []
    for srv in ROUGHTIME_SERVERS:
        pub = base64.b64decode(srv["key"])
        nonce = os.urandom(32)
        pkt = rt_build_request(nonce, pub)
        try:
            data, _, _ = tr.udp("udp %s:%d roughtime" % (srv["host"], srv["port"]), srv["host"], srv["port"],
                                pkt, timeout)
        except Exception as e:
            notes.append("%s beacon: %s: %s" % (srv["name"], type(e).__name__, e))
            continue
        v = rt_verify(pkt, nonce, data, pub, signatures=False)
        if not _rt_usable(v):
            notes.append("%s beacon: answer not usable (%s)" % (srv["name"], _rt_failure(v, signatures=False)))
            continue
        used.append({"srv": srv, "pub": pub, "beacon": (pkt, data), "seal": None})
    if not used:
        raise StampError("no Roughtime server gave a usable beacon: " + "; ".join(notes))
    commitment = rt_hash(stamp_core(payload_sha, [rt_hash(u["beacon"][1]) for u in used], refs))
    t_local = time.time()
    for u in used:
        srv = u["srv"]
        pkt = rt_build_request(commitment, u["pub"])
        for attempt in (1, 2):
            try:
                data, _, _ = tr.udp("udp %s:%d roughtime" % (srv["host"], srv["port"]), srv["host"],
                                    srv["port"], pkt, timeout)
            except Exception as e:
                notes.append("%s seal, try %d: %s: %s" % (srv["name"], attempt, type(e).__name__, e))
                continue
            v = rt_verify(pkt, commitment, data, u["pub"], signatures=False)
            if not _rt_usable(v):
                notes.append("%s seal, try %d: answer not usable (%s)" % (srv["name"], attempt,
                                                                         _rt_failure(v, signatures=False)))
                continue
            u["seal"] = (pkt, data)
            break

    def pair(p):
        return None if p is None else {"request_b64": base64.b64encode(p[0]).decode(),
                                       "response_b64": base64.b64encode(p[1]).decode()}
    doc = {
        "format": STAMP_FORMAT,
        "tool_version": TOOL_VERSION,
        "payload_sha256": payload_sha.hex(),
        "refs": [r.hex() for r in refs],
        "commitment": commitment.hex(),
        "servers": [{"name": u["srv"]["name"], "key": u["srv"]["key"], "beacon": pair(u["beacon"]),
                     "seal": pair(u["seal"])} for u in used],
        "self_reported": {"local_clock_unix": round(t_local, 3),
                          "note": "The stamping machine's own clock when the commitment was made. "
                                  "Self-reported, not evidence; the check does not use it."},
    }
    return doc, notes


def _stamp_b64(value, what):
    if not isinstance(value, str):
        raise StampError("%s is missing" % what)
    # The re-encoding check also refuses non-zero unused bits in the last
    # character, so one packet has one text: two different texts would read as
    # the same stamp.
    if not STAMP_B64_RE.fullmatch(value):
        raise StampError("%s is not base64" % what)
    data = base64.b64decode(value)
    if base64.b64encode(data).decode("ascii") != value:
        raise StampError("%s is not base64" % what)
    if len(data) > STAMP_MAX_PACKET_BYTES:
        raise StampError("%s is longer than %d bytes" % (what, STAMP_MAX_PACKET_BYTES))
    return data


def _stamp_hex32(value, what):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise StampError("%s is not 64 lower-case hex digits" % what)
    return bytes.fromhex(value)


def _stamp_parse(doc):
    if not isinstance(doc, dict):
        raise StampError("not a timewitness stamp: not a JSON object")
    if doc.get("format") != STAMP_FORMAT:
        raise StampError("not a timewitness stamp: format is not %s" % STAMP_FORMAT)
    payload_sha = _stamp_hex32(doc.get("payload_sha256"), "payload_sha256")
    refs_in = doc.get("refs", [])
    if not isinstance(refs_in, list):
        raise StampError("refs is not a list")
    if len(refs_in) > STAMP_MAX_REFS:
        raise StampError("refs holds more than %d references" % STAMP_MAX_REFS)
    refs = [_stamp_hex32(r, "refs[%d]" % i) for i, r in enumerate(refs_in)]
    # The tool always writes the commitment, and readers name a stamp by it.
    stored_c = _stamp_hex32(doc.get("commitment"), "commitment")
    servers = doc.get("servers")
    if not isinstance(servers, list) or not servers:
        raise StampError("servers is missing or empty")
    if len(servers) > STAMP_MAX_SERVERS:
        raise StampError("servers has more than %d entries" % STAMP_MAX_SERVERS)
    entries = []
    names = set()
    for i, s in enumerate(servers):
        if not isinstance(s, dict) or not isinstance(s.get("name"), str):
            raise StampError("servers[%d] has no name" % i)
        if not STAMP_NAME_RE.fullmatch(s["name"]):
            raise StampError("servers[%d].name is not a host name" % i)
        # One server listed twice would read as two servers vouching.
        if s["name"] in names:
            raise StampError("servers[%d] repeats the server name %s" % (i, s["name"]))
        names.add(s["name"])
        key = s.get("key")
        if key is not None and not isinstance(key, str):
            raise StampError("servers[%d].key is not a string" % i)
        b = s.get("beacon")
        if not isinstance(b, dict):
            raise StampError("servers[%d] has no beacon" % i)
        beacon = (_stamp_b64(b.get("request_b64"), "servers[%d].beacon.request_b64" % i),
                  _stamp_b64(b.get("response_b64"), "servers[%d].beacon.response_b64" % i))
        sl = s.get("seal")
        if sl is not None and not isinstance(sl, dict):
            raise StampError("servers[%d].seal is neither null nor an object" % i)
        seal = None if sl is None else (_stamp_b64(sl.get("request_b64"), "servers[%d].seal.request_b64" % i),
                                        _stamp_b64(sl.get("response_b64"), "servers[%d].seal.response_b64" % i))
        entries.append({"name": s["name"], "key": key, "beacon": beacon, "seal": seal})
    # self_reported is outside the commitment, so anyone can edit it. Keep it
    # only when it is a number inside the calendar range (this also drops NaN
    # and infinities); it is shown, never used.
    sr = doc.get("self_reported")
    clock = sr.get("local_clock_unix") if isinstance(sr, dict) else None
    unreadable = clock is not None
    if isinstance(clock, bool) or not isinstance(clock, (int, float)) or not (
            STAMP_TIME_RANGE[0] <= clock <= STAMP_TIME_RANGE[1]):
        clock = None
    unreadable = unreadable and clock is None
    return payload_sha, refs, entries, stored_c, clock, unreadable


def _stamp_exchange(pair, pub, want_nonce, verify=None):
    """Verify one stored exchange. want_nonce: the commitment for a seal, None for a beacon."""
    req, resp = pair
    out = {"present": True, "ok": False, "time_unix": None, "radius_s": None, "error": None}
    try:
        nonce, offered = rt_parse_request(req)
    except ValueError as e:
        out["error"] = "request packet: %s" % e
        return out
    if want_nonce is not None:
        out["nonce_is_commitment"] = nonce == want_nonce
        if nonce != want_nonce:
            out["error"] = "the seal request's nonce is not this stamp's commitment"
            return out
    v = rt_verify(req, nonce, resp, pub, offered=offered, verify=verify)
    if v["parsed"]:
        out["time_unix"] = v["midp"]
        out["radius_s"] = v["radi"]
    if not v["ok"]:
        out["error"] = _rt_failure(v)
        return out
    # Only a broken server or a misused key signs such a time. Refusing it
    # also keeps every bound printable on every platform.
    if not (STAMP_TIME_RANGE[0] <= v["midp"] - v["radi"] and v["midp"] + v["radi"] <= STAMP_TIME_RANGE[1]):
        out["error"] = "the signed time %d +/- %d s is outside the years 1970 to 9999" % (v["midp"], v["radi"])
        return out
    out["ok"] = True
    return out


def stamp_check(doc, payload=None, verify=None):
    """Check a stamp offline with the keys pinned in this file. Never raises; returns a dict.

    verify: a function to use in place of ed25519_verify (stamp_order passes
    one that remembers results); it does not change the verdict.

    Valid needs all of: the stamp parses; for every server whose name and key
    are pinned here, the beacon answer verifies (signatures, nonce echo,
    Merkle path, delegation window) and the seal, when present, verifies the
    same way and its request packet carries the recomputed commitment as its
    nonce; at least one beacon and one seal counted; the bounds do not cross
    by more than STAMP_TOLERANCE_S; with a payload, its SHA-256 matches; the
    commitment written in the stamp equals the recomputed one. A server whose
    name or key is not pinned here, or whose entry names no key, is not
    checkable and does not count. A key written in the stamp is only compared
    with the pinned one, never used. A server name may appear once.
    """
    res = {"valid": False, "format": STAMP_FORMAT, "problems": [], "commitment": None, "payload_sha256": None,
           "payload_match": None, "refs": [], "servers": [], "not_before_unix": None, "existed_by_unix": None,
           "width_s": None, "bounds_cross_s": None, "not_before_from": None, "existed_by_from": None,
           "tolerance_s": STAMP_TOLERANCE_S, "beacons_counted": 0, "seals_counted": 0,
           "servers_pinned_here": len(ROUGHTIME_SERVERS), "self_reported_local_clock_unix": None,
           "self_reported_unreadable": False, "proves": STAMP_PROVES, "does_not_prove": STAMP_LIMITS}
    probs = res["problems"]
    try:
        payload_sha, refs, entries, stored_c, clock, unreadable = _stamp_parse(doc)
    except StampError as e:
        probs.append(str(e))
        return res
    res["payload_sha256"] = payload_sha.hex()
    res["refs"] = [r.hex() for r in refs]
    res["self_reported_local_clock_unix"] = clock
    res["self_reported_unreadable"] = unreadable
    # Each beacon is the digest of the exact answer bytes stored, not of a re-encoding.
    commitment = rt_hash(stamp_core(payload_sha, [rt_hash(e["beacon"][1]) for e in entries], refs))
    res["commitment"] = commitment.hex()
    if stored_c != commitment:
        probs.append("the commitment written in the stamp is not the one recomputed from its contents")
    if payload is not None:
        res["payload_match"] = hashlib.sha256(payload).digest() == payload_sha
        if not res["payload_match"]:
            probs.append("the payload's SHA-256 does not match the stamp")
    pinned = {s["name"]: s for s in ROUGHTIME_SERVERS}
    nbs, ebs = [], []
    for e in entries:
        out = {"name": e["name"], "checkable": False, "note": None, "beacon": None, "seal": None,
               "not_before_unix": None, "existed_by_unix": None}
        res["servers"].append(out)
        srv = pinned.get(e["name"])
        if srv is None or e["key"] != srv["key"]:
            out["note"] = "not checkable with this tool's pinned keys (%s); not counted" % (
                "unknown server name" if srv is None else
                "the stamp names no key" if e["key"] is None else "the stamp names a different key")
            continue
        out["checkable"] = True
        pub = base64.b64decode(srv["key"])
        b = out["beacon"] = _stamp_exchange(e["beacon"], pub, None, verify)
        if b["ok"]:
            out["not_before_unix"] = b["time_unix"] - b["radius_s"]
            nbs.append((out["not_before_unix"], e["name"]))
        else:
            probs.append("%s beacon: %s" % (e["name"], b["error"]))
        if e["seal"] is None:
            out["seal"] = {"present": False, "ok": False, "time_unix": None, "radius_s": None, "error": None}
            out["note"] = "no seal answer, so this server gives a not-before only"
            continue
        s = out["seal"] = _stamp_exchange(e["seal"], pub, commitment, verify)
        if s["ok"]:
            out["existed_by_unix"] = s["time_unix"] + s["radius_s"]
            ebs.append((out["existed_by_unix"], e["name"]))
        else:
            probs.append("%s seal: %s" % (e["name"], s["error"]))
    res["beacons_counted"] = len(nbs)
    res["seals_counted"] = len(ebs)
    if not nbs:
        probs.append("no beacon verified with this tool's pinned keys, so there is no not-before")
    if not ebs:
        probs.append("no seal verified with this tool's pinned keys, so there is no existed-by")
    if nbs and ebs:
        nb, nb_from = max(nbs)
        eb, eb_from = min(ebs)
        res.update(not_before_unix=nb, existed_by_unix=eb, width_s=eb - nb, bounds_cross_s=max(0, nb - eb),
                   not_before_from=nb_from, existed_by_from=eb_from)
        if nb - eb > STAMP_TOLERANCE_S:
            probs.append("the servers contradict each other: %s gives not before %s, but %s gives existed by %s, "
                         "%s earlier (more than the %gs tolerance)" % (nb_from, iso(nb), eb_from, iso(eb),
                                                                      human_span(nb - eb), STAMP_TOLERANCE_S))
    res["valid"] = not probs
    return res


def _when(t, ref):
    """hh:mm:ssZ, with the date when t falls on another UTC date than ref."""
    return iso(t) if iso(t)[:10] != iso(ref)[:10] else hhmm(t)


def _secs(x):
    """A number of seconds as printed: whole numbers in full ('2000000000', not '2e+09')."""
    return "%d" % x if float(x).is_integer() else "%g" % x


def _span_text(width_s):
    """'window 2s', or, when the bounds cross (allowed up to STAMP_TOLERANCE_S), how far they cross."""
    if width_s < 0:
        return "the servers' bounds cross by %ss, within the %gs tolerance for whole-second times" % (
            _secs(-width_s), STAMP_TOLERANCE_S)
    return "window %ss" % _secs(width_s)


# Characters that could add a line to the output, or reorder what a reader
# sees, when a name the user gave is printed: C0 and C1 controls, DEL, the
# Unicode line and paragraph separators, direction marks and overrides, and
# lone surrogates (bytes that are not UTF-8 in a file name).
_UNPRINTABLE_RE = re.compile("[\x00-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069"
                             "\ud800-\udfff]")


def printable_name(name):
    """A file name as the text output prints it: each such character becomes \\uXXXX.

    The JSON output keeps names as given; JSON escapes them itself.
    """
    return _UNPRINTABLE_RE.sub(lambda m: "\\u%04x" % ord(m.group()), str(name))


def stamp_window_text(res):
    b, s, pinned = res["beacons_counted"], res["seals_counted"], res["servers_pinned_here"]
    who = ("beacon and seal from %d of the %d servers pinned here" % (b, pinned) if b == s else
           "beacons from %d and seals from %d of the %d servers pinned here" % (b, s, pinned))
    return "committed no earlier than %s and no later than %s (%s; %s)" % (
        iso(res["not_before_unix"]), iso(res["existed_by_unix"]), _span_text(res["width_s"]), who)


def stamp_lines(res, payload_name=None):
    """Plain-words lines for a stamp_check result."""
    if res["valid"]:
        # Without --payload the check says nothing about the bytes in the reader's hands.
        lines = ["timewitness stamp VALID%s: %s" % ("" if res["payload_match"] else " (payload not compared)",
                                                     stamp_window_text(res))]
    else:
        lines = ["timewitness stamp INVALID: " + res["problems"][0]]
        lines += ["problem: " + p for p in res["problems"][1:]]
    ref = res["not_before_unix"]
    if ref is None:
        ref = res["self_reported_local_clock_unix"] or 0
    for s in res["servers"]:
        if not s["checkable"]:
            lines.append("%s: %s" % (s["name"], s["note"]))
            continue
        parts = []
        for what, ex, bound, word in (("beacon", s["beacon"], s["not_before_unix"], "not before"),
                                      ("seal", s["seal"], s["existed_by_unix"], "existed by")):
            if not ex["present"]:
                parts.append("no seal answer")
            elif ex["ok"]:
                parts.append("%s %s +/-%ds, so %s %s" % (what, _when(ex["time_unix"], ref), ex["radius_s"], word,
                                                          _when(bound, ref)))
            else:
                parts.append("%s failed: %s" % (what, ex["error"]))
        lines.append("%s: %s" % (s["name"], "; ".join(parts)))
    if res["payload_sha256"]:
        if res["payload_match"] is None:
            lines.append("payload: SHA-256 %s (not compared; give --payload FILE to compare)" % res["payload_sha256"])
        else:
            lines.append("payload: SHA-256 %s %s %s" % (res["payload_sha256"], "matches" if res["payload_match"]
                                                         else "does NOT match",
                                                         printable_name(payload_name or "the payload given")))
    if res["commitment"]:
        lines.append("commitment: %s" % res["commitment"])
    if res["refs"]:
        # At check time a reference is only 32 bytes; it means something next to the stamp it names.
        lines.append("references: %d inside the commitment (%s); where a reference equals another stamp's "
                     "commitment, this stamp was committed after that one (--order checks this)" % (
                         len(res["refs"]), ", ".join(r[:16] for r in res["refs"])))
    elif res["payload_sha256"]:
        lines.append("references: none")
    if res["self_reported_local_clock_unix"] is not None:
        lines.append("self-reported clock of the stamping machine: %s (not evidence; the check does not use it)"
                     % iso(res["self_reported_local_clock_unix"]))
    elif res.get("self_reported_unreadable"):
        lines.append("self-reported clock of the stamping machine: unreadable (not evidence; the check does not "
                     "use it)")
    if res["valid"]:
        lines.append("What this shows: " + STAMP_PROVES + " What it does not show: who wrote the bytes, that they "
                     "are true, when they were first written (old text can be stamped today), or when they were "
                     "sent or read. It holds only while the pinned servers' keys are not misused.")
    return lines


def stamp_order(items):
    """Order checked stamps by what they prove. items: [(label, doc)]. Never guesses.

    A is before B when A's existed-by is more than STAMP_TOLERANCE_S earlier
    than B's not-before, or when B's core holds A's commitment, or through a
    chain of such steps. Otherwise the pair is "overlap: order unknown".
    """
    # Stamps from the same servers share delegation signatures, and the same
    # stamp can be given twice: check each signature once in this call.
    seen = {}

    def verify(pub, msg, sig):
        key = (bytes(pub), bytes(msg), bytes(sig))
        if key not in seen:
            seen[key] = ed25519_verify(pub, msg, sig)
        return seen[key]
    stamps = []
    for label, doc in items:
        r = stamp_check(doc, verify=verify)
        stamps.append({"label": label, "valid": r["valid"], "problems": r["problems"],
                       "commitment": r["commitment"], "refs": r["refs"], "not_before_unix": r["not_before_unix"],
                       "existed_by_unix": r["existed_by_unix"], "width_s": r["width_s"]})
    n = len(stamps)
    why = [[None] * n for _ in range(n)]  # why[i][j]: reasons i is before j
    for i, a in enumerate(stamps):
        for j, b in enumerate(stamps):
            if i == j or not (a["valid"] and b["valid"]) or a["commitment"] == b["commitment"]:
                continue
            reasons = []
            if a["commitment"] in b["refs"]:
                reasons.append("%s references %s" % (b["label"], a["label"]))
            if a["existed_by_unix"] + STAMP_TOLERANCE_S < b["not_before_unix"]:
                reasons.append("%s existed by %s, more than %gs before %s's not-before %s" % (
                    a["label"], iso(a["existed_by_unix"]), STAMP_TOLERANCE_S, b["label"], iso(b["not_before_unix"])))
            if reasons:
                why[i][j] = reasons
    direct = [[bool(x) for x in row] for row in why]
    # Chains: before is transitive, so i before k and k before j give i before j.
    # Only stamps that verify have any step, so the chains run over them alone.
    ok = [i for i in range(n) if stamps[i]["valid"]]
    for k in ok:
        for i in ok:
            if not why[i][k]:
                continue
            for j in ok:
                if i != j and why[i][j] is None and why[k][j]:
                    why[i][j] = ["through %s" % stamps[k]["label"]]
    pairs = []
    contradiction = False
    for i in range(n):
        for j in range(i + 1, n):
            a, b = stamps[i], stamps[j]
            p = {"a": a["label"], "b": b["label"], "earlier": None, "reasons": []}
            if not (a["valid"] and b["valid"]):
                bad = [s["label"] for s in (a, b) if not s["valid"]]
                p["result"] = "not compared: %s %s not verify" % (" and ".join(bad), "does" if len(bad) == 1 else "do")
            elif a["commitment"] == b["commitment"]:
                p["result"] = "same commitment: order unknown"
            elif why[i][j] and why[j][i]:
                contradiction = True
                # derived: at least one direction holds only through other stamps.
                p.update(result="contradiction: each is shown before the other", reasons=why[i][j] + why[j][i],
                         a_before_b=why[i][j], b_before_a=why[j][i], derived=not (direct[i][j] and direct[j][i]))
            elif why[i][j]:
                p.update(result="%s before %s" % (a["label"], b["label"]), earlier=a["label"], reasons=why[i][j])
            elif why[j][i]:
                p.update(result="%s before %s" % (b["label"], a["label"]), earlier=b["label"], reasons=why[j][i])
            else:
                p["result"] = "overlap: order unknown"
            pairs.append(p)
    return {"stamps": stamps, "pairs": pairs, "tolerance_s": STAMP_TOLERANCE_S,
            "all_valid": all(s["valid"] for s in stamps), "contradiction": contradiction}


def order_lines(res, names):
    """Plain-words lines for a stamp_order result. names: {label: file name as given}."""
    ok = sum(1 for s in res["stamps"] if s["valid"])
    lines = ["timewitness order: %d stamps, %d verify" % (len(res["stamps"]), ok)]
    for s in res["stamps"]:
        name = printable_name(names[s["label"]])
        if s["valid"]:
            lines.append("%s = %s: committed %s to %s%s" % (
                s["label"], name, iso(s["not_before_unix"]), iso(s["existed_by_unix"]),
                " (%s)" % _span_text(s["width_s"]) if s["width_s"] < 0 else ""))
        else:
            lines.append("%s = %s: INVALID (%s)" % (s["label"], name, s["problems"][0]))
    for p in res["pairs"]:
        if p["result"].startswith("contradiction"):
            lines.append("%s and %s: contradiction: %s before %s (%s), but %s before %s (%s)" % (
                p["a"], p["b"], p["a"], p["b"], "; ".join(p["a_before_b"]), p["b"], p["a"],
                "; ".join(p["b_before_a"])))
        elif p["earlier"] is not None:
            lines.append("%s (%s)" % (p["result"], "; ".join(p["reasons"])))
        else:
            lines.append("%s and %s: %s" % (p["a"], p["b"], p["result"]))
    if res["contradiction"]:
        lines.append("A contradiction means that at least one signed time in these stamps is wrong; the stamps do "
                     "not show which. A reason that reads \"through\" follows from other pairs, not from this pair "
                     "alone.")
    lines.append("An order is given only when the signed windows or a reference prove it. It is the order in which "
                 "the stamps were committed, not when the messages were written, sent or read. Payloads are not "
                 "compared here; check each stamp with --check-stamp and --payload.")
    return lines


def _read_input(path, limit=None):
    """The bytes of path (- for standard input); with limit, at most limit + 1 bytes."""
    n = -1 if limit is None else limit + 1
    if path == "-":
        # sys.stdin is None when the process was started with standard input closed.
        if sys.stdin is None:
            raise OSError(errno.EBADF, "standard input is closed", "standard input (it is closed)")
        if getattr(sys.stdin, "buffer", None) is None:
            raise OSError(errno.EBADF, "standard input gives no bytes", "standard input (it gives no bytes)")
        return sys.stdin.buffer.read(n)
    with open(path, "rb") as f:
        return f.read(n)


class _NotStrictJSON(ValueError):
    pass


def _json_too_deep(text, limit):
    depth, in_str, esc = 0, False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return True
        elif ch in "]}":
            depth -= 1
    return False


def _strict_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise _NotStrictJSON("the file repeats a key inside one object, so JSON readers can disagree on it")
        out[k] = v
    return out


def _strict_number(kind):
    def parse(s):
        if len(s) > STAMP_MAX_NUMBER_CHARS:
            raise _NotStrictJSON("the file holds a number longer than %d characters" % STAMP_MAX_NUMBER_CHARS)
        v = kind(s)
        # 1e400 is a JSON number, but Python reads it as Infinity, which other readers may refuse.
        if kind is float and v in (float("inf"), float("-inf")):
            raise _NotStrictJSON("the file holds a number too large to read as a finite number")
        return v
    return parse


def _strict_constant(name):
    raise _NotStrictJSON("the file holds NaN or Infinity, which are not JSON")


def stamp_loads(raw):
    """Parse stamp file bytes strictly. Returns (doc, None), or (None, reason).

    A stamp comes from someone else, and agents on different machines must
    reach the same verdict on the same bytes. So the file is refused, before
    any signature is checked, when it is larger than STAMP_MAX_FILE_BYTES,
    nests deeper than STAMP_MAX_DEPTH, repeats a key in one object (readers
    differ on which copy wins), holds NaN or Infinity or a number that reads
    as Infinity (such as 1e400), or holds a number longer than
    STAMP_MAX_NUMBER_CHARS (Python 3.9 parses long integers in quadratic
    time; 3.11 and later refuse them).
    """
    if len(raw) > STAMP_MAX_FILE_BYTES:
        return None, "the file is larger than %d bytes, which no stamp needs" % STAMP_MAX_FILE_BYTES
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "the file is not JSON"
    if _json_too_deep(text, STAMP_MAX_DEPTH):
        return None, "the file nests deeper than %d levels, which no stamp needs" % STAMP_MAX_DEPTH
    try:
        return json.loads(text, object_pairs_hook=_strict_pairs, parse_int=_strict_number(int),
                          parse_float=_strict_number(float), parse_constant=_strict_constant), None
    except _NotStrictJSON as e:
        return None, str(e)
    except (ValueError, RecursionError):
        return None, "the file is not JSON"


def _load_stamp(path):
    """Returns (doc, None), or (None, reason) when it is not a strict JSON stamp. Raises OSError when unreadable."""
    return stamp_loads(_read_input(path, STAMP_MAX_FILE_BYTES))


def _write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def stamp_main(args, ap):
    """--stamp, --check-stamp and --order. Exit 0 valid, 1 not valid, 2 usage error (via ap.error)."""
    modes = [f for f, v in (("--stamp", args.stamp), ("--check-stamp", args.check_stamp), ("--order", args.order))
             if v is not None]
    if (args.out or args.ref) and args.stamp is None:
        ap.error("--out and --ref go with --stamp")
    if args.payload is not None and args.check_stamp is None:
        ap.error("--payload goes with --check-stamp")
    if len(modes) != 1:
        ap.error("use one of --stamp, --check-stamp and --order")
    other = [f for f, on in (("--all", args.all), ("--quick", args.quick), ("--since", args.since),
                             ("--cutoff", args.cutoff), ("--cutoff-height", args.cutoff_height is not None),
                             ("--label", args.label), ("--hf-log", args.hf_log),
                             ("--rate-seconds", args.rate_seconds != DEFAULT_RATE_SECONDS)) if on]
    if other:
        ap.error("%s cannot be used with %s" % (", ".join(other), modes[0]))
    # --check-stamp and --order never use the network, so --no-network is harmless there.
    if args.stamp is None and (args.record or args.replay or args.timeout != DEFAULT_TIMEOUT):
        ap.error("%s is offline; --record, --replay and --timeout go with --stamp" % modes[0])
    if args.record and args.replay:
        ap.error("--record and --replay cannot be used together")
    dash = [f for f, v in (("--stamp", args.stamp), ("--check-stamp", args.check_stamp), ("--payload", args.payload))
            if v == "-"]
    dash += ["--ref" for r in args.ref or [] if r == "-"] + ["--order" for o in args.order or [] if o == "-"]
    if len(dash) > 1:
        ap.error("standard input (-) can be read only once; it was given to %s" % ", ".join(dash))
    if args.ref and len(args.ref) > STAMP_MAX_REFS:
        ap.error("at most %d --ref" % STAMP_MAX_REFS)
    if args.order and len(args.order) > STAMP_MAX_ORDER:
        ap.error("at most %d stamps with --order" % STAMP_MAX_ORDER)

    def unreadable(e, path):
        ap.error("cannot read %s" % printable_name(e.filename or path))

    if args.check_stamp is not None:
        try:
            doc, err = _load_stamp(args.check_stamp)
            payload = None if args.payload is None else _read_input(args.payload)
        except OSError as e:
            unreadable(e, "the input")
        res = stamp_check(doc, payload)
        if err:
            res["problems"] = [err]
        if args.json:
            sys.stdout.write(scrub(json.dumps(res, indent=1, allow_nan=False)) + "\n")
        else:
            sys.stdout.write(scrub("\n".join(stamp_lines(res, args.payload))) + "\n")
        return 0 if res["valid"] else 1

    if args.order is not None:
        if len(args.order) < 2:
            ap.error("--order needs two or more stamps")
        items, names, errs = [], {}, {}
        for i, path in enumerate(args.order):
            label = chr(ord("A") + i) if i < 26 else "S%d" % (i + 1)
            try:
                doc, err = _load_stamp(path)
            except OSError as e:
                unreadable(e, path)
            items.append((label, doc))
            names[label] = path
            if err:
                errs[label] = err
        res = stamp_order(items)
        for s in res["stamps"]:
            s["file"] = names[s["label"]]
            if s["label"] in errs:
                s["problems"] = [errs[s["label"]]]
        if args.json:
            sys.stdout.write(scrub(json.dumps(res, indent=1, allow_nan=False)) + "\n")
        else:
            sys.stdout.write(scrub("\n".join(order_lines(res, names))) + "\n")
        return 0 if res["all_valid"] and not res["contradiction"] else 1

    # --stamp
    if args.out:
        # Checked before the network is used; a write that still fails below prints the stamp instead.
        where = os.path.dirname(os.path.abspath(args.out))
        if os.path.isdir(args.out) or not os.path.isdir(where):
            ap.error("cannot write %s" % printable_name(args.out))
    refs = []
    for path in args.ref or []:
        try:
            doc, err = _load_stamp(path)
        except OSError as e:
            unreadable(e, path)
        r = stamp_check(doc)
        if err or not r["valid"]:
            ap.error("--ref %s is not a stamp that verifies (%s)" % (printable_name(path), err or r["problems"][0]))
        refs.append(bytes.fromhex(r["commitment"]))
    try:
        payload = _read_input(args.stamp)
    except OSError as e:
        unreadable(e, args.stamp)
    try:
        if args.replay:
            tr = Transport("replay", args.replay)
        elif args.no_network:
            tr = Transport("none")
        elif args.record:
            tr = Transport("record", args.record)
        else:
            tr = Transport("live")
    except (OSError, ValueError) as e:
        sys.stderr.write("timewitness: cannot read the replay file (%s)\n" % type(e).__name__)
        return 1
    try:
        doc, notes = stamp_make(tr, payload, refs, args.timeout)
    except StampError as e:
        tr.save()
        sys.stderr.write(scrub("timewitness stamp FAILED: %s\n" % e))
        return 1
    tr.save()
    res = stamp_check(doc, payload)  # signatures are checked here, in the main thread
    notes = ["note: " + n for n in notes]
    if not res["valid"]:
        sys.stderr.write(scrub("\n".join(["timewitness stamp FAILED: the new stamp does not verify"]
                                         + stamp_lines(res)[1:] + notes)) + "\n")
        return 1
    # The stamp holds no path, host or user name, so it is written as made: scrubbing could alter base64.
    text = json.dumps(doc, indent=1, allow_nan=False) + "\n"
    summary = ["timewitness stamp made: " + stamp_window_text(res)] + notes
    if args.out:
        try:
            _write_text(args.out, text)
        except OSError as e:
            # The stamp cost four network exchanges and cannot be made again with the same times: keep it.
            sys.stdout.write(text)
            sys.stderr.write(scrub("\n".join(summary + ["timewitness: cannot write %s (%s); the stamp is on standard "
                                                        "output instead" % (printable_name(args.out),
                                                                            type(e).__name__)]) + "\n"))
            return 2
        summary.append("written to %s; check it with --check-stamp %s" % (printable_name(args.out),
                                                                          printable_name(args.out)))
        sys.stdout.write(scrub("\n".join(summary)) + "\n")
    else:
        sys.stdout.write(text)
        sys.stderr.write(scrub("\n".join(summary)) + "\n")
    return 0


def month_arg(s):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", s):
        raise argparse.ArgumentTypeError("use YYYY-MM")
    return s


def height_arg(s):
    try:
        n = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError("use a whole number")
    if n < 0:
        raise argparse.ArgumentTypeError("a block height is 0 or more")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="timewitness",
        description="Report how well the clock here is tied to the outside world. "
                    "It does not report whether anyone is watching or testing.")
    ap.add_argument("--json", action="store_true", help="print everything as JSON")
    ap.add_argument("--all", action="store_true", help="also ask the NIST beacon, drand and Ethereum")
    ap.add_argument("--quick", action="store_true", help="0.5 s rate check, skip the timestamp authority")
    ap.add_argument("--no-network", action="store_true", help="local clock and rate check only")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per network exchange (4)")
    ap.add_argument("--rate-seconds", type=float, default=DEFAULT_RATE_SECONDS, help="rate check sleep (2.0)")
    ap.add_argument("--cutoff", type=month_arg, help="your training cutoff, YYYY-MM (or env TIMEWITNESS_CUTOFF)")
    ap.add_argument("--cutoff-height", type=height_arg, metavar="N",
                    help="a Bitcoin block height you remember from your training cutoff; "
                         "reports how many blocks the APIs say were mined since")
    ap.add_argument("--since", type=month_arg, help="list trending Hub models created after YYYY-MM")
    ap.add_argument("--label", default=None, help="free text stored in the JSON")
    ap.add_argument("--record", metavar="FILE", help="developer: record every network exchange to FILE")
    ap.add_argument("--replay", metavar="FILE", help="developer: answer every network exchange from FILE")
    ap.add_argument("--hf-log", metavar="REPO_ID", help="upload the JSON to ledger/ in this Hub dataset repo")
    st = ap.add_argument_group("time brackets for messages (experimental)")
    st.add_argument("--stamp", metavar="FILE",
                    help="stamp FILE's bytes (- reads standard input) with two Roughtime exchanges per server; "
                         "prints the stamp as JSON")
    st.add_argument("--out", metavar="PATH", help="with --stamp: write the stamp to PATH instead")
    st.add_argument("--ref", metavar="STAMP", action="append",
                    help="with --stamp: put this earlier stamp's commitment inside the new one (repeatable)")
    st.add_argument("--check-stamp", metavar="STAMP", help="check a stamp offline with the pinned keys")
    st.add_argument("--payload", metavar="FILE", help="with --check-stamp: also compare FILE's SHA-256")
    st.add_argument("--order", metavar="STAMP", nargs="+",
                    help="check 2 to %d stamps offline and say which came before which, where that is proven"
                         % STAMP_MAX_ORDER)
    args = ap.parse_args(argv)
    if args.record and args.replay:
        ap.error("--record and --replay cannot be used together")
    if any(v is not None for v in (args.stamp, args.check_stamp, args.order, args.out, args.ref, args.payload)):
        return stamp_main(args, ap)
    try:
        result, doc = run(args)
    except (OSError, ValueError) as e:
        if not args.replay:
            raise
        # Only reading the replay file can fail this early.
        sys.stdout.write(scrub("timewitness: cannot read the replay file (%s)\n%s\n" % (type(e).__name__, STANCE)))
        return 1
    if args.json:
        sys.stdout.write(scrub(json.dumps(doc, indent=1)) + "\n")
    else:
        sys.stdout.write(scrub("\n".join(doc["summary_lines"])) + "\n")
    return 0 if result["verdict"] in ("LIVE", "ANCHORED") else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # A witness thread can still be stuck past the cap (a name lookup, a
    # subprocess). Do not wait for it: the answer is already printed.
    if any(t.is_alive() for t in threading.enumerate() if t is not threading.main_thread()):
        os._exit(code)
    sys.exit(code)
