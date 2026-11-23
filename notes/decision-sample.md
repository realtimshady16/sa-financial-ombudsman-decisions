# Stage 3 gate: the 20-document decision sample, verified by hand

Run and verified 2026-11-23. This note is the gate report for `scripts/extract_decisions.py`.

**Verdict: the machinery is sound, and outcome, topic and citation are good enough to run. One
field, `rules_cited`, is not: in FAIS it misses most of the provisions an ombud discusses. Fix
that, or accept it knowingly, before the 532-document run.** Every disagreement is listed below,
so the decision can be made on the evidence.

## 1. What ran

- **Sample.** 20 canonical determination files, drawn by `--make-sample`, which is a stratified
  random draw with a fixed seed. NFO has 9 year bins over 2009–2024, and FAIS has 11 over
  2009–2025. The seed is **20261125**. The base seed 20261123 was bumped twice until the brief's
  constraints held. The list is `codebook/sample-decisions.jsonl`.
  - 9 NFO: 8 native, 1 OCR.
  - 11 FAIS: 7 native, 4 OCR.
  - Years span 2009–2025.
- **The brief's "≥ 1 `html`" is unsatisfiable.** No determination has HTML text: the 68 `html`
  documents are all digests (case studies). The sample has 5 OCR documents against the 3 asked
  for. No `repaired` file was drawn.
- **The sample is not independent of the codebook.** I derived the vocabularies by reading all 57
  NFO headnotes and endings, so all 9 sampled NFO documents had been seen before. 3 of the 11
  FAIS documents (`fe7193dd109d`, `51d9eef145f1`, `0b57feb5bc19`) were also in the ~50 FAIS
  documents read for the codebook. Treat the topic score as somewhat optimistic.
- **Model.** `opencode-go/deepseek-v4.1-flash` through `pi -p --mode json`. This is Tim's pi
  default: no tools, no session, no context files. The model makes one call per document,
  sequentially, with at least 2 s between calls. It sees **masked** text only
  (`scripts/redact.py`).
- **Two passes.**
  - **v1 as-run:** the records exactly as the run produced them, saved in
    `local/decisions.sample-asrun.jsonl`.
  - **v1.1:** the same saved model replies re-processed with the rule fixes this review found
    (`--reprocess`, no new model calls). These are the records committed in
    `decisions.public.jsonl`.

  The prompt did not change between the passes, so v1.1 measures the rule fixes and nothing else.

## 2. How I verified

For every record I read, with names masked:

- the opening (caption or headnote, and the complaint);
- the anchored page;
- the region before the signature line;
- the context of every rule cited.

These come from `scripts/decision_worksheet.py`. For `rules_cited` I also listed every
"section/rule/clause N" mention the regex did *not* capture, which is how the recall gap below
was found. I checked `year` against every date in the text, and the FAIS `date` against the
signed "DATED AT …" line.

A field **passes** when it is what a careful reader would record under the codebook.
`respondent_party_type: unknown` for a plain natural person counts as a fail: it is not wrong,
but it is not informative.

## 3. Per-field pass rates (20 records)

| field | v1 as-run | v1.1 | how it is set |
|---|---|---|---|
| `decision_id`, `office`, `division`, `doc_id` | 20/20 | 20/20 | census |
| `citation_policy`, `citation_url` | 20/20 | 20/20 | D1 rule; the validator recomputes it independently |
| `text_source` | 20/20 | 20/20 | text manifest |
| `extraction_method` | 20/20 | 20/20 | factual |
| **`outcome`** | **20/20** | **20/20** | model, checked by a rule |
| **`topic`** | **19/20** | **19/20** | model |
| `topics_secondary` (extra field) | 19/20 plausible | 19/20 | model |
| `year` | 19/20 | 20/20 | FAIS table, or the native signed date (v1.1); NFO title |
| `date` (FAIS, extra field) | 9/11 | 11/11 | same |
| **`page_anchor`** | **18/20** | **20/20** | the page where the model's verbatim quote is found |
| `respondent_raw` | 20/20 | 20/20 | FAIS table (11/11); NFO model string anchored in the text (9/9) |
| `respondent_canonical` | 20/20 | 20/20 | normalisation only; not a firm register |
| `respondent_party_type` (extra field) | 14/20 | 17/20 | heuristic. The 3 left are natural persons recorded as `unknown` |
| **`rules_cited`** | **11/20** | **13/20** | regex. NFO 9/9. **FAIS 2/11 → 4/11.** Precision: no wrong entry among 67 (v1) or 83 (v1.1) |
| `extraction_confidence` | not a truth field; see §5 | | |

