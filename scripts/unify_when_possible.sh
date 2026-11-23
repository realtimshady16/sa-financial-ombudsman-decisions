#!/usr/bin/env bash
# Run the unify pass the moment the Claude window allows it, instead of guessing the reset time.
#
# A usage limit is a guess until you try: the CLI reports a reset that has already moved twice today.
# So this probes with a real one-token call and only then starts unify_model.sh, which does the
# re-labelling. Probes cost nothing when they fail.
#
#   scripts/unify_when_possible.sh [MAX_ATTEMPTS] [SLEEP_SECONDS] [MODEL]
set -uo pipefail

MAX_ATTEMPTS=${1:-16}
SLEEP_S=${2:-900}
MODEL=${3:-claude-sonnet-5-5}
cd "$(dirname "$0")/.." || exit 1

ts() { date '+%Y-%m-%d %H:%M:%S'; }

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  out=$(claude -p --output-format json 'reply with the single word: ok' 2>&1)
  if printf '%s' "$out" | grep -q '"is_error":false'; then
    echo "$(ts) attempt $attempt/$MAX_ATTEMPTS: window is open"
    bash scripts/unify_model.sh "" "$MODEL"
    rc=$?
    echo "$(ts) unify finished with exit $rc"
    # a re-extraction regenerates records from model answers, so the post-pass must run after it:
    # citation drops, the respondent screen, the hand decisions and the locator all live there.
    echo "$(ts) finalising (citation verification, respondents, hand decisions, locator)"
    python3 scripts/finalise.py 2>&1 | sed "s/^/$(ts)   /"
    python3 scripts/package.py 2>&1 | tail -2 | sed "s/^/$(ts)   /"
    echo "$(ts) done — review and commit"
    exit "$rc"
  fi
  why=$(printf '%s' "$out" | python3 -c 'import json,sys
try: print(str(json.load(sys.stdin).get("result"))[:90])
except Exception: print("probe failed")' 2>/dev/null)
  echo "$(ts) attempt $attempt/$MAX_ATTEMPTS: still limited ($why); sleeping ${SLEEP_S}s"
  sleep "$SLEEP_S"
done

echo "$(ts) gave up after $MAX_ATTEMPTS probes — the window never opened"
exit 1
