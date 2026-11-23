"""Hand-verification worksheet for decision records: each field beside the source text it claims.

    python3 -I scripts/decision_worksheet.py DECISION_ID [...]   > local/worksheet.txt

For each record it prints the extracted fields (restricted ones only as their *shape*, never the
string), then masked source evidence: the opening of the document (caption / headnote / complaint),
the anchored outcome page, the region just before the signature (where a FAIS order sits), and the
first context of every rule cited. Everything shown passes through scripts/redact.py first.
Output belongs in local/ (gitignored) or a scratchpad, never in a committed file.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from redact import mask  # noqa: E402
from extract_decisions import DATED, SECTION, RULE  # noqa: E402


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def main(ids):
    recs = {json.loads(l)["decision_id"]: json.loads(l) for l in open(os.path.join(ROOT, "decisions.jsonl"))}
    rows = {json.loads(l)["row_index"]: json.loads(l)
            for l in open(os.path.join(ROOT, "local", "fais-determination-rows.jsonl"))}
    census = {json.loads(l)["doc_id"]: json.loads(l) for l in open(os.path.join(ROOT, "sources.jsonl"))}
    for did in ids:
        d = recs[did]
        r = census[d["doc_id"]]
        level = "full" if d["office"] == "FAIS" else "light"
        trows = [rows[i] for i in r.get("listing_row_indices") or []]
        extra = [x.get("complainant") for x in trows] + [x.get("respondent") for x in trows]
        text = open(os.path.join(ROOT, "text", "final", d["doc_id"] + ".txt"), encoding="utf-8").read()
        pages = text.split("\f")
        print("=" * 100)
        print(f"{did}  doc {d['doc_id']}  {d['office']}/{d['division']}  {d['text_source']}  "
              f"pages {len(pages)}  title={r.get('title')!r}")
        show = {k: v for k, v in d.items() if k not in ("respondent_raw", "respondent_canonical", "outcome_quote")}
        for k in ("respondent_raw", "respondent_canonical"):
            v = d.get(k)
            show[k] = (mask(v, extra=extra) if d["office"] == "FAIS" else v) if v else None
        show["outcome_quote"] = mask(d["outcome_quote"], extra=extra, level=level) if d.get("outcome_quote") else None
        for k in ("decision_id", "year", "date", "fiscal_year", "product_line", "topic_defence", "topic_conduct",
                  "outcome", "page_anchor", "outcome_quote", "rules_cited", "rules_proposed", "rules_dropped", "respondent_public", "respondent_raw",
                  "respondent_canonical", "respondent_party_type", "citation_policy", "citation_url",
                  "extraction_confidence", "extraction_flags"):
            print(f"  {k:22s} {show.get(k)}")
        if d["office"] == "FAIS":
            print(f"  table: date_raw={[x.get('date_raw') for x in trows]} fy={[x.get('fiscal_year') for x in trows]} "
                  f"category={[x.get('category') for x in trows]}")
        f = flat(text)
        print("\n  --- opening (masked) ---")
        print("  " + mask(f[:2600], extra=extra, level=level))
        if d.get("page_anchor"):
            p = pages[d["page_anchor"] - 1]
            print(f"\n  --- anchored page {d['page_anchor']} (masked) ---")
            print("  " + mask(flat(p)[:2200], extra=extra, level=level))
        ds = [m.start() for m in DATED.finditer(f)]
        end = ds[-1] if ds else len(f)
        print(f"\n  --- before the last signature line (masked; {len(ds)} DATED lines) ---")
        print("  " + mask(f[max(0, end - 1800): end + 200], extra=extra, level=level))
        print("\n  --- rules: first context of each ---")
        for m in list(SECTION.finditer(f))[:40] + list(RULE.finditer(f))[:10]:
            print("   · " + mask(f[max(0, m.start() - 40): m.end() + 30], extra=extra, level=level))
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
