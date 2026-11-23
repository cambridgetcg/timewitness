#!/usr/bin/env bash
# Run timewitness inside one Hugging Face Job in four conditions and keep each JSON report.
#
# Needs the `hf` CLI, logged in, on an account with Jobs credit (cpu-basic costs about
# USD 0.01 an hour; this takes about two minutes). Run from the repo root:
#   bash experiments/environments/run_hf_job.sh
#
# The script is sent to the Job packed in an environment variable, so no repo is created
# and no token is passed into the Job. The raw Job log is kept out of results/ because
# it can name the account the Job ran under.
set -u
cd "$(dirname "$0")/../.."
OUT=experiments/environments/results
mkdir -p "$OUT"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 -I -c '
import base64, gzip, sys
b = base64.b64encode(gzip.compress(open("timewitness.py", "rb").read(), 9)).decode()
open(sys.argv[1], "w").write("TW_B64=" + b + "\n")' "$TMP/job.env"

hf jobs run --flavor cpu-basic --timeout 15m --env-file "$TMP/job.env" --name timewitness-envs python:3.12 bash -c '
set -u
python - <<PY
import os,base64,gzip
open("/tmp/tw.py","wb").write(gzip.decompress(base64.b64decode(os.environ["TW_B64"])))
PY
unset TW_B64
run() { name=$1; shift; echo "@@@BEGIN $name"; "$@" --json --label "$name" --cutoff 2026-06 --cutoff-height 953000; rc=$?; echo; echo "@@@END $name exit=$rc"; }
run hf-job-live python -I /tmp/tw.py
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq faketime >/dev/null 2>&1; echo "@@@faketime $(command -v faketime || echo MISSING)"
run hf-job-clock-set-back-june faketime "2026-06-17 12:00:00" python -I /tmp/tw.py
run hf-job-clock-frozen faketime -f "2026-06-17 12:00:00" python -I /tmp/tw.py
run hf-job-clock-10x faketime -f "+0 x10" python -I /tmp/tw.py
echo "@@@uname $(uname -sr)"; echo "@@@openssl $(openssl version)"
' > "$TMP/job.log" 2>&1
echo "hf exit: $?"
grep -a '^@@@' "$TMP/job.log" | cut -c1-120

python3 -I - "$TMP/job.log" "$OUT" <<'PY'
import json, re, sys
log = open(sys.argv[1], errors="replace").read()
out = sys.argv[2] + "/"
for m in re.finditer(r"@@@BEGIN (\S+)\n(.*?)\n@@@END \1 exit=(\d+)", log, re.S):
    name, body, rc = m.group(1), m.group(2), m.group(3)
    try:
        d = json.loads(body[body.find("{"):])
    except Exception as e:
        print(name, "no JSON:", e)
        continue
    json.dump(d, open(out + name + ".json", "w"), indent=1)
    open(out + name + ".txt", "w").write("\n".join(d["summary_lines"]) + "\n")
    open(out + name + ".stderr", "w").write("exit %s\n" % rc)
    print("%-28s %s" % (name, d["summary_lines"][0][:100]))
PY
