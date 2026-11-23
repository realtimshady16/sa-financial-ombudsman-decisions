# Outcome labels, hand-checked — and two times I was wrong about being wrong

**Date:** 2026-11-23
**Scope:** the 51 records whose outcome is not `upheld`, plus the 12 with no outcome. The gate
(`notes/decision-sample.md`) had only ever seen `upheld` cases, so this was the one field whose
reliability had never been tested.

## Method

For each record: pull the ruling region of the source text (the `ORDER` section for FAIS, the
`Order`/`Final Determination`/`Outcome` sections for NFO), mask it, and read it against the label.
Excerpts, not full documents — which is the source of both errors below.

## Result

**FAIS: 43 of 43 consistent.** Dismissed records all carry "the complaint is dismissed" (often with
the case fee ordered against the respondent — that does not make it upheld); the six `amendment`
records are genuine corrections of a prior order ("Order should read thus", "the amount of
R79 607,65 is hereby substituted"); both `referred` records say the complaint is not determined and
belongs in a court; the single `settled` record is an offer accepted; the single FAIS
`partly_upheld` awards the complainant 70% of her loss, which is exactly what the label claims.

**NFO `partly_upheld`: 8 checked, 5 correct, 3 corrected to `upheld`.**

| record | before | after | why |
|---|---|---|---|
| `nfo-fd-4` | partly_upheld | **upheld** | "provisional ruling … confirmed in toto … instructed to comply" — a full remedy |
| `nfo-fd-34` | partly_upheld | **upheld** | "SDM was directed to pay the claim amount of R31 500,00 less the premiums paid" |
| `nfo-fd-42` | partly_upheld | **upheld** | insurer instructed to refund the premium difference plus interest — the remedy sought |
| `nfo-fd-20`, `-29`, `-36` | partly_upheld | unchanged | compensation ordered where the main complaint failed; partial remedy, correctly labelled |

The three corrections are marked `outcome_hand_verified` and their `field_sources.outcome` is `hand`,
so a later re-extraction that disagrees is visibly a disagreement rather than an overwrite.

## Two corrections to my own reading, both from the same cause

**1. I first judged 6 of the 8 NFO labels wrong, including `nfo-fd-20` as `dismissed`.** Then I read
the whole ruling: Liberty Life's right to cancel *was* upheld, **and** R2 000 compensation was
ordered to each complainant. Partial remedy — `partly_upheld` was right. My error was reading the
sentence about the insurer's right and stopping there.

**2. I first judged the four `no_ruling` records to be mislabelled "unreadable text" cases.** Checked
properly, none of the four contains the word "dismissed" or "upheld" anywhere, and they run to 555,
1 213, 4 265 and 20 362 words at word-rates of 0.24–0.44. They are readable documents with **no
ruling in them** — the label is exactly right. I had inferred "unreadable" from one bad excerpt.

Both errors are the same failure: **an excerpt is not the document.** It is the same shape as the
vehicle thread's parser mistake recorded on 2026-11-23 — *a tool's failure is evidence about the tool
first.*

## What this does and does not establish

It establishes that the outcome field is not systematically biased in the non-upheld direction, which
was the real risk: a model that over-labels `upheld` would have been invisible in a sample of upheld
cases.

It does not establish inter-annotator reliability. One reader (me) with the ruling text; no second
annotator, no blind re-read. The `nfo-fd-20`/`-29`/`-36` group shows why that matters: those three are
`partly_upheld` under a "partial remedy" rule and `upheld` under a "complainant got something" rule,
and the corpus does not yet state which rule it uses. That belongs in `codebook/outcomes.md`.
