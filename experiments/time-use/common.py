"""Small helpers shared by run_router.py, run_claude.py and score.py.

Privacy: every stored row goes through scrub(), which removes the home path, any
email address, the user name and the host name (names only as whole words; a
host name under 5 characters only in its exact case, because an earlier
version of this function, matching inside words, broke ordinary words). Extra
literal strings (such as the scratch folder the Claude Code arm runs in) can be
added with add_scrub().
"""

import datetime as dt
import getpass
import json
import os
import re
import socket
import threading

UTC = dt.timezone.utc
UA = "pilot-client/0.1"  # generic User-Agent; no name, email or path
_SCRUB = []
_lock = threading.Lock()


def init_scrub():
    if _SCRUB:
        return
    home = os.path.expanduser("~")
    _SCRUB.append((re.compile(re.escape(home)), "~"))
    _SCRUB.append((re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"))
    try:
        user = getpass.getuser()
        if user and len(user) >= 3:
            _SCRUB.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(user) + r"(?![A-Za-z0-9])", re.I), "[user]"))
    except Exception:
        pass
    for h in sorted({socket.gethostname(), socket.gethostname().split(".")[0]}, key=len, reverse=True):
        if not h or len(h) < 3:
            continue
        flags = re.I if len(h) >= 5 else 0
        _SCRUB.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(h) + r"(?![A-Za-z0-9])", flags), "[host]"))


def add_scrub(literal, repl):
    """Replace a literal string (checked first, before the general rules)."""
    if literal:
        _SCRUB.insert(0, (re.compile(re.escape(literal)), repl))
        real = os.path.realpath(literal)
        if real != literal:
            _SCRUB.insert(0, (re.compile(re.escape(real)), repl))


def scrub(obj):
    if isinstance(obj, str):
        for rx, repl in _SCRUB:
            obj = rx.sub(repl, obj)
        return obj
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {scrub(k): scrub(v) for k, v in obj.items()}
    return obj


def utcnow():
    return dt.datetime.now(UTC)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def load_rows(path):
    rows, bad = [], 0
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    bad += 1
    return rows, bad


def append_row(path, row):
    row = scrub(row)
    with _lock:
        with open(path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
