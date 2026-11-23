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
 10. every rules_cited entry is found in the document text, by a check written here (no code shared
     with the extractor): the instrument is named in the text, and the provision's number occurs
     right after a section/rule/clause keyword with each sub-part following it
 11. respondent_public: null for every natural/unknown party; where set, it is an entity-looking
     name that occurs in the FAIS table's respondent string (or, for NFO, in the text); the public
     file never carries respondent_raw or respondent_canonical
 12. topic axes: values from their own vocabularies; both null exactly when there is no ruling

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


def squash(x):
    return re.sub(r"\s+", " ", x.lower().replace("&", "and")).strip(" ,.;")


# respondent names that are published on purpose (entities): not restricted strings. Everything
# else in the respondent column, and every complainant string, still is.
published = {squash(d["respondent_public"]) for d in public if d.get("respondent_public")}
published |= {squash(p) for d in public for p in (d.get("respondent_public") or "").split(" | ") if p}
n_exempt = 0
for r in rows.values():
    for k in ("complainant", "respondent"):
        v = (r.get(k) or "").strip()
        if len(v) >= 6:
            # a respondent string is exempt when it is, or is contained in, a name published as
            # respondent_public: another table row may spell the same entity without "(Pty) Ltd"
            if k == "respondent" and any(squash(v) in p for p in published):
                n_exempt += 1
                continue
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
            if k != "respondent_public":     # an entity's own name may hold a first name; it comes from the respondent column, not the complainants
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
    elif r.get("year") and y != r["year"] and src != "fais_table":
        # for OCR documents the FAIS table date is the only readable date, so it wins over the title
        bad_y.append((d["decision_id"], "census"))
    if d.get("date") and int(d["date"][:4]) != y:
        bad_y.append((d["decision_id"], "date"))
    fy, ld = d.get("fiscal_year"), d.get("listed_date")
    anchor = d.get("date") if d.get("field_sources", {}).get("year") == "native_signed_date" else ld
    if fy and anchor:
        a = int(fy[:4])
        if not (f"{a}-04-01" <= anchor <= f"{a + 1}-03-31"):
            bad_y.append((d["decision_id"], "fiscal_year vs signed/listing date"))
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
IDRE = re.compile(r"(?<![0-9A-Za-z=/_-])\d{6}\s?\d{4}\s?\d{2}\s?\d(?![0-9A-Za-z])")   # not inside a hex hash
for t in sorted(set(tracked + untracked)):
    p = os.path.join(ROOT, t)
    if not os.path.isfile(p):
        continue
    with open(p, encoding="utf-8", errors="replace") as f:
        hay = f.read().lower()
    n = sum(1 for s in needles if s in hay)
    if n:
        tree_hits[t] = n      # file and count only, never the string
    if t.endswith(".md") or t.endswith(".json") or t.endswith(".jsonl") or t.endswith(".py"):
        for m in IDRE.finditer(hay):          # SA identity numbers: 13 digits, possibly spaced
            if re.fullmatch(r"\d{13}", re.sub(r"\s", "", m.group(0))):
                tree_hits[t + " [id-number-shaped]"] = tree_hits.get(t + " [id-number-shaped]", 0) + 1
check("committed tree carries no restricted string and no ID-number-shaped digit run", not tree_hits,
      f"{len(needles)} strings ({n_exempt} respondent strings exempt as published entities) x "
      f"{len(set(tracked + untracked))} files; hits {tree_hits}")

# ---- 10. rules_cited verified against the text, independently
ALIAS = {
    "General Code": r"general code|\bthe code\b|\bcode\b", "FAIS Act": r"fais act|intermediary services act|\bthe act\b",
    "FSOS Act": r"fsos act|ombud schemes act", "FSR Act": r"fsr act|fsra\b|financial sector regulation",
    "LTIA": r"ltia\b|long[- ]term insurance act", "STIA": r"stia\b|short[- ]term insurance act",
    "PPR": r"\bppr\b|policyholder protection", "FAIS Ombud Rules": r"rules on proceedings|\brules\b",
    "OLTI Rules": r"\brules\b|\bolti\b|\bour rules?\b", "Prescription Act": r"prescription act", "CPA": r"consumer protection act|\bcpa\b",
    "NCA": r"national credit act|\bnca\b", "PFA": r"pension funds act", "CISCA": r"collective investment|cisca",
    "Companies Act": r"companies act", "Insurance Act": r"insurance act", "MSA": r"medical schemes act|\bmsa\b"}
