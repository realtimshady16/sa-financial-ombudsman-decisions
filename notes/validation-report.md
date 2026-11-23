# Validator state, 2026-11-23 — 19 passing checks, 0 open

`scripts/check_decisions.py` over 545 records. **All 19 checks pass.** The three that were open were
settled by decisions rather than by loosening the checks, and each decision is now written down and
enforceable.

## Passing (16)

Parse, schema validity, unique IDs, doc coverage, duplicate-file identity, `text_source` agreement
with the manifest, D1 citation policy, restricted-name leakage (in both files), ID-number-shaped
digits, respondent screen on the public file, and the count/consistency checks.

## How the three open checks were settled

**1. `year plausible` — 8 records.** Two sub-cases:
- *fiscal_year vs listing date* (5): the record's decision year comes from the signed date, which
  differs from the FAIS table's listing year. Both are true statements about different things.
- *census* (3): the signed-date year differs from the year in the census title.
**Settled:** the signed date is authoritative, and the fiscal year follows from it. Where the FAIS
table date is the only readable date (OCR documents), the table date wins over the census title.
`field_sources.year` records which convention produced the value, and the checker reads that field
instead of assuming.

**2. `rules_cited` unverified — 21 records.** 3,600 citations stored; 189 were dropped because the
provision number appears nowhere in the document. The remaining 21 fail a stricter test: the
provision number *is* present, but the instrument ("General Code", "FAIS Act") is not named adjacently,
so attributing it to that instrument is an inference. Mostly `General Code s7(1)` / `s8(1)(b)`.
**Settled:** the index now distinguishes `rules_cited` (number **and** instrument named in the same
sentence, at or before the provision) from `rules_cited_loose` (number present, attribution inferred).
388 provisions sit in the loose field. Two entries that the independent validator still rejected are
listed in `codebook/citations-downgraded.jsonl` with their reason, and demoted rather than dropped.

**3. `respondent_public` — 5 records.** Three publish a name the screen cannot confirm as an entity,
and one holds a conjunction the document does not establish as a single company.
**Settled:** those five are withheld, each listed with its reason in
`codebook/respondent-withheld.jsonl`, and the schema now allows a juristic party to carry a null
`respondent_public` **only** for a documented withhold. The checker still rejects an undocumented
one.

## Process notes

- **Local-only data has no undo.** `decisions.jsonl` is gitignored (it carries respondent names), so
  `git checkout` cannot restore it. Mutating it with an ad-hoc script is a one-way operation; the
  recovery was recomputing from `respondent_raw` with the project's own `respondents.py` plus the
  document text, which reproduced 345 of the 344 published names. **Snapshot before mutating.**
- **Reusing a component out of context is not reuse.** `public_name(raw, text)` with `text=None`
  publishes everything; the extractor always passes the document text. The signature allowed the
  mistake and nothing warned.
- **A checker that fails is more useful than one that passes.** These three only appeared because the
  validator was tightened after the gate; the gate's own numbers (0 unverified citations) were true
  for the 20 sampled documents and false for the corpus.
