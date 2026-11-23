"""Post-pass that makes a freshly extracted `decisions.jsonl` publishable, and idempotent.

Anything that re-extracts records (a bulk run, a model change, `--force`) regenerates records from the
model's answer, which means every rule applied *after* extraction is lost: hand-verified outcomes,
citation verification, the respondent screen, the citation locator, and the year convention. This
script is that lost layer, in one place, so a re-extraction can be followed by one command instead of
five ad-hoc ones.

Order matters: citations before publication, respondents before the public file, hand decisions last
so they cannot be overwritten by a rule.

  python3 scripts/finalise.py [--check]
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import respondents as R  # noqa: E402

DEC = os.path.join(ROOT, "decisions.jsonl")
HAND = os.path.join(ROOT, "codebook", "hand-decisions.jsonl")
WITHHOLD_PATH = os.path.join(ROOT, "codebook", "respondent-withheld.jsonl")
DOWNGRADE_PATH = os.path.join(ROOT, "codebook", "citations-downgraded.jsonl")

INSTRUMENT = re.compile(
    r"(General\s+Code|Code\s+of\s+Conduct|FAIS\s+Act|OLTI\s+Rules|FAIS\s+Ombud\s+Rules|the\s+Rules|"
    r"PPR|Policyholder\s+Protection\s+Rules|LTIA|STIA|FSR\s+Act|FSOS\s+Act|PFA|NCA|CPA|CISCA|"
    r"Companies\s+Act|Insurance\s+Act|MSA|Prescription\s+Act|Short-term\s+Insurance\s+Act|"
    r"Long-term\s+Insurance\s+Act|Pension\s+Funds\s+Act|National\s+Credit\s+Act)", re.I)

# stricter than the checker's own entity test on purpose: this pass may only *remove* a published
# name, never add one, so a disagreement between the two errs toward withholding.
ENTITY_TAIL = re.compile(
    r"(?:pty|ltd|limited|cc|bk|bpk|inc|npc|soc|corporation|company|insurers?|insurance|assurance|bank|"
    r"underwriters?|holdings|proprietary|brokers?|consultants?|consulting|services|administrators?|"
    r"group|trust|fund|schemes?|association|society|investments?|management|managers|capital|securities)"
    r"\W*(?:\([^)]*\))?\W*$", re.I)


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def bare(entry):
    m = re.match(r"^(.*?)\s+[sr]([0-9].*)$", entry)
    return m.group(2) if m else entry


def number_present(num, text):
    pat = (re.escape(num).replace(r"\ ", r"\s*")
           .replace(r"\(", r"\s*\(\s*").replace(r"\)", r"\s*\)"))
    return list(re.finditer(pat, text))


def instrument_near(text, num):
    """The instrument must be named in the same sentence as the provision, at or before it."""
    for m in number_present(num, text):
        start = max(text.rfind(". ", 0, m.start()), text.rfind("; ", 0, m.start())) + 1
        end = text.find(". ", m.end())
        # the checker requires the instrument at or before the provision, so require exactly that:
        # the part of the sentence up to and including the provision number.
        upto = text[start: m.end()]
        if INSTRUMENT.search(upto):
            return True
    return False


def fiscal_from_date(d):
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}/{str(y + 1)[2:]}" if m >= 4 else f"{y - 1}/{str(y)[2:]}"


def main(argv):
    check_only = "--check" in argv
    recs = load(DEC)
    hand = {}
    if os.path.exists(HAND):
        for row in load(HAND):
            hand[row["decision_id"]] = row
    WITHHOLD = {row["decision_id"] for row in load(WITHHOLD_PATH)} if os.path.exists(WITHHOLD_PATH) else set()
    # provisions the independent validator rejects: kept, but demoted to the loose field
    DOWNGRADE = {}
    if os.path.exists(DOWNGRADE_PATH):
        for row in load(DOWNGRADE_PATH):
            DOWNGRADE.setdefault(row["decision_id"], set()).add(row["entry"])

    texts = {}

    def text_of(doc):
        if doc not in texts:
            try:
                texts[doc] = re.sub(r"\s+", " ", open(os.path.join(ROOT, "text", "final", doc + ".txt"),
                                                      encoding="utf-8", errors="replace").read())
            except OSError:
                texts[doc] = ""
        return texts[doc]

    stats = dict(year=0, rules_loose=0, rules_dropped=0, respondents_withheld=0,
                 hand_applied=0, locator=0)

    for r in recs:
        t = text_of(r["doc_id"])

        # 1. year: the year the decision was signed, and a fiscal year that follows from it
        d = r.get("date")
        if d and len(d) >= 7:
            y = int(d[:4])
            if r.get("year") != y:
                stats["year"] += 1
            r["year"] = y
            r["fiscal_year"] = fiscal_from_date(d)
            if r.get("text_source") in ("native", "repaired", "converted"):
                r.setdefault("field_sources", {})["year"] = "native_signed_date"

        # 2. citations: strict where the instrument is named near the provision, loose where only the
        #    number is present, dropped where neither is
        strict, loose = [], []
        demote = DOWNGRADE.get(r["decision_id"], set())
        for c in (r.get("rules_cited") or []) + (r.get("rules_cited_loose") or []):
            num = bare(c)
            if c in demote:
                loose.append(c)
            elif number_present(num, t):
                (strict if instrument_near(t, num) else loose).append(c)
            else:
                stats["rules_dropped"] += 1
        stats["rules_loose"] += len(loose)
        r["rules_cited"] = strict
        if loose:
            r["rules_cited_loose"] = loose
        else:
            r.pop("rules_cited_loose", None)

        # 3. respondent: the project screen, then a stricter tail test that may only withhold
        raw = r.get("respondent_raw")
        if not raw:
            r["respondent_public"] = None
        elif r["office"] == "FAIS":
            pub, kind = R.public_name(raw, t)
            r["respondent_public"], r["respondent_party_type"] = pub, kind
        else:
            name = R.canonical_name(raw)
            r["respondent_public"], r["respondent_party_type"] = name, "juristic"
        # a short, explicit list rather than a rule of my own: these are the parties the validator
        # cannot confirm as one entity, each with its reason in the codebook.
        if r["decision_id"] in WITHHOLD:
            r["respondent_public"] = None
            r["extraction_flags"] = sorted(set(list(r.get("extraction_flags") or [])
                                               + ["respondent_public_withheld_unconfirmed"]))
            stats["respondents_withheld"] += 1

        # 4. the pointer that makes a list-page citation usable (D1's hash tier)
        topic = r.get("topic_defence") or r.get("topic_conduct") or "unclassified"
        r["citation_locator"] = (
            f"FAIS Ombud determinations table, {r.get('year')} — {topic} — identify the row by the "
            f"respondent published in this record" if r["office"] == "FAIS"
            else f"NFO documents archive — Final Determination {r['decision_id'].replace('nfo-fd-', '')} ({r.get('year')})")
        stats["locator"] += 1

        # 5. hand decisions last: a person read the ruling, so a rule may not overwrite it
        h = hand.get(r["decision_id"])
        if h:
            for k, v in h.get("set", {}).items():
                r[k] = v
            r["extraction_flags"] = sorted(set(list(r.get("extraction_flags") or []) + ["hand_verified"]))
            r.setdefault("field_sources", {})["outcome"] = "hand"
            stats["hand_applied"] += 1

    if check_only:
        print("check only — nothing written")
        return 0

    with open(DEC, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    import extract_decisions as E
    n = E.publish()
    print(f"finalised {len(recs)} records; published {n}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
