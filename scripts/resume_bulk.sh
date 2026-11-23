#!/usr/bin/env bash
# Wait out a provider usage window, then run the decisions bulk extraction unattended.
#
# Why not just cron the start time: the window reset is a wall-clock guess, and a run that starts
# two minutes early would abort (correctly) and sit done. This probes with one real document every
# ten minutes and only starts the bulk once a probe actually succeeds. A probe that hits the limit
# writes nothing — the extractor aborts before the record is written, by design.
#
#   scripts/resume_bulk.sh [MAX_ATTEMPTS] [SLEEP_SECONDS] [MODEL]
#
# Exit 0 only if the bulk run itself exits 0.
set -uo pipefail

MAX_ATTEMPTS=${1:-18}
SLEEP_S=${2:-600}
MODEL=${3:-claude-sonnet-5-5}

cd "$(dirname "$0")/.." || exit 1

ts() { date '+%Y-%m-%d %H:%M:%S'; }

probe() {
  python3 - "$1" <<'PY'
import json, sys
q = [json.loads(l)["doc_id"] for l in open("codebook/queue-decisions.jsonl")]
done = {json.loads(l)["doc_id"] for l in open("decisions.jsonl")}
rem = [d for d in q if d not in done]
print(rem[0] if rem else "")
PY
}

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  doc=$(probe x)
  if [ -z "$doc" ]; then
    echo "$(ts) nothing left to extract — done"
    exit 0
  fi
  echo "$(ts) attempt $attempt/$MAX_ATTEMPTS: probing with $doc on $MODEL"
  # A probe that succeeds writes a record; one that hits the limit writes nothing and exits non-zero.
  if python3 -u -I scripts/extract_decisions.py --model "$MODEL" "$doc" 2>&1 | sed "s/^/$(ts)   /"; then
    if python3 - "$doc" <<'PY'
import json, sys
doc = sys.argv[1]
ids = {json.loads(l)["doc_id"] for l in open("decisions.jsonl")}
raise SystemExit(0 if doc in ids else 1)
PY
    then
      echo "$(ts) window is open — starting the bulk run"
      python3 -u -I scripts/extract_decisions.py --model "$MODEL" \
        --queue codebook/queue-decisions.jsonl 2>&1 | sed "s/^/$(ts)   /"
      rc=${PIPESTATUS[0]}
      echo "$(ts) bulk run exited $rc"
      exit "$rc"
    fi
  fi
  echo "$(ts) still limited; sleeping ${SLEEP_S}s"
  sleep "$SLEEP_S"
done

echo "$(ts) gave up after $MAX_ATTEMPTS attempts — the window never opened"
exit 1
