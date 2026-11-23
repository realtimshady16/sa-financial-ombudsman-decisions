# Stage 3c gate: the 20-document sample on Claude Sonnet 5.5, verified by hand

Run and verified 2026-11-23, on the v2 machinery (two topic axes, text-verified `rules_cited`,
entity-only `respondent_public`). The v1 gate (DeepSeek, one `topic`) is kept below as history.

**Verdict: the gate passes, narrowly on one field, and the hand check found three defects that the
validator could not see. All three are fixed and re-checked. The bulk run is cleared to start.**

| gate item | needed | measured |
|---|---|---|
| census, citation, `text_source` | 20/20 | **20/20** |
| `outcome` | ≥ 19/20 | **19/20** (one model error: `nfo-fd-9`) |
| `topic_defence`, where it applies | ≥ 18/20 | **19/20** over all 20 (12/13 where an insurer decision is in dispute) |
| `topic_conduct`, where it applies | ≥ 18/20 | **20/20** |
| `page_anchor` | ≥ 19/20 | **20/20 correct**, 19/20 by the quote mechanism (one by the rule fallback, flagged `low`) |
| `rules_cited` unsupported by the text | 0 | **0 of 108** entries (checker, plus I read the model's citing words for all of them) |
| complainant names or ID numbers in the committed tree | 0 | **0** (`check_decisions.py`, 1905 restricted strings and 833 name tokens) |

**Caveats that matter more than the table.**

- **The outcome gate cannot tell a good model from one that always says `upheld`.** All 20 records are
  `upheld`. The sample has no `dismissed`, and the one real `partly_upheld` is the one Sonnet missed.
  Both offices publish mostly decisions for the complainant (`codebook/outcomes.md`), so this is the
  corpus, not the sample. The 19/20 is a statement about `upheld` and says nothing about the rare values.
- **The sample is not independent of the codebook.** All 9 NFO documents were read when the codebook
  was derived, and so were 3 of the 11 FAIS ones. The topic scores are optimistic by an unknown amount.
- **Sonnet is not deterministic.** I ran the whole gate twice (run 1 through the default Claude Code
  call, run 2 through the lean one below). `outcome` was identical on 20/20. The two topic fields
  differed on **4 of 40 cells**, always `null` in one run and a term in the other (`nfo-fd-50` conduct,
  `fais-d-fe7193dd109d` defence, `fais-d-514c4ef9e6b4` defence, `fais-d-0b57feb5bc19` conduct). So
  whether a *secondary* axis is filled at all is about 90% repeatable, and counts of "documents with
  both axes" should not be quoted to the unit. The scored run is run 2, which is what the bulk run uses.

## 1. What ran

- **Sample.** The same 20 documents as the v1 gate (`codebook/sample-decisions.jsonl`, seed 20261125):
  9 NFO (8 native, 1 OCR) and 11 FAIS (7 native, 4 OCR), 2009–2025.
- **Model.** `claude-sonnet-5-5`, through the Claude Code CLI (`claude -p --output-format json`),
  because pi's own Anthropic sign-in has expired. Every one of the 20 records carries
  `extraction_model: claude-sonnet-5-5`. The CLI runs a small internal step on haiku, so its
  `modelUsage` lists two models; the extractor records the one that was asked for.
- **The call, changed during the gate.** Run 1 used the CLI as it comes: the extraction prompt was sent
  as user text, on top of Claude Code's own system prompt and tool definitions. That cost **~$0.14 and
  ~35k input tokens per document**, of which about 30k was the CLI's own overhead. Run 2 passes
  `--tools "" --system-prompt <the extraction prompt> --disable-slash-commands --strict-mcp-config
  --setting-sources "" --no-session-persistence`: **~$0.026 and ~8k tokens**, five times cheaper and
  twice as fast. On the one document I compared field by field before adopting it, the answer was
  identical. `prompt_sha256` is unchanged: it hashes the prompt text, not the way it is sent.
- **Masking.** Model input is masked by `scripts/redact.py` exactly as in v1. No complainant name and
  no ID number was sent.

## 2. Measured time and cost (run 2, 20 first-time extractions)

| | per document |
|---|---|
| wall time | median **4.5 s**, mean 7.6 s, range 2.5–20.9 s (total 153 s) |
| `total_cost_usd` | median **$0.022**, mean **$0.026**, max $0.068 (total $0.53) |
| input tokens | median 7.9k, max 13.1k; output median 441, max 2.4k |

`total_cost_usd` is the API-equivalent price the CLI reports. **On Tim's subscription it is allowance,
not a bill.** It also counts only the final attempt: 2 documents needed retries (below), which adds a
few cents. Run 1, on the default call, measured $2.82 for the same 20 (mean $0.141).

**Estimate for the bulk run: 524 documents to extract (526 distinct decisions in the queue, 2 already
done), of which 4 have no usable text and make no model call. About 520 calls: ~$14 API-equivalent and
~85 minutes**, at the 2 s minimum gap between calls. The sample's longest input was 13k tokens, and some
FAIS files run to 43 pages, so the tail will be longer.

## 3. Per-field pass rates (20 records, final rules)

A field **passes** when it is what a careful reader would record under the codebook. A call I could
defend either way is counted as a pass and listed in section 4 as *debatable*.

| field | pass | set by |
|---|---|---|
| `decision_id`, `office`, `division`, `doc_id` | 20/20 | census |
| `citation_policy`, `citation_url` | 20/20 | D1 rule, recomputed independently by the validator |
| `text_source`, `extraction_method`, `extraction_model` | 20/20 | text manifest / run |
| `year` | 20/20 | NFO title; FAIS native signed date, else the table. One (`2f28…`, OCR) has no legible year in its text, so it rests on the table and agrees with the case number |
| `date` (FAIS) | 11/11 | native signed date; OCR files keep the table date, 3 of the 4 checked against the signature line |
| **`outcome`** | **19/20** | model, cross-checked by a rule |
| **`topic_defence`** | **19/20** | model |
| **`topic_conduct`** | **20/20** | model |
| **`page_anchor`** | **20/20** | the page of the model's verbatim quote; 19/20 by the quote itself |
| `respondent_raw` | 20/20 | FAIS table (11/11); NFO model string found in the text (9/9) |
| `respondent_public` | 20/20 published values correct; 3 withheld where a company existed (see §4) | `scripts/respondents.py` |
| `respondent_party_type` (extra) | 17/20 | the 3 are the same 3 withheld records: `unknown` where `mixed` is true |
| **`rules_cited`** | **0 wrong of 108** | model proposes, text verifies; regex merged |
| `extraction_confidence` | not a truth field | see §6 |

## 4. Every disagreement, and whether it is a rule bug or a model error

| record | field | extractor said | the document says | kind |
|---|---|---|---|---|
| `nfo-fd-9` (2011) | `outcome` | `upheld` | the office **upheld the insurer** on the first policy (para 6) and ruled for the complainant on the second. The v1 gate settled this as `partly_upheld` | **model error.** The rule cross-check also said `upheld`, so nothing fired: the model and the rule share the blind spot that the order at the end covers only the second policy |
| `nfo-fd-6` (2010) | `topic_defence` | `lapse_and_cancellation` | a funeral policy lapsed, was reinstated, and the insurer said a new waiting period applied. The case title is "interpretation of conditions regarding reinstatement after lapsing" | **codebook overlap, counted as a miss.** The codebook lists case 6 under `policy_interpretation` (waiting period). Both terms fit; the ratio is the waiting-period wording. A rule for "reinstatement and waiting period" would settle it |
| `fais-d-0fc4a77f8770` | `respondent_public` | `<person> and <company> CC` | a natural person and a close corporation, joined in the table string | **rule bug, FIXED (the important one).** `scripts/respondents.py` could not tell "X and Y CC" (one entity) from "person and entity". It published the person's name. **The validator did not catch it**: it exempts any table string equal to a published name, so a wrongly published name vouches for itself. Now such a name is published only when the business words before the last "and" make it plainly one entity, or the document itself calls the whole name a company. The validator has its own copy of that test, and I confirmed it fires on the old output |
| `fais-d-0fc4…`, `fais-d-b57e6fc57f49`, `fais-d-fe7193dd109d` | `respondent_public`, `respondent_party_type` | withheld, `unknown` | each has one real company and one natural person | **the price of the fix, kept on purpose.** Two of the three would have been correct before (a company named after two people, and a table string that lacks "CC"). Withholding errs one way: a wrong withheld costs a name, a wrong publish costs a person. The firm register (Stage 6) is where this closes |
| `fais-d-9a74e28e5f71` | `page_anchor` | 14, flagged `low` (`quote_not_anchored`) | the order is split by a footnote and a page break: "The complaint is upheld" is on page 14, the payment order on page 15 | **not an error, but the quote mechanism failed here.** The model's quote joined the two parts across the footnote, so it matched no page; the rule fallback found 14. Counted as a pass, scored 19/20 by quote |
| `fais-d-fe7193dd109d` | `topic_defence` | `exclusion_clause` | the broker conveyed wrong information about an approved immobiliser; the insurer's earlier decline is not what this determination rules on | **debatable.** The codebook's own example allows both axes. Run 1 said `null`. Counted as a pass |
| `fais-d-514c4ef9e6b4` | `topic_conduct` | `unlicensed_provider` | a funeral home that was a registered FSP but "unlawfully issued policies and accepted premiums without being underwritten" | **debatable.** It fits "carried on insurance business without … registration" and not "no licence at all" |
| `fais-d-0b57feb5bc19` | `topic_conduct` | `other` | a funeral home with no underwriter that did not pay a claim, against Policyholder Protection Rule 2A.8 | **a codebook gap, not an error.** The same story as `514c` got a different term. A `claims_handling` term for conduct is the candidate; the run will show how many documents fall here. Listed under `other` in `codebook/topics.md` |
| `fais-d-0b57feb5bc19` | `rules_cited` | the model once filed section 28(1) under *FAIS Ombud Rules* | the citing words read "SECTION 28(1) OF THE FINANCIAL ADVISORY AND …" | **model error, caught by luck**, because "Rules" had not yet appeared in the text. **New rule: if the citing words name a different instrument, drop the proposal.** It did not fire on this sample, so the sample does not test it |

## 5. `rules_cited` in detail

108 entries over 20 documents: **0 unsupported**. The checker confirms every entry's number follows a
section keyword and its instrument is named; I also read the model's citing words for all of them and
the surrounding text for the six where the instrument is not next to the number.

- **Recall.** For each document I listed every "section / rule / clause N" mention and compared. An
  in-list citation was missed in **2 documents of 20**:
  - `nfo-fd-50`: "Rule 3.2.5", the NFO's own compensation rule. The text never says "Rules" or "our
    Rule", so the instrument is not named and the entry is dropped by design.
  - `fais-d-9a74e28e5f71`: "Section 7(1)", a cross-reference inside a quoted provision.
  - Left out because the instrument is not on the list, correctly: a group scheme's own rules
    (`nfo-fd-1`: "section 2.6.5 of the Rules"), a policy "clause 5.2", the Inspection of Financial
    Institutions Act, the Financial Institutions (Protection of Funds) Act, Board Notice 104.
- **Who found what.** FAIS: 104 entries, of which 26 only the model found, 14 only the regex found,
  the rest both. The regex alone gave a complete list for **5 of 11** FAIS documents; with the model's
  proposals it is **10 of 11**. NFO: 4 entries over 9 documents, since NFO reports rarely cite a section.
- **11 proposals dropped (13 before a small alias fix), and 1 of them is a real loss.** All were
  `instrument_not_named`. Ten were captions cut off before the instrument ("SECTION 28(1) OF THE
  FINANCIAL ADVISORY AND"), which the regex recovers anyway; the eleventh is the `nfo-fd-50` Rule above.
- **A regex rule changed:** a "Rule N.N" in an NFO document used to be filed under the OLTI Rules
  unconditionally. It now needs the instrument named at or before it, like the model's proposals.
  `our Rule 3.2.5` counts as naming the NFO's own rules. This removed 1 entry and is why the
  validator's check #10 now agrees with the extractor.

## 6. Bugs found while running the gate (all fixed)

1. **A schema-invalid record was written and left on disk.** `PPR r2a.8` (lower-case) failed
   validation *after* it had been appended, and the run crashed. The normaliser now upper-cases the
   letter in a dotted number at any depth, and a record is validated **before** it is written; an
   invalid one is logged as `failed_validation` and skipped, and the run goes on. Without this, one
   odd citation at document 300 of 524 would have stopped the bulk run.
2. **A retry cost a whole call.** 3 of the first 20 calls were "unparseable reply" (3 attempts on one
   document, 2 on another). The model copies a line break from the text into a `cite` string, which is
   a raw newline inside a JSON string and invalid. The parser is now non-strict. Re-calling the two
   documents that had failed gave a first-attempt parse for both.
3. **The checker's respondent exemption was circular** (see `fais-d-0fc4…` above).

`extraction_confidence` is still a self-check and not a truth field. Of the 5 records that carry an
error or a debatable call (`nfo-fd-9`, `nfo-fd-6`, `0fc4`, `fe7193`, `514c`), **none is `low`**:
four are `high` and one `medium`. The one `low` record (`9a74`) was right. Read `high` as "no check
fired", not "correct".

## 7. Two records, in full (the public form, so `outcome_quote` is null)

**NFO, both axes set: `nfo-fd-50`** (case 50, 2022; a telephone sale of "non-natural death" cover to
someone who asked for "life cover"). The insurer's reason for declining was the policy's scope, which
is `policy_interpretation`; the ombud's finding is about what was agreed at the sale, which is
`sale_disclosure`.

```json
{"decision_id": "nfo-fd-50", "office": "NFO", "division": "OLTI", "year": 2022, "product_line": "Long-term",
 "citation_policy": "direct", "citation_url": "https://nfosa.co.za/docs/final-determinations-2022-case-50/",
 "text_source": "native", "extraction_model": "claude-sonnet-5-5",
 "outcome": "upheld", "topic_defence": "policy_interpretation", "topic_conduct": "sale_disclosure",
 "rules_cited": [], "rules_proposed": 1, "rules_dropped": 1, "page_anchor": 3,
 "respondent_public": "Liberty Group Limited", "respondent_party_type": "juristic",
 "extraction_confidence": "high", "extraction_flags": ["rules_proposal_dropped"]}
```

**FAIS, both axes set: `fais-d-514c4ef9e6b4`** (2024; a funeral home that took premiums and did not
pay a R20 000 claim). The claim was not paid, and the finding is that it issued policies without an
underwriter. Signed 1 November 2024, listed 6 December.

```json
{"decision_id": "fais-d-514c4ef9e6b4", "office": "FAIS", "division": "FAIS", "date": "2024-11-01", "year": 2024,
 "fiscal_year": "2024/25", "listed_date": "2024-12-06", "product_line": "Long-term",
 "citation_policy": "hash", "citation_url": "https://www.faisombud.co.za/determinations/",
 "text_source": "native", "extraction_model": "claude-sonnet-5-5",
 "outcome": "upheld", "topic_defence": "claim_not_paid", "topic_conduct": "unlicensed_provider",
 "rules_cited": ["FAIS Act s27(5)(c)", "FAIS Act s28(1)", "FSR Act s230", "FSR Act s230(2)"],
 "rules_proposed": 4, "rules_dropped": 1, "page_anchor": 6,
 "respondent_public": "Lebohang Funeral Home (Pty) Ltd", "respondent_party_type": "juristic",
 "extraction_confidence": "high", "extraction_flags": ["listed_date_differs", "rules_proposal_dropped"]}
```

(Both records also carry `field_sources`, `prompt_sha256`, `extractor_version`, `extracted_at` and the
three restricted fields, null in the public file; they are in `decisions.public.jsonl`.)

## 8. Glossary and hooks

- **Axis:** one of the two topic fields. `topic_defence` is the insurer's side of a claim dispute;
  `topic_conduct` is what the adviser or provider did wrong.
- **Circular check:** a test that passes because it trusts the thing it tests. Here, the validator
  exempted a restricted name because it was published, and it was published because the extractor
  said so.
- **API-equivalent cost:** what the same tokens would cost on the pay-per-token API. On a subscription
  it is a measure of allowance used.
- **What this assumes:** that my hand reading is the ground truth. It is one reader, who also wrote
  the codebook. Two of the three `topic` calls I scored as misses or "debatable" turn on codebook
  wording I wrote.
- **Open questions:** (a) whether `claims_handling` should become a conduct term once the full run shows
  how many documents land in `other`; (b) whether `outcome` should record "partly" when a determination
  merely *recites* an earlier ruling against the complainant, as `nfo-fd-9` does; (c) whether the
  stability of the secondary axis (about 90%) is acceptable, or whether the bulk run should call each
  document twice and keep only agreement.

---

# Appendix: the v1 gate (DeepSeek, one `topic`) — superseded by the report above

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