KEY = r"(?:sections?|sec\.|ss?\.?|clauses?|rules?|regulations?|paragraphs?|para\.?)"
PAR = re.compile(r"\(\s*([0-9a-z]{1,4})\s*\)")


def unverified(rec):
    p = os.path.join(ROOT, "text", "final", rec["doc_id"] + ".txt")
    if not rec.get("rules_cited"):
        return []
    t = PAR.sub(r"(\1)", re.sub(r"\s+", " ", open(p, encoding="utf-8", errors="replace").read().lower()))
    bad = []
    for c in rec["rules_cited"]:
        m = re.match(r"^(.+?) ([sr])(\d{1,3}[a-z]?(?:\.\d{1,3}[a-z]?)*)((?:\([0-9a-z]{1,4}\))*)$", c, re.I)
        if not m or m.group(1) not in ALIAS:
            bad.append(c)
            continue
        lab, base, subs = m.group(1), m.group(3).lower(), re.findall(r"\([0-9a-z]{1,4}\)", m.group(4).lower())
        ok_c = False
        for hit in re.finditer(r"(?<![\d.])" + re.escape(base) + r"(?!\d|\.\d)", t):
            before = t[max(0, hit.start() - 90): hit.start()]
            after = t[hit.end(): hit.end() + 60]
            if re.search(KEY + r"[^.;]{0,70}$", before, re.I) and all(x in after for x in subs) \
                    and re.search(ALIAS[lab], t[: hit.end() + 120]):
                ok_c = True
                break
        if not ok_c:
            bad.append(c)
    return bad


bad_rules = {}
n_rules = 0
for d in local:
    if d["text_source"] != "none":
        n_rules += len(d["rules_cited"])
        u = unverified(d)
        if u:
            bad_rules[d["decision_id"]] = u
check("every rules_cited entry is found in the document text (zero unverified)", not bad_rules,
      f"{n_rules} entries over {len(local)} records; unverified {bad_rules}")
bad_cnt = [d["decision_id"] for d in local if d.get("rules_dropped") is not None
           and (d["rules_dropped"] > d["rules_proposed"] or d["rules_proposed"] < 0)]
check("rules_dropped <= rules_proposed", not bad_cnt, f"{bad_cnt}")

# ---- 11. respondent_public
ENTITY_END = re.compile(r"(?:pty|ltd|limited|cc|bk|bpk|inc|npc|soc|corporation|company|insurers?|insurance|assurance|"
                        r"bank|underwriters?|holdings|proprietary|brokers?|consultants?|consulting|services|"
                        r"administrators?|group|trust|fund|scheme|association|society|investments?|management|"
                        r"managers|capital|securities)\W*(?:\([^)]*\))?\W*$", re.I)
bad_pub = []
for d in local:
    rid = d["decision_id"]
    if d.get("respondent_public"):
        if d.get("respondent_party_type") in ("natural", "unknown"):
            bad_pub.append((rid, "set for a natural/unknown party"))
        for part in d["respondent_public"].split(" | "):
            if d["office"] == "FAIS" and not ENTITY_END.search(part.strip()):
                bad_pub.append((rid, "does not look like an entity"))
            if d["office"] == "FAIS":
                raw = squash(" | ".join(dict.fromkeys(rows[i]["respondent"].strip()
                      for i in by_id[d["doc_id"]].get("listing_row_indices") or [] if rows[i].get("respondent"))))
                if squash(part) not in raw.replace("(pty) ltd", "(pty) ltd"):
                    # the canonical form re-cases and re-spaces; compare on letters and digits only
                    if re.sub(r"\W", "", squash(part)) not in re.sub(r"\W", "", raw):
                        bad_pub.append((rid, "not in the table's respondent"))
            else:
                txt = re.sub(r"\s+", " ", open(os.path.join(ROOT, "text", "final", d["doc_id"] + ".txt"),
                             encoding="utf-8", errors="replace").read().lower())
                if squash(part) not in txt:
                    bad_pub.append((rid, "NFO insurer not in the text"))
    elif d.get("respondent_party_type") == "juristic" and \
            "respondent_public_withheld_unconfirmed" not in (d.get("extraction_flags") or []):
        # withholding a party is allowed only when it is on the documented list (codebook/
        # respondent-withheld.jsonl) and the record says so.
        bad_pub.append((rid, "juristic but nothing published"))
