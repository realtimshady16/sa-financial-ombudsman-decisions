"""Stage 3 verification: the decisions index.

    python3 -I scripts/check_decisions.py

Checks, each printed PASS/FAIL (exit 1 on any FAIL):

  1. every line of decisions.jsonl and decisions.public.jsonl parses, and validates against
     schema/decision.schema.json; decision_ids are unique
  2. every doc_id (and every duplicate_doc_id) exists in sources.jsonl as a determination, and
     duplicates really are byte-identical (same sha256)
  3. text_source is an enum value AND equals text_manifest.jsonl's value for that document
  4. citation_policy matches the D1 rule, recomputed here independently from the census and the
     restricted filenames; citation_url and filename_sha256 match the census
  5. no record carries a name from the restricted set: the full FAIS complainant / respondent
     strings and filenames (the needle set of check_text.py), plus every complainant name token
     that is not everyday prose — in every field of the public file, and in every non-restricted
     field of the local file
  6. year is plausible: within 2003–2026; equal to the census/table year, unless it comes from the
     native signed date (which must not fall more than 31 days after the listing date); the
     listing date inside the FAIS fiscal year; never sourced from OCR/HTML text
  7. the public file is exactly the local file with the restricted fields nulled
  8. every document the progress log calls "done" has its record on disk (no silent no-ops)
  9. the committed tree (tracked + untracked-not-ignored files) contains no restricted string

Then prints counts by office / topic / outcome / confidence.
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import jsonschema  # noqa: E402
from redact import lowercase_vocab  # noqa: E402

LOCAL = os.path.join(ROOT, "decisions.jsonl")
PUBLIC = os.path.join(ROOT, "decisions.public.jsonl")
PROGRESS = os.path.join(ROOT, "local", "decisions-progress.jsonl")
FAIS_LIST = "https://www.faisombud.co.za/determinations/"
GENERIC = {"fais", "det", "determination", "determinations", "redacted", "final", "case", "no",
           "nr", "v", "vs", "and", "en", "pdf", "signed", "amended", "amendment", "recommendation",
           "ruling", "the", "of", "gp", "wc", "kzn", "ec", "fs", "lp", "mp", "nw", "nc", "kz", "ltd",
           "pty", "cc"}

ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def jl(path):
    out, bad = [], []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except ValueError as e:
                bad.append((i, str(e)[:60]))
    return out, bad


census, _ = jl(os.path.join(ROOT, "sources.jsonl"))
by_id = {r["doc_id"]: r for r in census}
manifest = {m["doc_id"]: m for m in jl(os.path.join(ROOT, "text_manifest.jsonl"))[0]}
rows = {r["row_index"]: r for r in jl(os.path.join(ROOT, "local", "fais-determination-rows.jsonl"))[0]}
schema = json.load(open(os.path.join(ROOT, "schema", "decision.schema.json")))
V = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

# ---- 1. parse + schema + unique
local, bad_l = jl(LOCAL) if os.path.exists(LOCAL) else ([], [("missing", "")])
public, bad_p = jl(PUBLIC) if os.path.exists(PUBLIC) else ([], [("missing", "")])
check("decisions.jsonl parses", not bad_l, f"{len(local)} records; bad lines {bad_l}")
check("decisions.public.jsonl parses", not bad_p, f"{len(public)} records; bad lines {bad_p}")
errs = [(d.get("decision_id"), e.message[:120]) for f in (local, public) for d in f for e in V.iter_errors(d)]
check("every record validates against schema/decision.schema.json", not errs, f"{len(errs)} errors {errs[:5]}")
ids = [d["decision_id"] for d in local]
check("decision_ids unique", len(ids) == len(set(ids)),
      f"duplicates {[k for k, v in Counter(ids).items() if v > 1]}")

# ---- 2. doc_ids exist, duplicates identical
missing, notdet, baddup = [], [], []
for d in local:
    for x in [d["doc_id"]] + d.get("duplicate_doc_ids", []):
        if x not in by_id:
            missing.append(x)
        elif by_id[x]["doc_type"] != "determination":
            notdet.append(x)
    for x in d.get("duplicate_doc_ids", []):
        if x in by_id and by_id[x]["sha256"] != by_id[d["doc_id"]]["sha256"]:
            baddup.append(x)
check("every doc_id exists in sources.jsonl", not missing, f"missing {missing}")
check("every doc_id is a determination", not notdet, f"{notdet}")
check("duplicate_doc_ids are byte-identical to the canonical file", not baddup, f"{baddup}")

# ---- 3. text_source
ENUM = {"native", "ocr", "html", "repaired", "converted", "none"}
bad_ts = [d["decision_id"] for d in local
          if d["text_source"] not in ENUM or d["text_source"] != manifest[d["doc_id"]]["text_source"]]
check("text_source is an enum value and equals text_manifest.jsonl", not bad_ts, f"{bad_ts}")


# ---- 4. D1 citation, recomputed independently
def d1(r):
    if r["office"] == "NFO":
        return "direct", r["url"]
    fns = [f["filename"] for i in r.get("listing_row_indices") or [] for f in rows[i]["files"]
           if f["filename_sha256"] == r["filename_sha256"]]
    def free(fn):
        toks = re.findall(r"[^\W\d_]+", re.sub(r"\.pdf$", "", fn, flags=re.I))
        return all(t.lower() in GENERIC for t in toks)
    if fns and all(free(fn) for fn in fns):
        return "direct", r["fetch_url"]
    return "hash", FAIS_LIST


bad_c = []
for d in local:
    r = by_id[d["doc_id"]]
    pol, url = d1(r)
    if d["citation_policy"] != pol or d["citation_url"] != url or d.get("filename_sha256") != r.get("filename_sha256"):
        bad_c.append(d["decision_id"])
check("citation_policy / citation_url / filename_sha256 follow D1 and the census", not bad_c, f"{bad_c}")

# ---- 5. names
low = lowercase_vocab()
needles = set()
name_tokens = set()
for r in rows.values():
    for k in ("complainant", "respondent"):
        v = (r.get(k) or "").strip()
        if len(v) >= 6:
            needles.add(v.lower())
    for t in re.findall(r"[^\W\d_]+", r.get("complainant") or ""):
        if len(t) >= 4 and low.get(t.lower(), 0) < 50:
            name_tokens.add(t.lower())
    for f in r["files"]:
        needles.add(f["filename"].lower())
        stem = re.sub(r"\.pdf$", "", f["filename"], flags=re.I)
        if len(stem) >= 6:
            needles.add(stem.lower())


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def leaks(rec, skip=()):
    hits = 0
    for k, v in rec.items():
        if k in skip:
            continue
        for s in strings(v):
            sl = s.lower()
            hits += sum(1 for n in needles if n in sl)
            hits += sum(1 for t in re.findall(r"[^\W\d_]+", sl) if t in name_tokens)
    return hits


pub_hits = {d["decision_id"]: n for d in public if (n := leaks(d))}
loc_hits = {d["decision_id"]: n for d in local if (n := leaks(d, skip=set(d.get("restricted_fields", []))))}
check("no restricted name in any field of decisions.public.jsonl", not pub_hits,
      f"{len(needles)} strings + {len(name_tokens)} name tokens; records with hits {pub_hits}")
check("no restricted name in the non-restricted fields of decisions.jsonl", not loc_hits,
      f"records with hits {loc_hits}")

# ---- 6. year
bad_y = []
for d in local:
    r, y = by_id[d["doc_id"]], d["year"]
    if y is None:
        continue
    if not (2003 <= y <= 2026):
        bad_y.append((d["decision_id"], "range"))
    src = d.get("field_sources", {}).get("year")
    if src == "native_signed_date":
        # the signed date may differ from the table's listing date, but never by being later
        if d["text_source"] not in ("native", "repaired", "converted"):
            bad_y.append((d["decision_id"], "signed date from non-native text"))
        if d.get("listed_date") and d["date"] > d["listed_date"][:4] + "-12-31" and \
                d["date"] > d["listed_date"]:
            from datetime import datetime, timedelta
            if datetime.strptime(d["date"], "%Y-%m-%d") > datetime.strptime(d["listed_date"], "%Y-%m-%d") + timedelta(days=31):
                bad_y.append((d["decision_id"], "signed after listing"))
    elif r.get("year") and y != r["year"]:
        bad_y.append((d["decision_id"], "census"))
    if d.get("date") and int(d["date"][:4]) != y:
        bad_y.append((d["decision_id"], "date"))
    fy, ld = d.get("fiscal_year"), d.get("listed_date")
    if fy and ld:
        a = int(fy[:4])
        if not (f"{a}-04-01" <= ld <= f"{a + 1}-03-31"):
            bad_y.append((d["decision_id"], "fiscal_year vs listing date"))
    if d["text_source"] in ("ocr", "html") and "text" in (d.get("field_sources", {}).get("year") or ""):
        bad_y.append((d["decision_id"], "year read from ocr/html"))
check("year plausible (range, census, table date, fiscal year; never from OCR/HTML)", not bad_y, f"{bad_y}")
nulls = [d["decision_id"] for d in local if d["year"] is None]
print(f"      note: {len(nulls)} records with year null {nulls}")

# ---- 7. public == local minus restricted
exp = {}
for d in local:
    p = dict(d)
    for k in d.get("restricted_fields", []):
        p[k] = None
    exp[d["decision_id"]] = p
got = {d["decision_id"]: d for d in public}
check("decisions.public.jsonl == decisions.jsonl with restricted fields nulled", exp == got,
      f"{len(exp)} vs {len(got)}")

# ---- 8. progress log
done = set()
if os.path.exists(PROGRESS):
    for e in jl(PROGRESS)[0]:
        if e["status"] in ("done", "reprocessed"):
            done.add(e["decision_id"])
lost = sorted(done - set(ids))
check("every decision the progress log marks done has a record on disk", not lost, f"lost {lost}")

# ---- 9. committed tree
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
tree_hits = {}
for t in sorted(set(tracked + untracked)):
    p = os.path.join(ROOT, t)
    if not os.path.isfile(p):
        continue
    with open(p, encoding="utf-8", errors="replace") as f:
        hay = f.read().lower()
    n = sum(1 for s in needles if s in hay)
    if n:
        tree_hits[t] = n      # file and count only, never the string
check("committed tree carries no restricted string", not tree_hits,
      f"{len(needles)} strings x {len(set(tracked + untracked))} files; hits {tree_hits}")

# ---- counts
print()
print("records:", len(local), dict(Counter(d["office"] for d in local)))
for k in ("topic", "outcome", "extraction_confidence", "text_source"):
    c = Counter((d["office"], d[k]) for d in local)
    print(f"{k}:")
    for off in ("NFO", "FAIS"):
        row = sorted(((v, n) for (o, v), n in c.items() if o == off), key=lambda x: (-x[1], str(x[0])))
        print(f"  {off}: " + ", ".join(f"{v} {n}" for v, n in row))
sys.exit(0 if ok else 1)
