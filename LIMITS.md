# What this dataset cannot tell you

Read this before using the numbers. Every item here is a known property of the data, not a caveat
added for form's sake.

## 1. It is not a measure of consumer harm, and it cannot rank firms

**88% of the records say `upheld`** (492 of 545). That is not the ombud finding for consumers nine
times out of ten. Both offices publish selectively: the NFO publishes curated case reports, and the
FAIS Ombud publishes mostly rulings against respondents who ignored a recommendation. The denominator
— complaints that never reached publication — is not in this dataset and is not published anywhere.

So: **do not compute a win rate**, and do not compare firms by outcome. A firm with many `upheld`
records may simply be a firm that generates many complaints.

## 2. It covers published decisions only

Determinations start in **2005** and run to **2025**, but the coverage is per office, not uniform:
OLTI from 2003, Credit Ombud from 2006, OBS from 2009, OSTI from 2016, NFO from 2024, FAIS from 2005.
A time series is only defensible within one office's coverage window, and **2022 has no FAIS
determinations at all**.

## 3. 21 documents have no text

Of 1004 censused files, 983 yielded text. The 21 gaps are 19 image-only documents whose digits were
not trustworthy enough to read (`notes/ocr-sample.md`) and 2 PDFs truncated on the server. Every gap
is listed in `sources.public.jsonl` with a reason.

## 4. Some text came from OCR — and no number here comes from it

166 documents were read by OCR. OCR is adequate for **words** (topics, outcomes, provisions) and
unfit for **digits**: on designed pages it rendered `R3 000.00` as `k3 000,00` and `R20 000.00` as
`R20 D00.00`. Every record carries `text_source`, and **no field in this dataset is transcribed from
OCR text**. If you need an amount from a determination, read the original.

## 5. The labels were produced by models, and partly by two different ones

Every record carries `extraction_model` and `extraction_confidence` (313 high, 206 medium, 26 low).
Most of the corpus was labelled by one model; a block was labelled by a second while the first
provider's usage window was closed, and a re-labelling pass is pending. **A consumer should treat
`extraction_confidence` as the intended filter**, and can filter on `extraction_model` if uniformity
matters.

`outcome` was hand-checked against the ruling text for **every non-`upheld` record** (51 records, 3
corrected — `notes/outcome-check.md`). It has **not** been hand-checked for the 492 `upheld` records;
that direction was sampled at the gate only.

## 6. Citations are verified but not complete

`rules_cited` holds only provisions whose words appear **verbatim** in the decision. 189 proposed
citations were dropped for failing that test, and the stored instrument name is sometimes an
inference from context. So the field under-reports: absence of a provision does not mean the
determination did not consider it.

## 7. Party names are deliberately incomplete

Complainant names are never present. Respondent names are published **only where the party is an
entity**; natural persons and sole traders are withheld, and a firm named after its owner can be
withheld by mistake. The safe direction is to withhold, so expect some missing firms rather than some
surplus people.

## 7a. FAIS links point at a table, not a file

For FAIS the published filename *is* the case caption, so a direct link would put the complainant's
name into the URL of anyone using this dataset. Every FAIS record therefore links to the
determinations table, with `citation_locator` describing where the row sits. One extra click, and the
name stays on the office's page rather than in yours.

## 8. This is not legal advice

It is an index. A record summarises how one model read one document; the determination is the
authority, and `citation_url` takes you to it.
