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
| `url` | url | **published-facing** link, chosen per document by `citation_policy` (below). NFO: the doc page. FAIS with a name in the filename: the `/determinations/` list page, paired with `filename_sha256` |
| `citation_policy` | enum | `direct` when the filename carries no personal name; `hash` when it does — see D1 below |
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
`suspect`, `suspect_reasons`, `restricted_fields`, `restricted` (local only),
`needs_ocr`, `damaged`, `unreadable`, `damage_reasons`.

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

### `text` — one row per document (Stage 2, `text_manifest.jsonl`, committed)

There is one row for each `document` row, in the same order. It describes `text/final/<doc_id>.txt`,
which is local only, like every derived text: FAIS bodies name people. The row has no names and
no restricted fields.

| field | type | notes |
|---|---|---|
| `doc_id` | string | → `document` |
| `text_source` | enum | `native` · `ocr` · `html` · `repaired` · `converted` · `none` (see below) |
| `pages` | int\|null | PDF pages. For the converted `.ppt` it is the slide count; `null` for `.doc` and HTML |
| `words` | int\|null | letter runs in `text/final`, the same `pdfcheck.text_metrics` count as `document.words` |
| `common_word_rate` | float\|null | Stage 1's metric on `text/final`. English-only, so non-English newsletters score low by design |
| `ocr_mean_confidence` | float\|null | mean Tesseract word confidence (0–100). Set whenever OCR ran, even if the output was not promoted |
| `repair_fonts` | list\|null | `repaired` only: `[{font, obj, map: {shown_as: repaired_to}}]`, one entry per PDF font object whose ToUnicode map was patched |
| `notes` | string\|null | how the text was made, normalisation counts, and any known gap (watermark-only text layer, embedded image pages) |

**`text_source` vocabulary**

**Damage flags — `suspect` is not one thing.** `suspect` was originally a single boolean and read as
"this document is damaged", which overstated it sixtyfold. Derive, never infer:

| flag | meaning | count at 2026-11-23 |
|---|---|---|
| `needs_ocr` | no text layer — a scan awaiting OCR | 185 |
| `damaged` | text present but corrupt (`quartz_cmap_holes`, `no_tion_in_long_english_text`, `replacement_chars`, `many_suspect_tokens`) | 4 |
| `unreadable` | neither: truncated at the source, permanent gap | 2 |

`scripts/flags.py` computes all three from `suspect_reasons` and writes them into both census files.
**No figure in `figures.csv` may come from a document where `text_source` is `ocr` or `html`** — OCR is
good enough for words and not for digits, which is why the split exists.

| value | meaning |
|---|---|
| `native` | the PDF's own text layer: Stage 1's `pdftotext -layout` output plus `scripts/normalize.py` (expands U+FB00–FB06, drops U+00AD; deliberately *not* NFKC, see that file) |
| `ocr` | Tesseract output from an image-only PDF, promoted after the gate (`notes/ocr-sample.md`) |
| `repaired` | re-extracted from a copy of the PDF whose fonts' ToUnicode maps were patched per font object (`scripts/repair.py`) |
| `converted` | legacy MS Office file converted with LibreOffice |
| `none` | no text in `text/final` yet. `notes` says why: OCR gated, PDF truncated at the source, or HTML-only page not extracted |

### `decision` — one per distinct determination file (Stage 3, `decisions.jsonl`)

Machine-checkable half: [`decision.schema.json`](decision.schema.json), validated by
`scripts/check_decisions.py`. Vocabularies: [`codebook/topics.md`](../codebook/topics.md) and
[`codebook/outcomes.md`](../codebook/outcomes.md). Built by `scripts/extract_decisions.py`.

**Unit, changed from the v0 stub.** v0 said "FAIS: one per table row (509)". Stage 3 builds one record
per **distinct file**. A file is the thing that can be cited, anchored to a page and hashed. The
census has 552 determination files, and they hold 545 distinct byte strings: 3 NFO yearly packages
duplicate a case page, and 4 FAIS files are each linked from two table rows. A duplicate folds
into its canonical record's `duplicate_doc_ids`. The 509-row parity is recoverable through
`sources.jsonl`'s `listing_row_indices`, which stays local because the row order is the live
page's and is not stable.

