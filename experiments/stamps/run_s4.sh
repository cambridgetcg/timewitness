#!/usr/bin/env bash
# S4: two machines. Two agents (true clock; clock set back to 2026-06-17 12:00) run inside one
# Hugging Face Job (Linux, cpu-basic) while two (7 min behind; 2 h ahead) run on this Mac. Both
# drivers follow one plan keyed to the same true start time T0, chosen here before the Job is sent.
# The Job's messages and stamps come back through its log and are checked here, offline.
#
# Needs: the `hf` CLI, logged in, with Jobs credit (cpu-basic is USD 0.01 an hour; this takes about
# ten minutes, most of it waiting for T0); Homebrew python3 and libfaketime on the Mac.
# Run from the repo root (takes about 11 minutes):
#   bash experiments/stamps/run_s4.sh
#
# As in experiments/environments/run_hf_job.sh, the code is sent packed in an environment variable,
# so no repo is created and no token is passed into the Job. The raw Job log stays in a temp folder:
# it can name the account the Job ran under. Only the marked lines are kept.
set -u
cd "$(dirname "$0")/../.."
PY=/opt/homebrew/bin/python3
LEAD=${LEAD:-300}
OUT=experiments/stamps/data
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
T0=$($PY -I -c "import time; print(int(time.time()) + $LEAD)")
$PY -I - "$TMP/job.env" "$T0" <<'PY'
import base64, io, sys, tarfile
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as t:
    for p in ("timewitness.py", "experiments/stamps/agent.py", "experiments/stamps/driver.py"):
        t.add(p, arcname=p)
open(sys.argv[1], "w").write("TW_TGZ=" + base64.b64encode(buf.getvalue()).decode() + "\nT0=" + sys.argv[2] + "\n")
PY
hf jobs run --detach --flavor cpu-basic --timeout 25m --env-file "$TMP/job.env" --name timewitness-stamps python:3.12 bash -c '
set -u
mkdir -p /tmp/tw && cd /tmp/tw
python -c "import os,base64,io,tarfile; tarfile.open(fileobj=io.BytesIO(base64.b64decode(os.environ[\"TW_TGZ\"]))).extractall(\".\")"
unset TW_TGZ
echo "@@@unpacked $(date -u +%s)"
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq faketime >/dev/null 2>&1
echo "@@@faketime $(command -v faketime || echo MISSING)"
echo "@@@uname $(uname -sr)"
python -I experiments/stamps/driver.py s4-job --t0 "$T0" --out /tmp/out --python python --faketime "$(command -v faketime)" 2>&1 | sed "s/^/@@@driver /"
python - <<PY
import base64, gzip, hashlib, os
for n in sorted(os.listdir("/tmp/out")):
    b = open("/tmp/out/" + n, "rb").read()
    z = base64.b64encode(gzip.compress(b, 9)).decode()
    parts = [z[i:i + 1000] for i in range(0, len(z), 1000)]
    print("@@@FILE %s %s %d" % (n, hashlib.sha256(b).hexdigest(), len(parts)))
    for i, p in enumerate(parts):
        print("@@@CHUNK %s %d %s" % (n, i, p))
print("@@@DONE")
PY
' > "$TMP/submit.txt" 2>&1
RC=$?
# A failed submission prints an error that can hold hex request ids, so the id is read only on success.
if [ $RC -ne 0 ]; then
  echo "Job not submitted (hf exit $RC): $(/usr/bin/grep -m1 -iE 'error|insufficient' "$TMP/submit.txt" | sed -E 's/\(Request ID[^)]*\)//; s#https?://[^ ]*#<url>#g')"
  /usr/bin/grep -m1 -i 'insufficient' "$TMP/submit.txt"
  $PY -I - "$TMP/submit.txt" "$RC" >> "$OUT/s4-attempts.jsonl" <<'PY'
