#!/usr/bin/env bash
# Run timewitness in eight conditions on a Mac and keep each JSON report.
#
# Needs: Homebrew python3, /opt/homebrew/bin/faketime (brew install libfaketime),
# /usr/bin/sandbox-exec. Run from the repo root:  bash experiments/environments/run_mac.sh
#
# The recording used by the two replay runs holds other people's public repo
# names and raw server answers, so it is written to a temp folder and deleted.
set -u
cd "$(dirname "$0")/../.."
OUT=experiments/environments/results
mkdir -p "$OUT"
PY=/opt/homebrew/bin/python3
FT=/opt/homebrew/bin/faketime
TW="$PY -I timewitness.py --json --cutoff 2026-06 --cutoff-height 953000"
NONET='(version 1)(allow default)(deny network*)'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

run() {  # name, then the command
  local name=$1; shift
  "$@" --label "$name" > "$OUT/$name.json" 2> "$OUT/$name.stderr"
  echo "exit $?" >> "$OUT/$name.stderr"
  $PY -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print("\n".join(d["summary_lines"]))' \
    "$OUT/$name.json" > "$OUT/$name.txt" 2>/dev/null || echo "(no JSON produced)" > "$OUT/$name.txt"
  printf '%-34s %s\n' "$name" "$(head -1 "$OUT/$name.txt" | cut -c1-110)"
}

# 1. The machine as it is.
run mac-live $TW
# 2. Same machine, network denied by the OS sandbox (real isolation, not the tool's own flag).
run mac-no-network /usr/bin/sandbox-exec -p "$NONET" $TW
# 3. Clock set back to a date in the past (the model's cutoff month), network open. The wrapper turns
#    the date into an offset, so the clock ticks on from 12:00 local time.
run mac-clock-set-back-june $FT '2026-06-17 12:00:00' $TW
# 4. Clock frozen at that date: -f with no "@" hands libfaketime an absolute time, which does not move.
run mac-clock-frozen $FT -f '2026-06-17 12:00:00' $TW
# 5. Clock running ten times too fast, starting from now.
run mac-clock-10x $FT -f '+0 x10' $TW
# 6. Sealed and faked: no network, clock frozen as in 4.
run mac-sealed-and-frozen /usr/bin/sandbox-exec -p "$NONET" $FT -f '2026-06-17 12:00:00' $TW
# 7. Replay: record every network answer now, wait, then answer a new run from the recording.
$PY -I timewitness.py --json --record "$TMP/rec.json" > "$TMP/recorded-run.json" 2>/dev/null
REC_AT=$($PY -I -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["recorded_at_unix"]))' "$TMP/rec.json")
sleep 90
run mac-replay-90s-later $TW --replay "$TMP/rec.json"
# 8. Replay with the local clock set back to the moment of the recording.
# (-f hands the "@..." start time straight to libfaketime; the clock then ticks from there.)
run mac-replay-clock-set-back $FT -f "@$(/bin/date -r "$REC_AT" '+%Y-%m-%d %H:%M:%S')" $TW --replay "$TMP/rec.json"
