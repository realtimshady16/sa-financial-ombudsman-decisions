# OCR gate — 5-document sample (Stage 2, step 1)

Run 2026-11-22 with `scripts/ocr.py`: `pdftoppm -r 300 -gray`, one page at a time, then
`tesseract 5.5.3 -l eng` (leptonica 1.87; `eng` is the only language installed). All 185
image-only rows are tagged `en` in the census, and every sample document is English. The output
is in `text/ocr/<doc_id>.txt`, with per-page TSV and the mean word confidence in
`text/ocr/<doc_id>.json` (all local, under the gitignored `text/`).

**Result: the gate FAILS on the amounts criterion, so bulk OCR was not run.** The three
determinations and the NFO ruling pass every check. The annual report fails: 3 of the 10 rand
amounts on its checked page are wrong.

## Sample

The sample is three FAIS determinations (old, middle and recent), one NFO determination and one
annual report. Each is the representative of its class among the 185.

| doc_id | what | pages | source images | tesseract mean conf | words¹ | `common_word_rate`¹ | native median, same doc_type² |
|---|---|---|---|---|---|---|---|
| `fais-det-78abea9da08d` | FAIS determination, short-term, 2005-07-21 (oldest image-only) | 21 | 100 ppi grey JPEG | 90.92 | 5,910 | **0.5144** | 0.4637 |
| `fais-det-0787110f99f5` | FAIS determination, investments, 2010-10-25 (the bulk year: 72 of 159) | 12 | 150 ppi RGB JPEG | 90.47 | 1,868 | **0.4599** | 0.4637 |
| `fais-det-895cdb015126` | FAIS determination, investments, 2018-09-17 (newest image-only; Xerox scanner) | 15 | 100 ppi grey JPEG | 90.29 | 3,724 | **0.4930** | 0.4637 |
| `nfo-5534` | NFO Final Determination 2014, case 18 | 14 | 200 ppi grey JPEG | 90.02 | 3,635 | **0.4900** | 0.5086 |
| `fais-ar-2012-13` | FAIS Annual Report 2012/13, two-column designed layout | 64 | 100 ppi JPEG, light-grey sans text | 84.28 | 14,474 | **0.4104** | 0.4166 |

¹ Stage 1's own metric: `pdfcheck.text_metrics`, letter runs, and the ~110-word `COMMON` set.
² The median over native-text English documents of that `doc_type` in `sources.jsonl`.

126 pages took 342 s of CPU time, about 2.7 s a page. The 3,089 pages of the full image-only set
would take about 2.3 h, run sequentially on this machine.

## The three gate criteria

| criterion | threshold | measured | verdict |
|---|---|---|---|
| mean `common_word_rate` | ≥ 0.20 | **0.4735** (0.4104–0.5144) | pass |
| every amount and date on two checked pages correct | 100% | determination page **5/5**; annual-report page **9/12** (amounts 7/10, dates 2/2) | **FAIL** |
| page word count vs manual count | within 10% | **278 OCR vs 279 manual (−0.4%)** | pass |

**About the 28–36% reference in the brief.** Stage 1's `common_word_rate` does not put clean
digital text there. Clean native English in this corpus has a median of **0.42–0.51**,
depending on document type (FAIS determinations 0.464, NFO determinations 0.509, FAIS annual
reports 0.417, NFO digests 0.479). The 28–36% band probably comes from a different denominator,
whitespace tokens rather than letter runs. So the 0.20 threshold is very permissive on this
metric. The stronger test is that **each OCR'd document lands inside the native range for its own
type**, and all five do. The word-level metric cannot see digit errors, and that is where the
gate failed.

### How the two checked pages were chosen

The rule was fixed before I looked at any page image: **the page with the most amounts and dates
among the determinations** (they are 169 of the 185), and **the page with the most amounts and
dates in the non-determination document**. Ties were broken by page order.