import json, re, sys, time
t = open(sys.argv[1], errors="replace").read()
first = next((l for l in t.splitlines() if re.search(r"error", l, re.I)), "")
first = re.sub(r"\(Request ID[^)]*\)", "", re.sub(r"'?https?://[^' ]+'?", "<url>", first)).strip()
why = next((l.strip() for l in t.splitlines() if "insufficient" in l.lower()), None)
print(json.dumps({"at_unix": round(time.time()), "hf_exit": int(sys.argv[2]), "error": first, "detail": why,
                  "job_created": False}, sort_keys=True))
PY
  exit 1
fi
JOB=$(/usr/bin/grep -oE '[0-9a-f]{24}' "$TMP/submit.txt" | tail -1)
[ -n "$JOB" ] || { echo "no Job id in the submit output"; exit 1; }
echo "job submitted; T0=$T0 ($(date -u -r "$T0" +%H:%M:%SZ))"
echo "$JOB" > "$TMP/job.id"

# The Mac half, on the same plan.
$PY -I experiments/stamps/driver.py s4-mac --t0 "$T0"
echo "mac half exit: $?"

hf jobs wait "$JOB" >/dev/null 2>&1 || true
hf jobs logs "$JOB" > "$TMP/job.log" 2>&1
hf jobs inspect --json "$JOB" > "$TMP/job.json" 2>/dev/null
mkdir -p "$OUT/s4-job"
$PY -I - "$TMP/job.log" "$TMP/job.json" "$OUT/s4-job" <<'PY'
import base64, gzip, hashlib, json, os, re, sys
log = open(sys.argv[1], errors="replace").read().splitlines()
out = sys.argv[3]
for f in os.listdir(out):
    os.remove(os.path.join(out, f))
files, chunks, notes = {}, {}, []
for line in log:
    m = re.match(r"^@@@FILE (\S+) ([0-9a-f]{64}) (\d+)$", line)
    if m:
        files[m.group(1)] = (m.group(2), int(m.group(3)))
        continue
    m = re.match(r"^@@@CHUNK (\S+) (\d+) (\S+)$", line)
    if m:
        chunks.setdefault(m.group(1), {})[int(m.group(2))] = m.group(3)
        continue
    if line.startswith("@@@") :
        notes.append(line[:200])
bad = 0
for name, (sha, n) in files.items():
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        bad += 1
        continue
    parts = chunks.get(name, {})
    try:
        b = gzip.decompress(base64.b64decode("".join(parts[i] for i in range(n))))
    except Exception:
        bad += 1
        continue
    if hashlib.sha256(b).hexdigest() != sha:
        bad += 1
        continue
    open(os.path.join(out, name), "wb").write(b)
# Job timing, for the cost. Only times are kept, not the account.
try:
    j = json.load(open(sys.argv[2]))
    j = j[0] if isinstance(j, list) else j
    keep = {k: v for k, v in j.items() if k in ("created_at", "started_at", "finished_at", "flavor", "durations")}
    st = j.get("status") or {}
    keep["status"] = {k: v for k, v in st.items() if k in ("stage",)} if isinstance(st, dict) else None
except Exception as e:
    keep = {"error": type(e).__name__}
json.dump({"log_markers": [x for x in notes if not x.startswith("@@@driver ")] , "driver_lines": [x for x in notes if x.startswith("@@@driver ")],
           "files": len(files), "files_bad": bad, "job": keep}, open(os.path.join(out, "job_log_summary.json"), "w"), indent=1)
print("job files: %d, bad: %d" % (len(files), bad))
for x in notes:
    print(x)
PY
# The price per hour of the flavor, as the CLI lists it, for the cost line in the README.
hf jobs hardware 2>/dev/null | awk -F'\t' '$1=="cpu-basic" {print "{\"flavor\": \"cpu-basic\", \"cost_per_hour\": \"" $NF "\", \"cost_per_min\": \"" $(NF-1) "\"}"}' > "$OUT/s4-job/price.json"
cat "$OUT/s4-job/price.json"
