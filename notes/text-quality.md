# Text quality after Stage 2 — the residual defect surface

Computed from `text_manifest.jsonl` (2026-11-22). `common_word_rate` is Stage 1's metric
(`pdfcheck.text_metrics`), measured on `text/final/<doc_id>.txt`. **Floor: 0.20**, the gate's
number. Clean native English text sits much higher: the median is 0.42–0.51 depending on
`doc_type` (see `notes/ocr-sample.md`). So the floor catches only text that is plainly not
English prose, and §2 and §3 list what it cannot see.

## Summary

| | documents |
|---|---|
| text in `text/final`, at or above the floor | 721 |
| text in `text/final`, **below the floor** | **28**: 26 non-English by design, **2 real** |
| text present, above the floor, but mostly image pages (need OCR) | **3** |
| text present, but one embedded image page holds text (page-level OCR) | **6** |
| **no text in `text/final`**: image-only, OCR gated | **185** |
| no text: PDF truncated at the source | 2 |
| no text: HTML-only page, not extracted in Stage 2 | 68 (not a defect) |

**The honest residual right now is 191 PDFs without usable text:** 185 gated + the watermark-only
determination in §1 + 3 mostly-image files in §2 = **189 for OCR**, and 2 that cannot be recovered.
On top of that come **6 single pages** inside recent FAIS determinations. Once the pending OCR
decision is made and carried out, the residual would be **1 real defect (the chart in §1) + 2
truncated files**, plus whatever the OCR itself gets wrong (see `notes/ocr-sample.md`).

## 1. Below the floor, with text in `text/final` (28)

**Not English, so the metric does not apply (26).** These are FAIS newsletters in other SA
languages. Their text is intact native text, and the census `language` tag explains the low
rate. They are not defects.
`fais-nl-16-isindebele`, `fais-nl-16-sepedi`, `fais-nl-16-siswati`, `fais-nl-issue-10-isixhosa`,
`fais-nl-issue-10-sepedi`, `fais-nl-issue-10-sesotho`, `fais-nl-issue-11-isindevele`,
`fais-nl-issue-11-siswati`, `fais-nl-issue-12-isixhosa`, `fais-nl-issue-12-sesotho`,
`fais-nl-issue-12-zulu`, `fais-nl-issue-13-afrikaans`, `fais-nl-issue-13-setswana`,
`fais-nl-issue-13-venda`, `fais-nl-issue-14-isixhosa`, `fais-nl-issue-14-isizulu`,
`fais-nl-issue-14-xitsonga`, `fais-nl-issue-15-isizulu`, `fais-nl-issue-15-setswana`,
`fais-nl-issue-15-tshivenda`, `fais-nl-issue-17-afrikaans`, `fais-nl-issue-17-sesotho`,
`fais-nl-issue-17-xitsonga`, `fais-nl-issue-9-isizulu`, `fais-nl-issue-9-setswana`,
`fais-nl-issue-9-tshivenda`.

**Real (2):**

- `fais-det-15c2696c4e68`, rate 0.000. A 13-page FAIS determination from 2006, scanned at
  300 ppi. Its only text layer is a PDF-XChange trial watermark repeated on every page, so
  Stage 1's "< 20 words = image-only" rule missed it. **Needs OCR.**
- `fais-det-2bc1a054c329`, rate 0.092. A one-page group-structure chart (company names in boxes),
  dated 2007, that the FAIS table links as the "Determination". The low rate reflects the content,
  not damage. The ruling's text is not in this file. **Stage 3 should check that row's other
  links before recording an outcome.**

## 2. Above the floor, but text hidden in images

The page-level test is "pages with fewer than 10 words in the text layer". For each candidate I
then OCR'd sample pages at 200 dpi to see whether the image actually holds text.

**Mostly image pages (3): should join the OCR set.** These documents clear the floor on their
few text pages and hide everything else. On each sampled page the text layer has 0 words and
the visible text runs to 155–637 words:

- `nfo-8202`: NFO Financial Statements 2024. 61 of 65 pages near-empty.
- `nfo-11308`: NFO Financial Statements 2025, in a DocuSign envelope. 70 of 75 pages
  near-empty.
- `nfo-3146`: Briefcase, 2nd quarter 2015. 10 of 12 pages near-empty.

**One embedded image page that holds text (6): page-level OCR.** `fais-det-0b57feb5bc19`,
`fais-det-170de4935c92`, `fais-det-5fced554b462`, `fais-det-cf6db343bfa5`,
`fais-det-d8f54f31c416` and `fais-det-df08d4efe364` are all FAIS determinations from
2025. Each has one page that is a single image. When OCR'd, those pages carry 138–271 words
and 29–42 numbers each (all six checked), which looks like a pasted schedule or table. These are
typed documents, the class that passed the gate. **Stage 3 must not read amounts from these six
until that page is OCR'd.**

**Not a defect:** `nfo-4341-1` (a 2004 slide deck). Its near-empty pages really are near-empty:
OCR finds 4–12 words, the same as its text layer. 174 near-empty pages carrying a page-size
image across 69 native documents are mostly covers, photo spreads and section dividers. Four
sampled annual-report pages gave 0–2 visible words. In total, 121 native documents have at least
one near-empty page (434 pages), and apart from the files above, none is more than 33%
near-empty.

## 3. Low but explained (0.20–0.30), no action

- `nfo-12607`, 0.251: NFO Trend Report Jan–Jun 2026, which is mostly tables and chart labels.
- `nfo-1644`, 0.282: Credit Ombud Annual Report 2018, which is dominated by tables.
- `nfo-4341-1`, 0.239: a 2004 slide deck with very little text per slide (§2).
- `nfo-4353-3`, 0.282: a 3-page 2004 workshop handout in slide-style bullets.
- `nfo-5978`, 0.204: OSTI Summary of Income and Expenditure 2023, a one-page Excel table.

## 4. No text in `text/final`

- **185 image-only PDFs, held back by the OCR gate.** The 5 sample documents are OCR'd in
  `text/ocr/` but not promoted. 180 are not yet run. Decision pending: `notes/ocr-sample.md`.
- **2 PDFs truncated at the source:** `fais-det-49487d5ae2b3` and `fais-det-806bc34b15b5`. Both
  end mid-object, with no trailer and no catalog. qpdf recovery fails. The first still holds 13
  page objects, so a hand-rebuilt page tree might salvage some pages. I did not attempt that.
  Re-fetching would not help, because the server sends exactly these bytes (Stage 1 §7).
- **68 HTML-only pages** (44 NFO doc pages, 24 FAIS case studies, all digests). Their text is in
  `html/` and is outside the Stage 2 brief. Extracting the main content is a small, separate job.

## Repaired and converted files

All of them clear the floor. Cases 56, 57 and 58 score 0.54, 0.47 and 0.48. Note that they also
scored 0.47–0.54 *before* repair: this metric cannot see ligature damage, which is why the repair
has its own checks (`text/repair/<id>.json`, `scripts/check_text.py`). The 8 converted legacy
files score 0.38–0.54.
