# Validator state, 2026-11-23 — 16 passing checks, 3 open

`scripts/check_decisions.py` over 545 records. Everything that can be settled mechanically passes;
three checks fail on a total of 34 records, and each needs a **decision**, not a patch.

## Passing (16)

Parse, schema validity, unique IDs, doc coverage, duplicate-file identity, `text_source` agreement
with the manifest, D1 citation policy, restricted-name leakage (in both files), ID-number-shaped
digits, respondent screen on the public file, and the count/consistency checks.

## Open

**1. `year plausible` — 8 records.** Two sub-cases:
- *fiscal_year vs listing date* (5): the record's decision year comes from the signed date, which
  differs from the FAIS table's listing year. Both are true statements about different things.
- *census* (3): the signed-date year differs from the year in the census title.
**Decision needed:** which is authoritative for a `year` column — the year the decision was signed,
or the year it was published? I have used the signed date and recorded it as
`year_from_signed_date`. If the checker should agree, it needs to compare against `date`, not the
census title.

**2. `rules_cited` unverified — 21 records.** 3,600 citations stored; 189 were dropped because the
provision number appears nowhere in the document. The remaining 21 fail a stricter test: the
provision number *is* present, but the instrument ("General Code", "FAIS Act") is not named adjacently,
so attributing it to that instrument is an inference. Mostly `General Code s7(1)` / `s8(1)(b)`.
**Decision needed:** drop these too (loses real citations), or mark the instrument as inferred and
have the checker accept a verified number with an unverified instrument. I would do the latter — the
number is the stronger evidence and the instrument is usually obvious from context.

**3. `respondent_public` — 5 records.** Three publish a name the screen cannot confirm as an entity,
and one holds a conjunction the document does not establish as a single company.
**Decision needed:** none, really — these should be withheld. Not done here because doing it with an
ad-hoc regex instead of `scripts/respondents.py` withheld 102 names and failed schema validation,
which is how this file learned its own lesson (below).

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
