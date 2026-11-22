# Schema v0 — stub contract

Stage 1 deliverable. This fixes **names, identifiers and vocabularies** so every later stage writes
to the same shape. It is deliberately thin: the full codebook (what "complaint" meant in each era,
fiscal calendars, every gap) is Stage 4. Only `document` is populated in Stage 1; the other four
entities are declared so Stages 3–6 have something to conform to.

Machine-checkable half: [`document.schema.json`](document.schema.json) (JSON Schema 2020-12),
validated against every row of `sources.public.jsonl` by `scripts/check.py`.

## Conventions

- **IDs are opaque, stable, lowercase, `[a-z0-9-]`**, and never contain a natural person's name.
- **Dates** are ISO 8601. A FAIS fiscal year is written `YYYY/YY` and runs **1 April – 31 March**.
  NFO-family reports are calendar years, except NFO 2024, which covers **1 Mar – 31 Dec 2024**
  (10 months; recorded in the codebook, not normalised away).
- **Restricted fields.** A row may list field names in `restricted_fields`. Those fields exist only
  in local files and are nulled in anything committed or published. Holding a field there is not a
  publication decision; D1 in the plan decides what (if anything) is ever published.
- **No inferred values.** A field the source does not state is `null`, never guessed.

## Entities

### `office`

| field | type | notes |
|---|---|---|
| `office_id` | enum | `NFO` (National Financial Ombud Scheme SA, `nfosa.co.za`) · `FAIS` (Ombud for Financial Services Providers, `faisombud.co.za`) |
| `name` | string | as the office styles itself |
| `site` | url | |
| `statute` | string\|null | FAIS: statutory office under the FAIS Act 37 of 2002. NFO: industry ombud scheme (recognition basis to be confirmed in the Stage 4 codebook) |

### `division` (vocabulary on `document.division`)

| code | meaning | office |
|---|---|---|
| `OLTI` | Ombudsman for Long-Term Insurance (pre-merger) | NFO |
| `OBS` | Ombudsman for Banking Services (pre-merger) | NFO |
| `OSTI` | Ombudsman for Short-Term Insurance (pre-merger) | NFO |
| `CO` | Credit Ombud (pre-merger) | NFO |
| `NFO` | the merged National Financial Ombud (2024 →) | NFO |
| `FAIS` | the FAIS Ombud (one office, no divisions) | FAIS |

### `document` — one row per fetched file (`sources.jsonl`)

Required by the brief, in order:

