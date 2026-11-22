#!/usr/bin/env bash
# Stage 1 literal verification (the plan's checks). `--live` also re-counts the NFO sitemaps
# (2 polite requests). Run from the repo root.
set -u
UA='ombudsman-data-research/0.1 (+contact: tim@hellotim.co.za)'
echo "\$ wc -l sources.jsonl            -> $(wc -l < sources.jsonl)"
echo "\$ ls pdf/ | wc -l                -> $(ls pdf/ | wc -l)"
echo "\$ ls html/ | wc -l               -> $(ls html/ | wc -l)   (HTML-only documents; pdf/ + html/ = $(( $(ls pdf/ | wc -l) + $(ls html/ | wc -l) )))"
echo "\$ sha256sum -c SHA256SUMS        -> $(sha256sum -c SHA256SUMS 2>&1 | awk '{print $NF}' | sort | uniq -c | xargs)"
python3 -c "import json;[json.loads(l) for l in open('sources.jsonl')]" && echo "\$ python -c json.loads(sources.jsonl) -> parses"
if [ "${1:-}" = "--live" ]; then
  d=$(curl -s -A "$UA" https://nfosa.co.za/docs-sitemap.xml | grep -c '<loc>'); sleep 1.2
  p=$(curl -s -A "$UA" https://nfosa.co.za/wpdmpro-sitemap.xml | grep -c '<loc>')
  echo "\$ curl docs-sitemap.xml | grep -c '<loc>'    -> $d"
  echo "\$ curl wpdmpro-sitemap.xml | grep -c '<loc>' -> $p"
fi
python3 -I scripts/check.py
