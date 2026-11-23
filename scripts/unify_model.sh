#!/usr/bin/env bash
# Bring the decisions corpus onto one labeller once the main bulk run has finished.
#
# Why: part of the corpus was labelled while Claude's 5-hour window was closed (Gemini 4 Argon), so
# records carry different `extraction_model` values. Mixing is auditable but not uniform, and the
# point of redoing it is that a consumer should not have to care which model ran when.
#
# Order matters:
#   1. wait for the bulk unit to stop, so two writers never touch decisions.jsonl at once
#   2. a full pass over the queue to retry anything previously deferred (skips are cheap)
#   3. --force re-extraction of every record not labelled by the target model
#
# A document whose re-run fails keeps its existing record: the extractor writes only on success.
#
#   scripts/unify_model.sh <unit-to-wait-for> [MODEL]
set -uo pipefail

UNIT=${1:-}
MODEL=${2:-claude-sonnet-5-5}
MAX_WAIT_S=${MAX_WAIT_S:-10800}   # 3 h
cd "$(dirname "$0")/.." || exit 1

ts() { date '+%Y-%m-%d %H:%M:%S'; }

if [ -n "$UNIT" ]; then
  waited=0
  while systemctl --user is-active --quiet "$UNIT"; do
    if [ "$waited" -ge "$MAX_WAIT_S" ]; then
      echo "$(ts) waited ${MAX_WAIT_S}s for $UNIT and it is still running — not starting"
      exit 1
    fi
    sleep 60
    waited=$((waited + 60))
  done
  echo "$(ts) $UNIT is no longer active after ${waited}s"
fi

echo "$(ts) pass 1: retry anything still missing, on $MODEL"
python3 -u -I scripts/extract_decisions.py --model "$MODEL" --queue codebook/queue-decisions.jsonl 2>&1 \
  | sed "s/^/$(ts)   /"

echo "$(ts) pass 2: re-label records not extracted by $MODEL"
ids=$(python3 - "$MODEL" <<'PY'
import json, sys
model = sys.argv[1]
docs = [json.loads(l)["doc_id"] for l in open("decisions.jsonl")
        if json.loads(l).get("extraction_model") != model]
print(" ".join(docs))
PY
)
if [ -z "${ids// /}" ]; then
  echo "$(ts) nothing to re-label — every record is already $MODEL"
else
  count=$(echo "$ids" | wc -w)
  echo "$(ts) re-labelling $count record(s)"
  python3 -u -I scripts/extract_decisions.py --force --model "$MODEL" $ids 2>&1 | sed "s/^/$(ts)   /"
fi

echo "$(ts) done; models now:"
python3 - <<'PY'
import collections, json
rows = [json.loads(l) for l in open("decisions.jsonl")]
for k, v in collections.Counter(r.get("extraction_model") for r in rows).most_common():
    print(f"  {k}: {v}")
print(f"  total {len(rows)}")
PY
