# ombudsman-data

A provenance-cited census of what South Africa's financial ombuds publish: the **NFO**
(`nfosa.co.za`, the merged OLTI / OBS / OSTI / Credit Ombud) and the **FAIS Ombud**
(`faisombud.co.za`). This is Stage 1 of the plan in
`~/thinking/plans/2026-11-22-financial-ombudsman-data.md`. Stage 1 builds the schema stub and the
census and snapshots every file once. Stage 2 turns the snapshots into text (`text/final/`,
described by the committed `text_manifest.jsonl`), with OCR held back at its quality gate (see
`report.md` §S2). There is no decisions index yet, no figures and no presentation. **Nothing is
published.** The repo has no remote.

## Layout

| path | committed? | what |
|---|---|---|
| `schema/SCHEMA.md`, `schema/document.schema.json` | yes | the v0 contract: document, decision, office, participant, figure |
| `sources.public.jsonl` | yes | the census: one row per file, restricted fields nulled |
| `SHA256SUMS` | yes | `sha256sum -c SHA256SUMS` re-verifies every snapshot |
| `report.md` | yes | counts, reconciliation against the sitemaps, extraction health, failures, spot reads |
| `text_manifest.jsonl` | yes | Stage 2: one row per document, giving how its text was made (`native`/`ocr`/`repaired`/`converted`/`none`), word count, quality, and repair map. No names |
| `notes/` | yes | hand-written inputs to the report: spot reads, the OCR gate sample, the residual text defects |
| `scripts/` | yes | Stage 1: `census.py` → `harvest.py` → `build.py` → `check.py`. Stage 2: `ocr.py`, `repair.py`, `text_final.py` → `check_text.py` |
| `sources.jsonl` | **no** | the same census with FAIS restricted fields (party names, real file URLs) |
| `pdf/`, `html/` | **no** | the snapshots, named `<doc_id>.<ext>` |
| `text/raw/` | **no** | `pdftotext -layout` output, unrepaired, never overwritten |
| `text/final/` | **no** | the text to use downstream (FAIS bodies name people, so it stays local) |
| `text/ocr/`, `text/repair/`, `text/converted/` | **no** | OCR pages and confidences, font-patched PDF copies and repair maps, LibreOffice output |
| `local/` | **no** | cached listing pages, `.md` twins, fetch log, the restricted FAIS table rows |

Why so much is local-only:

- **The snapshots are other people's documents.** The NFO's terms claim copyright in all site
  content. The design is to index and cite them, never to mirror them.
- **FAIS determinations name complainants.** The names appear in the listing *and in the file
  URLs*, and redaction only began in FY2024/25. Plan decision D1 is still open. Until it is
  settled, names live in a `restricted` field in local files only, and `build.py` refuses to
  finish if any of them reaches a committed file.

## Run

```sh
python3 -I scripts/census.py    # enumerate from sitemaps + listing pages (cached in local/raw/)
python3 -I scripts/harvest.py   # fetch, hash, snapshot, analyse (resumable; skips valid files)
python3 -I scripts/build.py     # sources.jsonl, sources.public.jsonl, SHA256SUMS, report.md, privacy gate
python3 -I scripts/check.py     # verification (scripts/verify.sh --live adds the plan's literal shell checks)

# Stage 2 (local only, no network)
python3 -I scripts/ocr.py [DOC_ID ...]  # tesseract, 300 dpi, sequential, resumable -> text/ocr/
python3 -I scripts/repair.py            # per-font ToUnicode patch of NFO cases 56-58 -> text/final/
python3 -I scripts/text_final.py        # text/final/ for native + converted, text_manifest.jsonl
python3 -I scripts/check_text.py        # Stage 2 verification + name-leak gate
```

All network access goes through `scripts/polite.py`. It makes one request at a time, at most one
per second, under the user agent `ombudsman-data-research/0.1 (+contact: tim@hellotim.co.za)`. A
failed fetch is retried at most twice (404/410 are not retried), then recorded as a failure.

Requires `pdfinfo`, `pdffonts` and `pdftotext` (poppler), `qpdf`, and Python with `requests`,
`beautifulsoup4`, `PyYAML` and `jsonschema`. Stage 2 adds `pdftoppm`, `tesseract` (with `eng`),
`libreoffice`.