| field | type | notes |
|---|---|---|
| `decision_id` | string | `nfo-fd-<case>` · `fais-d-<12 hex of the canonical doc_id>`. Never a name |
| `doc_id`, `duplicate_doc_ids` | string, string[] | → `document`. The canonical file (the NFO per-case page, else the lowest doc_id), plus byte-identical copies |
| `office` / `division` / `kind` | enum | from the census. `kind` is always `determination` in v1 (recommendations are a separate set of 24 files) |
| `year`, `date`, `fiscal_year` | int, date, `YYYY/YY` | FAIS: from the official table's date. NFO: from the title. A year is read from text only if the census has none **and** the text is native. **Never from OCR or HTML** |
| `product_line` | string | FAIS table `category` verbatim. NFO: `Long-term` |
| `topic_defence` | enum\|null | **axis 1** (codebook/topics.md): what the insurer's side said, in a dispute over a claim or a policy decision, and what the ombud rules on. Its own 10-term vocabulary. `null` when no insurer decision is in dispute. Model-assigned |
| `topic_conduct` | enum\|null | **axis 2** (codebook/topics.md): what the adviser, broker or provider did wrong, as the ombud found it. Its own 8-term vocabulary. `null` when no conduct finding is made. Model-assigned. A record may carry both axes, one, or (for a non-ruling) neither. **v2 replaces v1's single `topic` and `topics_secondary`** |
| `outcome` | enum\|null | `upheld` · `partly_upheld` · `dismissed` · `referred` · `settled` · `amendment` · `no_ruling` (codebook/outcomes.md). Model-assigned and cross-checked by a rule. `null` only when there is no usable text |
| `page_anchor` | int\|null | page of `text/final` on which the model's verbatim outcome quote was **found**. A quote that cannot be found gives `null` and confidence `low` |
| `outcome_quote` | string\|null | **restricted**: the anchored sentence, from masked text. Kept locally for audit, never published |
| `respondent_raw`, `respondent_canonical` | string\|null | FAIS: the table's respondent. NFO: the insurer as written, kept only if the string occurs in the text. **Restricted for both offices: local only, never in the public file** |
| `respondent_public` | string\|null | **the only respondent field that is published.** The name of the respondent when it is an *entity* (Pty Ltd, CC, Ltd, Insurers, Bank, Brokers, Administrators …), `null` when it is a natural person (a sole adviser is a person) or cannot be shown to be an entity. `X CC and Jan Smith` carries `X CC` only; `Jan Smith t/a Z` carries nothing. Computed by `scripts/respondents.py`; the validator re-checks it independently |
| `respondent_party_type`, `respondent_source` | enum | `juristic` (every party an entity) · `mixed` (some) · `natural` (none, and none looks like a business) · `unknown` (no entity, but a business-looking name we refused to publish). `fais_table` · `text_anchored` |
| `rules_cited` | string[] | normalised to `<instrument> s<section>(<sub>)` or `<instrument> r<rule>`. **The model proposes, the text verifies:** the model lists provisions with the words that cite each; a proposal is kept only if those words occur verbatim in the document, contain the provision's number and every sub-part, and the instrument is named in those words or earlier in the document. A regex pass over the text is merged in (verbatim by construction). Anything the text cannot show is dropped and counted. Sorted, not in order of citation. Ranges list their two ends only |
| `rules_proposed`, `rules_dropped` | int\|null | how many provisions the model proposed and how many failed verification. Recall per office is in `codebook/rules.md` |
| `citation_policy`, `citation_url`, `filename_sha256` | | D1, below. Recomputed independently by the validator |
| `text_source` | enum | copied from `text_manifest.jsonl`; the validator checks it |
| `extraction_method`, `extraction_model`, `prompt_sha256`, `extractor_version` | | `model+rules` · `rules` · `none`. The model is recorded per record (`anthropic/claude-sonnet-5-5` through `pi -p` for the v2 run) |
| `extraction_confidence`, `extraction_flags` | enum, string[] | `low` if the model and the rule disagree, the quote cannot be anchored, or the model reply is invalid or off-vocabulary. `medium` if the rule is silent, the text is OCR, the model is unsure, or a page is an image not yet OCR'd. Otherwise `high` |
| `field_sources` | object | which mechanism set each field |
| `restricted_fields` | string[] | nulled in `decisions.public.jsonl`: always `respondent_raw`, `respondent_canonical`, `outcome_quote`, for both offices |

**No prose abstracts and no amounts in v1.** An abstract is interpretation. An amount from an
OCR'd determination is exactly the digit risk the Stage 2 gate measured.

**Respondents: entities are published, natural persons are withheld (decided for v2).** The FAIS table names
the parties; many respondents are sole advisers, and a sole adviser is a person. `respondent_public`
carries a name only when the party is an entity, and the rule errs towards withholding. The committed
file never carries `respondent_raw`. Residual risk, stated: a business named after its owner
("Surname Brokers") can pass the screen; Stage 6's firm register is where that closes. Complainant names,
and every respondent string that is not published, remain restricted (`check_text.py` and
`check_decisions.py` treat them as needles; they exempt only the strings published as `respondent_public`).

**Text sent to the model is masked first** (`scripts/redact.py`): party names from the
restricted table, honorific + name, capitalised words never seen in lower case in the corpus, and
street addresses. This is best-effort, and it is documented as such in that file.

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

## Citation policy (D1, decided 2026-11-22)

On FAIS the filename *is* the case caption, so a direct link puts a party name into the URL — and from
there into any page, sitemap or git history that carries it. Measured on the live determinations table
(552 links, 539 unique): **515 filenames contain a party name**, 26 are case-numbered, 11 say "Redacted"
while still carrying surnames. NFO determinations carry no names at all.

Rule, applied per document:

- **`citation: direct`** — filename carries no personal name: all NFO determinations, the 26
  case-numbered FAIS files, annual reports, newsletters, trend reports, financial statements.
- **`citation: hash`** — filename carries a party name: `url` = `/determinations/`, with
  `filename_sha256` identifying the document. One extra click, no name in our output.

A hyperlink to lawfully published material is not a republication — that is why this design is
defensible. The two things it does not buy: a direct link opens a **PDF**, not the ombud's page (the
list page is the page); and the *index* still processes personal information even when every individual
link does not, which is the reason the hash tier exists.