## 4. Every disagreement

| record | field | extractor said | the document says | kind |
|---|---|---|---|---|
| `nfo-fd-9` (case 9, 2011) | `page_anchor` | 1 | 3. The order is on the last page | **model error, caught by rule (v1.1).** The model "quoted" two non-adjacent passages stitched into one (p.1's "the office upheld the insurer's decision…" plus p.3's order). v1 anchored the prefix to p.1. v1.1 anchors the prefix and suffix separately, detects the stitch (`quote_stitched`), takes the later page, and drops confidence to `low` |
| `nfo-fd-25` (case 25, 2016) | `page_anchor` | 3 | 6 | **fixable rule (fixed).** NFO reports restate the provisional ruling, in the same words, before the final one. v1 took the first occurrence; v1.1 takes the last |
| `fais-d-0fc4a77f8770` (2016) | `topic` | `advice_suitability` | the advice was unsuitable, **and** the adviser was the only member of the close corporation running the scheme he sold (conflict of interest under Code s3(1)(b), s4(1)(d)) | **codebook ambiguity.** By the ratio, the model is right. By the codebook's literal precedence ("misappropriation_fraud: the respondent … ran the scheme"), it is wrong. The codebook must decide whether "ran the scheme" needs a finding of dishonesty |
| `fais-d-aca9bd9715ea` (Sharemax) | `year`, `date` | 2021, 2021-01-22 | signed 13 October 2020 | **fixable rule (fixed): the FAIS table date is a *listing* date.** Across the corpus it equals the signed date in 301 of 321 native files. 13 differ by a whole year, mostly a January 2021 bulk listing of decisions signed in 2019–2020. v1.1 uses the native signed date and keeps the table's as `listed_date`. OCR files keep the table date, because no digits are read from OCR |
| `fais-d-514c4ef9e6b4` (2024) | `date` | 2024-12-06 | signed 1 November 2024 | same rule (fixed). The year was right |
| `nfo-fd-15` | `respondent_party_type` | `unknown` | an insurer (Momentum) | **fixable rule (fixed).** The NFO only has jurisdiction over subscribing insurers, so every NFO respondent is juristic |
| `fais-d-e20138437716` | `respondent_party_type` | `juristic` | a company **and** a natural person, comma-joined in the table | **fixable rule (fixed).** The split now covers commas |
| `fais-d-0b57feb5bc19` | `respondent_party_type` | `mixed` | one company whose name contains "and" | **fixable rule (fixed).** v1.1 checks the text for "<name> … a company duly incorporated" |
| `fais-d-51d9eef145f1`, `fais-d-9a74e28e5f71`, `fais-d-aca9bd9715ea` | `respondent_party_type` | `unknown` | natural persons | **heuristic limit, not fixed.** No juristic marker does not prove a person. It is left `unknown` on purpose; the firm register is Stage 6. The name is not published, so this has no public effect |
| 7 FAIS records (`fe7193dd109d`, `51d9eef145f1`, `9a74e28e5f71`, `0fc4a77f8770`, `bc530657c949`, `e20138437716`, `aca9bd9715ea`) | `rules_cited` | incomplete | FAIS determinations discuss the Code under a heading ("H. GENERAL CODE OF CONDUCT … [25] Section 3(1) provides …", "the following sections of the Code: Section 3 (1) (a) (i) and (iii); Section 7 (1) (a)"), or say "In terms of section 11 a provider is required …". The instrument is named once, *before* the list | **fixable, not fixed: the regex attaches an instrument only within the same phrase.** v1.1 fixed the cheap cases: enumerations ("sections 7, 8, 9 and 11"), sibling paragraphs ("8 (1) (a), (b) and (c)"), ranges ("(a) to (d)"), "Rule 6(b) of the Rules on Proceedings of this Office", and "Financial Service Ombud Schemes Act". That added 16 correct citations and removed none. Also missed: instruments outside the list (Board Notice 104, Inspection of Financial Institutions Act, Financial Institutions (Protection of Funds) Act), and "Clause 7(1)(c)(vii) of the General Code", where "clause" is not a keyword |
| `fais-d-2f2862620653`, `fais-d-b57e6fc57f49` | `rules_cited` | incomplete in v1 | FSOS Act s10, s11; Code s7 (an enumeration) | fixed in v1.1 |
| `nfo-fd-43` | `rules_cited` | `LTIA s53` | "section 53, in particular 53 (2) (b)" | counted as a pass: the section is right, the subsection is not captured |
| `nfo-fd-1` | `topic` vs my codebook | `lapse_and_cancellation` | the decision turns on the insurer ending cover for unpaid premiums after membership ceased | **the model was right and my codebook evidence was wrong.** I had filed case 1 under `disability_assessment` from its headnote. The codebook has been corrected |

**The rule cross-check on `outcome`:**

- it agreed with the model on 17 documents;
- it was silent on 2 (`nfo-fd-15`, `fais-d-fe7193dd109d`);
- it disagreed on 1 (`nfo-fd-9`), and there **the rule was wrong**: the complainant lost on one
  policy and won on the other, so `partly_upheld` is correct.

## 5. `extraction_confidence` is a self-check, not a guarantee

As-run, 9 records were `high`, 10 `medium` and 1 `low`. Counting errors in the fields confidence
is meant to cover (outcome, topic, page anchor):

- the one `low` record held a real page error;
- **2 of the 9 `high` records were wrong**: the duplicated-quote page in `nfo-fd-25` (now fixed)
  and the topic ambiguity in `0fc4a77f8770`;
- the `medium` records held none.

Confidence does not look at `rules_cited` at all. Read `high` as "no check fired", not "correct".

## 6. Privacy: what happened, plainly

- **An SA identity number reached the model and this session's transcript.** In
  `fais-det-51d9eef145f1`, an OCR'd 2011 determination, the first respondent (a natural person)
  is described with her 13-digit ID number. The v1 masker covered names and street addresses but
  not ID numbers. `redact.py` now has an ID-number layer at every masking level, applied before
  anything else. The other 19 documents went out masked, but masking is best-effort: partial
  addresses ("Block 94, Flat 3") and some first names that are also common words can pass. **20
  masked determinations were sent to opencode-go's DeepSeek endpoint. I do not know that
  provider's retention terms.** If that matters for the full run, a local model is the
  alternative. Ollama is installed, but no model is pulled and there is no working GPU.
- **Nothing restricted is in the committed tree.** Two separate checks pass:
  - `check_decisions.py`: 1912 restricted strings plus 833 complainant name tokens, against every
    public field and the whole committable tree. 0 hits.
  - `check_text.py`'s Stage 2 gate, unchanged. 0 hits.
- **FAIS respondent names are not published in v1** (SCHEMA.md, decision section).
  `check_text.py` treats every FAIS respondent string as restricted, and many respondents are
  sole traders. Publishing juristic respondents is a decision for Tim, and it belongs to Stage 6.
- **D1 does not match the measurement.** D1 expected 26 FAIS determinations to be
  direct-citable, because their filenames are case numbers. Under a conservative test (every
  letter run in the filename must be a generic word), **0 of 552 FAIS links pass**. 514 carry a
  token from their own row's party names, and the other 38 each carry at least one token that is
  not prose in this corpus. So every FAIS record is `citation: hash`. One false `hash` costs a
  reader a click; one false `direct` would publish a name.

## 7. Measured cost

Measured over all 20 first-time extractions, each with exactly one attempt and no errors:

- **Time:** median **16.6 s** per document (mean 22.1, range 6.1–94.6).
- **Tokens:** median input 4,285, output 1,492, of which 1,401 are reasoning.
- **Money:** median **$0.00165** per document; $0.037 for all 20.

**Estimate for the queue (532 documents): about 2.4–3.3 h sequential, about $1.** The sample
had no very long FAIS determination: the largest input was 6.7k tokens, while some files run to
43 pages. So the tail will be longer than this sample shows.

## 8. Doubts about the topic/outcome split, from the corpus

1. **Outcome is almost a constant in what is published.** The sample is 19 upheld and 1 partly
   upheld. The whole-corpus phrase census agrees: FAIS has 395 "upheld" and 26 "dismissed" among
   the 425 standard phrases, and every NFO case report I read ended in the complainant's favour.
   NFO publishes curated case reports, and FAIS mostly publishes determinations against
   respondents who ignored a recommendation. `outcome` cannot carry a "win rate" claim. The
   informative variation is *what was awarded*, and v1 deliberately records no amounts.
2. **`topic` conflates two axes.** NFO topics answer "what was the insurer's defence"
   (non-disclosure, exclusion, late notification). FAIS topics answer "what did the adviser do
   wrong" (unsuitable advice, fraud, no licence). In the sample, NFO used 7 terms and FAIS used
   5, and only `sale_disclosure` was shared. A two-field design (`conduct_finding` for FAIS,
   `claim_defence` for insurer complaints, plus the existing `product_line`) would remove most of
   the precedence problems, including the 0fc4 ambiguity.
3. **FAIS investment cases are one story with three labels.** A failed scheme, an adviser who sold
   it, and sometimes an adviser who ran it. `advice_suitability`, `misappropriation_fraud` and
   `unlicensed_provider` are the same disputes cut by different findings. They are the topic
   most likely to disagree between two careful readers.
4. **Clusters distort counts.** There are mass complaints (the 2010 binder dispute, the 2025
   funeral non-payments) and a January 2021 bulk listing that re-dates 2019–2020 decisions. Any
   per-year or per-topic count needs cluster and listing-date caveats. One further file
   (`fais-det-b033072304a7`) has a "DATED" line in 2022 against a 2019 listing. v1.1 rejects such
   signed dates (`signed_date_after_listing`), but that file deserves a look, given the plan's
   "no FAIS decisions in 2022".

## 9. Before the full run

1. **Decide on `rules_cited`.** The cheapest real fix is to let the model propose citations as
   part of the call it already makes, then keep only those whose section number *and* instrument
   are found in the text within one paragraph. That is the same string-anchoring idea the review
   asked for on figures. It changes the prompt, so the 20-document sample must be re-run and
   re-checked. The alternative is to accept regex recall, document it, and use `rules_cited` as
   "provisions cited in a self-identifying phrase".
2. **Settle the 0fc4 precedence question** in `codebook/topics.md`, or adopt the two-axis split
   in §8.2.
3. **Launch with `python3 -u`** under `bg-run`. Without it the log is block-buffered, and the run
   looks silent until it ends. Progress is in `local/decisions-progress.jsonl` either way.

## Glossary and hooks

- **String-anchoring:** a model's output is accepted only if its quote, or its citation, is found
  verbatim in the source. That turns "the model said so" into something checkable.
- **Ratio (ratio decidendi):** the reason a decision actually turns on, as opposed to everything
  else the decision discusses.
- **Listing date vs signed date:** FAIS publishes a table of determinations with a date per row.
  That date is when the row was listed, which is usually but not always the date the ombud signed
  the decision.
- **What this assumes:** that hand-reading masked text is enough to judge topic. Masking hides
  firm names in places, but it never hid the reasoning in these 20.
- **Open question:** does the provider behind opencode-go retain prompts? That decides whether
  the full run's 532 masked documents may go there.