# a published name with a conjunction inside ("X and Y CC") may be a person plus an entity: it is
# acceptable only when the business words before the last conjunction make it plainly one entity, or
# the document itself calls the whole name a company. Written here, sharing nothing with respondents.py.
BIZ = re.compile(r"\b(?:insurance|assurance|life|bank|holdings|brokers?|services|group|trust|fund|capital|investments?|"
                 r"consult\w*|management|administrators?|underwriters?|company|corporation|securities)\b", re.I)
for d in local:
    for part in (d.get("respondent_public") or "").split(" | "):
        body = re.sub(r"\s*\((?:pty|edms)\)\s*(?:ltd|bpk)?\s*$|\s+(?:ltd|limited|cc|bpk|bk|inc|npc)\.?\s*$", "", part.strip(), flags=re.I)
        seps = list(re.finditer(r"\s+(?:and|&|en)\s+|,\s*", body, re.I))
        if not part or not seps or BIZ.search(body[:seps[-1].start()]):
            continue
        txt = re.sub(r"\s*&\s*", " and ", re.sub(r"\s+", " ", open(os.path.join(ROOT, "text", "final", d["doc_id"] + ".txt"),
                     encoding="utf-8", errors="replace").read()))
        if not re.search(re.escape(re.sub(r"\s+", " ", body)) + r"[^.]{0,90}?(?:a company|a private company|a close corporation|duly incorporated|registration (?:no|number)|incorporated in terms of)", txt, re.I):
            bad_pub.append((d["decision_id"], "published name holds a conjunction the document does not confirm as one company"))
for d in public:
    if d.get("respondent_raw") or d.get("respondent_canonical"):
        bad_pub.append((d["decision_id"], "public file carries a restricted respondent field"))
check("respondent_public: entities only, null for natural/unknown, never raw in the public file", not bad_pub, f"{bad_pub}")

# ---- 12. topic axes
DEF = {"claim_not_paid", "non_disclosure", "exclusion_clause", "late_notification", "policy_interpretation",
       "disability_assessment", "lapse_and_cancellation", "service_and_compensation", "beneficiary_and_cession", "other"}
CON = {"advice_suitability", "misappropriation_fraud", "unlicensed_provider", "mandate_breach", "fees_and_charges",
       "intermediary_cover_failure", "sale_disclosure", "other"}
bad_t = []
for d in local:
    if d["topic_defence"] is not None and d["topic_defence"] not in DEF:
        bad_t.append((d["decision_id"], "defence term"))
    if d["topic_conduct"] is not None and d["topic_conduct"] not in CON:
        bad_t.append((d["decision_id"], "conduct term"))
    if d["outcome"] in ("amendment", "no_ruling", None) and (d["topic_defence"] or d["topic_conduct"]):
        bad_t.append((d["decision_id"], "topic on a document with no ruling"))
check("topic_defence / topic_conduct come from their own vocabularies; none on a non-ruling", not bad_t, f"{bad_t}")

# ---- counts
print()
print("records:", len(local), dict(Counter(d["office"] for d in local)))
both = Counter((d["office"], d["topic_defence"] is not None, d["topic_conduct"] is not None) for d in local)
print("axes filled (office, defence, conduct): " + ", ".join(f"{k} {v}" for k, v in sorted(both.items())))
pub_n = Counter((d["office"], bool(d.get("respondent_public")), d.get("respondent_party_type")) for d in local)
print("respondent_public set (office, published, party_type): " + ", ".join(f"{k} {v}" for k, v in sorted(pub_n.items(), key=str)))
rp = Counter(d["office"] for d in local if d.get("rules_proposed"))
print("rules: model proposed", sum(d.get("rules_proposed") or 0 for d in local), "dropped", sum(d.get("rules_dropped") or 0 for d in local),
      "kept entries", sum(len(d["rules_cited"]) for d in local))
for k in ("topic_defence", "topic_conduct", "outcome", "extraction_confidence", "text_source"):
    c = Counter((d["office"], d[k]) for d in local)
    print(f"{k}:")
    for off in ("NFO", "FAIS"):
        row = sorted(((v, n) for (o, v), n in c.items() if o == off), key=lambda x: (-x[1], str(x[0])))
        print(f"  {off}: " + ", ".join(f"{v} {n}" for v, n in row))
sys.exit(0 if ok else 1)