**Page A: `fais-det-78abea9da08d` p.6** (2005, typed, Times). Correct against the image:
2 amounts (`R261, 00`, `R563 500, 00`; the odd spacing is printed that way) and 3 dates
(`30 September 2004`, `1 April 2005`, `12 July 2005`, the last split across a line).
**5/5.** Other numbers on the page went wrong: the superscript ordinals are garbled ("1st
Respondent" came out as `1%`, `1` and `1*`, and "2nd" as `2*!`), and the paragraph number `[18]`
came out as `(18]`. These are not amounts or dates, but they matter for Stage 3: the ordinal is
what tells the 1st and 2nd respondents apart.

**Page B: `fais-ar-2012-13` p.15** (designed two-column layout). Against the image, the 2 dates
are right (`26th October 2007`, `23rd October 2007`), and 7 of the 10 rand amounts are right.
The wrong ones:

| printed | OCR | effect |
|---|---|---|
| `R67 494.53` | `R67 494,53` | decimal point became a comma (same value in SA style, but not verbatim) |
| `R3 000.00` | `k3 000,00` | currency marker lost; an amount search misses it |
| `R20 000.00` | `R20 D00.00` | a digit lost |

A held-out page, p.20, which I checked after the gate, has the same failure:
`R50 000.00` came out as `RS0 000.00` twice (confirmed against the image).

### Word count (page A)

I counted the words in the page image by eye, line by line. A word was a whitespace-separated
token with at least one letter or digit, and the paragraph numbers, `R261,` / `00` and the page
number each counted. The OCR text was counted the same way. **Manual 279, OCR 278.** The one
missing word is the page number `5`. Caveat: the four party names on the page were masked
before I viewed it. Each mask is one OCR word box, so those four words count as one each in both
counts.

## Why it fails, and what it is not

- **It is the document class, not Tesseract in general.** The determinations are typed at
  10–12 pt in black and scanned at 100–200 ppi, and they OCR cleanly. Across all four
  determination-type sample documents, **21 of 22 currency tokens are right**. The one miss is a
  footnote marker set straight after an amount: `R800 000⁴` came out as `R800 0004`, which a
  parser would read as a different number. The annual report has light-grey ~9 pt sans text in a
  100 ppi JPEG, and Tesseract confuses `5/S`, `0/D` and `R/k` in it.
- **Preprocessing does not fix the annual report.** I tried five variants on p.15 and on the
  held-out p.20: 400 dpi, 600 dpi, autocontrast at 300 and at 400 dpi, and a binarised 300 dpi.
  None is clean on both pages. 400 dpi fixed p.15 but still gave `RS0 000.00` on p.20. 600 dpi
  was worse (`R3O0 000`, `R3I0 000`). Binarising cleaned up p.15 but dropped three amounts from
  p.20 entirely.
- **Confidence does not catch it.** The annual report's 84.28 is lower than the determinations'
  ~90, but the wrong digits sit in words with ordinary confidence. A per-document threshold would
  not have flagged them.
- **The sample under-represents the non-determination class.** Only one of its 16 documents was
  sampled. The other 15 are 13 NFO digests (six one-page 2005 press clippings, Briefcase
  newsletters, seminar papers), the FAIS Annual Report 2018/19 and the NFO-side OLTI financial
  statements 2023. Their quality is unmeasured.

## The OCR set is bigger than 185

Stage 1 called a PDF image-only when `pdftotext` gave fewer than 20 words. That rule misses
scans whose text layer is just a watermark, and documents where most pages are images. See
`notes/text-quality.md` §1–2. Four more documents should join the OCR set, which brings it to
**189**:

- `fais-det-15c2696c4e68`: its only text is a PDF-XChange trial watermark on every page.
- `nfo-8202`, `nfo-11308`, `nfo-3146`: 83–94% of pages are images of text.

Separately, **six 2025 FAIS determinations** each have one embedded image page holding 138–271
words, and those pages need page-level OCR.

## Decision needed (not taken here)

1. **Recommended: split by class.** Bulk-OCR the 169 determination-type scans (159 FAIS
   determinations, 3 FAIS recommendations, 7 NFO determinations), plus the watermark-only FAIS
   determination and the six single image pages in the 2025 determinations, with exactly this
   Tesseract setup. Their sample passed every criterion. Promote
   that output to `text/final` with `text_source: ocr`. Record two known hazards for Stage 3:
   superscript ordinals, and footnote markers fused to amounts. For the 16 designed documents and
   the 3 mostly-image NFO files, either use a vision model or keep the Tesseract text for search only,
   flagged as unreliable for amounts and never used as a figures source. Stage 5 transcribes
   figures with two independent extractions anyway.
2. Tesseract for all 185, with a per-document flag. This is the fastest option, but on dense
   annual-report pages roughly 1 amount in 3 is wrong.
3. A vision model for everything. The sample does not justify the cost for typed determinations.
