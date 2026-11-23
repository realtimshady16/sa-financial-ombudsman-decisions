# `outcome` — what the decision did (decision index, Stage 3, v1)

**Derived from the corpus.** I read the closing order of all 57 distinct NFO Final Determinations
and of ~60 FAIS determinations, with names masked. I also ran a phrase census over all 543
distinct determinations that have text (a throwaway script, not committed). For each document it
took the last "complaint/claim/matter … is/was/be … upheld/dismissed/…" phrase in the final 40%.

- **FAIS, 486 documents:** 425 matched (upheld 395, dismissed 26, rejected 2, referred 2) and 61 did not.
- **NFO, 57 documents:** only 3 matched. NFO case reports do not use the formula.

Most of the vocabulary below comes from reading the 61 FAIS misses and all the NFO endings.

**Outcome is read from the complainant's side and from the order itself.** It records what the
ombud *ordered*, not what happened afterwards. NFO case 48 is upheld even though the later claim
assessment paid nothing. When the order says one thing and the reasons another, the order wins.

## Vocabulary (7 values; `null` only when there is no usable text)

| value | definition | how it is phrased in the corpus | evidence |
|---|---|---|---|
| `upheld` | the complainant gets the relief at issue: an order to pay, to assess the claim, to reinstate, or to refund. **This includes orders that never use the word**, such as "The Respondents are hereby ordered … to pay", "The complaint succeeds", NFO "the insurer is instructed to assess the claim", "the provisional ruling is confirmed" when that ruling favoured the complainant, and a merits-only finding with quantum left to the parties | FAIS "The complaint is upheld" (395 of the 425 FAIS documents with a standard phrase); 36 of the 61 FAIS documents without one still order the respondent "to pay" or "to compensate" | `fais-det-8afe834df450`, `fais-det-1bbcbfbca013`, `fais-det-4f73dfd68d93` ("succeeds"), `fais-det-25fcc8188899` and `fais-det-a1953d1f3096` (merits upheld, quantum separated), NFO cases 5, 9, 19, 55 |
| `partly_upheld` | some of the relief is granted and some is expressly refused, or the award is expressly reduced for the complainant's own conduct (apportionment). **Not** a lower award caused by a statutory cap or by the ombud's own quantification | "partially upheld", "upheld in part", a refused head of claim | NFO case 44 (`nfo-4251`: annual medical reviews allowed, not the more frequent ones the insurer wanted, and not the permanent status the complainant wanted). Rare: the phrase census found no standard "partly upheld" phrase at all |
| `dismissed` | the complaint fails. **This includes dismissals on prescription or jurisdiction when the order says "dismissed"** | "The complaint is dismissed", "the complaint falls to be dismissed", "the claim is rejected" | `fais-det-588ea45bf3ab`; `fais-det-c79d4b6b9465` ("dismissed and be referred to Ombud for Banking Services". The order dismisses, so the value is `dismissed`, not `referred`) |
| `referred` | the ombud declines to decide the merits and sends the matter elsewhere, without dismissing it: to a court, another ombud, or s27(3)(c) | "the complaint is not finally determined … it is appropriate that this complaint be dealt with by a court"; "complainant is referred to court" | `fais-det-aabc601f3e36`, `fais-det-978faaafe118` |
| `settled` | the parties settled, and the determination records the settlement rather than deciding the dispute | "settled", "concluded a settlement" | NFO case 28 (`nfo-4249`), arguably: the insurer withdrew its appeal and settled the compensation. **Borderline**: the merits had already been decided in the complainant's favour, so a reader could call it `upheld`. Rare |
| `amendment` | the document only corrects or amends an earlier determination or recommendation, such as a wrong amount or an omitted interest order. It is not a fresh decision | "Order should read thus:", "is hereby amended as follows", "Paragraph 52 of the recommendation is therefore hereby amended" | `fais-det-500c2b2c855f`, `fais-det-4c619d36cc30`, `fais-det-5f86fb399ede`, `fais-det-9094f1c08d79` (a letter amending a recommendation) |
| `no_ruling` | the file the table links as a "Determination" contains no ruling: a chart, an annexure or a covering letter | — | `fais-det-2bc1a054c329` (a group-structure chart) |

`null` is reserved for documents with no usable text: the two PDFs truncated at the source, and
`fais-det-15c2696c4e68`, whose only text layer is a PDF-XChange watermark. That file probably does
hold a ruling, but only in the image, which is not yet OCR'd. The extractor treats any text with
`common_word_rate` < 0.10 as unusable, and it never guesses there.

## Traps the extractor must not fall into (all seen in the corpus)

1. **"Leave to appeal is granted"** is boilerplate in post-2017 FAIS orders (FSR Act s230), and is
   not an outcome. A naive "appeal … granted" match fired on 26 FAIS documents, and "leave to appeal … granted" appears in **22**.
2. **The order is not always at the end.** OCR'd FAIS determinations often end with annexures:
   application forms, fund tables, a broker's quotation. Their last "ORDER" or amount belongs to
   the annexure (`fais-det-58b7f452139d`, `fais-det-798c14d93c0c`, `fais-det-9088f9b9a712`,
   `fais-det-6cd1802935f9`, `fais-det-3b15d12210dc`).
3. **NFO case reports are retellings.** Many end with an "Outcome" or "Result" paragraph saying
   what the insurer did afterwards ("The insurer paid the claim"). That paragraph confirms the
   outcome, but it is not the order.
4. **NFO appeals invert the wording.** In case 10 (`nfo-5512`), the *insurer's* appeal failed, so
   the complaint is `upheld`. In cases 18 (`nfo-5534`) and 58 (`nfo-6787`), the *complainant's*
   appeal succeeded, so again `upheld`. Read whose appeal it is.
5. **"The insurer's decision is upheld"** would mean the complaint is dismissed. I did not see
   this phrasing in the sample, but it is the obvious inversion, and the prompt warns about it.

## What these counts cannot tell you

- **Neither office publishes a random sample of its decisions.** NFO's "Final Determinations" are
  57 case reports chosen for publication across 2009–2024, and every one I read ended in the
  complainant's favour. FAIS publishes formal determinations, which it issues mostly after a
  respondent ignored a recommendation or conciliation failed. So "% upheld" here is a property
  of what the offices choose to publish. It is not a win rate, and it must never be charted as
  one.
