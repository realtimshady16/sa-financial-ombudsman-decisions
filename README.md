# ombudsman-data

An index of every determination published by South Africa's two financial ombuds — the **National
Financial Ombud Scheme** (NFO: the merged OLTI / OBS / OSTI / Credit Ombud) and the **FAIS Ombud** —
as machine-readable records: outcome, topic on two independent axes, statutory provisions verified
verbatim, and a canonical link to the office that published it.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24465702.svg)](https://doi.org/10.5281/zenodo.24465702)

**5 years of it did not exist before in any usable form.** Both offices publish only PDFs on
WordPress, with no CSV, no API and no index; the determinations have never been searchable by subject,
firm or provision. That is what this repo is for.

> **Read [`LIMITS.md`](LIMITS.md) before using any number here.** In particular: 88% of outcomes are
> `upheld` because publication is selective, so this dataset cannot produce a win rate or rank firms.

## At a glance

| | |
|---|---|
| determinations indexed | **545** records, covering all **552** published files (7 are byte-identical duplicates) |
| period | **2005 – 2025** |
| sources | NFO (OLTI 2003–, Credit Ombud 2006–, OBS 2009–, OSTI 2016–, NFO 2024–) and FAIS Ombud (2005–) |
| documents censused | **1 004** files, all hashed; **983** yielded text (4.14M words) |
| provisions | **3 600** citations, each found verbatim in its decision |
| firms named | **345** records name an entity respondent; 195 distinct firms |
| confidence | 313 high · 206 medium · 26 low |
| licence | data **CC BY 4.0** · code **MIT** |

## Quick start

```bash
# every determination about advice suitability, newest first
python3 - <<'EOF'
import json
recs = [json.loads(l) for l in open("decisions.public.jsonl")]
hits = [r for r in recs if r["topic_conduct"] == "advice_suitability"]
for r in sorted(hits, key=lambda r: r["date"] or "", reverse=True)[:5]:
    print(r["date"], r["office"], r["outcome"], r["respondent_public"])
    print("   ", r["citation_locator"])
EOF
```

`decisions.public.csv` carries the same records for spreadsheet use (list fields are pipe-joined).

## What is in a record

| field | meaning |
|---|---|
| `outcome` | `upheld` · `partly_upheld` · `dismissed` · `settled` · `referred` · `amendment` · `no_ruling` |
| `topic_defence` | the insurer-side issue — `claim_not_paid`, `exclusion_clause`, `non_disclosure`, `policy_interpretation`, … |
| `topic_conduct` | the adviser-conduct issue — `advice_suitability`, `unlicensed_provider`, `intermediary_cover_failure`, `misappropriation_fraud`, … |
| `rules_cited` | provisions whose words appear verbatim in the decision (never inferred) |
| `respondent_public` | the firm, when the party is an entity; `null` for natural persons |
| `citation_url` | the ombud's own publication — **follow this for the text** |
| `citation_locator` | plain-language pointer into the office's table, for the records whose direct file URL would carry a complainant's name |
| `text_source` | `native` · `ocr` · `html` · `converted` · `repaired` · `none` |
| `extraction_confidence` | `high` · `medium` · `low` |

The two topic axes are separate on purpose: NFO topics describe the **insurer's defence**, FAIS
topics describe the **adviser's conduct**, and forcing them into one vocabulary made both wrong.

## Files

| path | what |
|---|---|
| `decisions.public.jsonl` / `.csv` | the index — one record per determination, name-free |
| `sources.public.jsonl` | the census: one row per published file, hashed, with extraction diagnostics |
| `text_manifest.jsonl` | how each document's text was produced, and how good it is |
| `datapackage.json` | the Frictionless package: fields, counts, licences — verified by `scripts/package.py` |
| `codebook/` | the vocabularies and the rules behind them, with the corpus evidence for each term |
| `schema/` | the record contracts |
| `report.md` | what was fetched, what was missing, what was damaged, and the spot reads |
| `notes/` | the working record: the OCR quality gate, the outcome hand-check, the validator state |
| `LIMITS.md` | what this cannot tell you |

Not committed, by design: the source PDFs, the extracted text, and the unrestricted records. FAIS
determinations name complainants in their text, so the text stays local and the published package
carries indexes and links only. `sources.jsonl` and `decisions.jsonl` hold the restricted fields.

## How it was built

Census from the offices' own sitemaps (the human-facing archive page omits 39 pages, including every
NFO-era document) → fetch and hash every file → text by native extraction, OCR, HTML extraction or
font-level repair, each recorded per document → one model pass per determination constrained to
corpus-derived vocabularies → mechanical validation. `report.md` is the audit trail; `notes/` carries
the two quality gates that changed the design (the OCR gate failed on digits, so no figure here comes
from a scan; the outcome gate sampled only `upheld` cases, so the non-upheld records were checked by
hand).

Verification: `python3 scripts/check_decisions.py` (16 checks passing, 3 open and documented in
`notes/validation-report.md`), `python3 scripts/package.py`, and `sha256sum -c SHA256SUMS` for the
snapshots.

## Cite

> Tim, *South African financial ombudsman determinations, 2005–2025* (2026). CC BY 4.0.
> https://doi.org/10.5281/zenodo.24465702

See `CITATION.cff`. The determinations themselves remain the offices' documents — cite them too, via
`citation_url`.

## Licence

Data CC BY 4.0 (`LICENSE-DATA.md`); code MIT (`LICENSE`). The underlying determinations are not
covered: they are linked, not reproduced.