| field | type | notes |
|---|---|---|
| `doc_id` | string | NFO: `nfo-<wpdm_id>` (`-<n>` per file in a multi-file package). FAIS: `fais-det-<sha256(filename)[:12]>`, `fais-ar-<YYYY>-<YY>`, `fais-nl-<slug>`, `fais-cs-<slug>` |
| `url` | url | **published-facing** link. NFO: the doc page. FAIS determinations: the `/determinations/` list page (D1 option a), paired with `filename_sha256` |
| `fetch_url` | url\|null | where the bytes came from. **Restricted** for FAIS determinations (the filename carries a party name) |
| `sha256` | hex | of the bytes served — the only integrity record (the NFO `.md` card's size is wrong) |
| `fetched_at` | datetime | UTC |
| `bytes` | int | |
| `office` | enum | `NFO` \| `FAIS` |
| `division` | enum\|null | see above |
| `doc_type` | enum | see vocabulary below |
| `period_covered` | string\|null | `YYYY` · `YYYY/YY` (FAIS fiscal) · `YYYY-MM-DD` (a decision date) · `YYYY-MM/YYYY-MM` (a range) |
| `pages` | int\|null | from `pdfinfo` |
| `producer` | string\|null | from `pdfinfo` — the damage diagnostic |
| `fonts_have_tounicode` | bool\|null | every font has a ToUnicode map (`pdffonts` `uni`). `null` = no fonts (image-only) or not a PDF |
| `has_text_layer` | bool\|null | `pdftotext` yields ≥ 20 words. `null` = not a PDF |

Extras recorded in Stage 1 (stable names; later stages may add, not rename):
`year`, `fiscal_year`, `title`, `language` (ISO 639-1/-3), `category` (source's own label),
`tags`, `updated` (site's date, not the document's), `wpdm_id`, `package_url`, `doc_pages`,
`filename_sha256`, `listing_row_indices`, `link_labels`, `snapshot`, `text_raw`, `fonts`,
`fonts_missing_tounicode`, `cmap_hole_count`, `cmap_holes`, `words`, `words_per_page`,
`common_word_rate`, `tion_count`, `suspect_tokens`, `camel_tokens`, `soft_hyphens`, `ligature_chars`,
`replacement_chars`, `pdf_readable`, `category_source`, `served_filename`,
`suspect`, `suspect_reasons`, `restricted_fields`, `restricted` (local only).

**`doc_type` vocabulary**

| value | meaning | is a decision? |
|---|---|---|
| `determination` | a final ruling (NFO Final Determination; FAIS determination) | yes |
| `recommendation` | a FAIS recommendation (the table's "Recommendation" link label; legal effect to be stated in the codebook) | partly — record, don't count as outcome |
| `annual_report` | | no |
| `financial_statements` | | no |
| `trend_report` | NFO semi-annual trend report (2026 →) | no |
| `newsletter` | FAIS newsletter, any language | no — editorial |
| `digest` | case studies, bulletins, Briefcase, Ombuzz, guides: the office's own retelling | no — editorial; any outcome field derived from one is flagged `editorial` |

### `decision` — one per ruling (Stage 3, `decisions.jsonl`)

| field | type | notes |
|---|---|---|
| `decision_id` | string | FAIS: one per **table row** (509), not per file. NFO: `nfo-fd-<case>` |
| `office` / `division` | enum | |
| `year` / `date` | int / date | decision date as the source states it |
| `fiscal_year` | string\|null | FAIS `YYYY/YY` |
| `kind` | enum | `determination` \| `recommendation` |
| `topic` | enum\|null | controlled vocabulary, seeded from the FAIS table categories + `complaint-category` taxonomy (Stage 4) |
| `outcome` | enum\|null | `upheld` · `partly_upheld` · `dismissed` · `settled` · `other` — from the decision text, with page anchor |
| `amount_awarded` | number\|null | ZAR, as stated |
| `respondent_id` | string\|null | → `participant`; published only where `party_type = juristic` |
| `rules_cited` | string[] | |
| `source_doc_ids` | string[] | → `document` (a FAIS row can link 1–3 files; a file can serve 2 rows) |
| `page_anchor` | int\|null | page of the outcome statement |
| `restricted` | object | local only: complainant/respondent as listed |

No prose abstracts in v1.

### `participant` — firms and respondents (Stage 6, `firms.json`)

| field | type | notes |
|---|---|---|
| `participant_id` | string | |
| `canonical_name` | string | only for `party_type = juristic` |
| `party_type` | enum | `juristic` \| `natural` \| `unknown` |
| `aliases` | string[] | every spelling seen ("CC and" / "CC &", case variants) |
| `registration_no` | string\|null | CIPC / FSP number when stated |

### `figure` — one number from one page (Stage 5, `figures.csv`)

| field | type | notes |
|---|---|---|
| `figure_id` | string | |
| `source_doc_id` | string | → `document`; must exist in `sources.jsonl` |
| `page` | int | |
| `label_verbatim` | string | exactly as printed |
| `value` | number | |
| `unit` | string | `complaints`, `ZAR`, `percent`, `days`… |
| `office` / `division` | enum | |
| `period` | string | as `period_covered` |
| `measure` | enum | Stage 4 codebook: `received` · `accepted` · `formal` · `closed` · … (what "complaint" means differs by era) |
| `verification` | enum | `hand` · `anchored+reconciled+sampled` · `anchored+reconciled` — never null |
