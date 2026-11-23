# `rules_cited` — the model proposes, the text verifies (decision index, Stage 3, v2)

**Rule.** The extractor asks the model for every provision of a known instrument that the document
cites, each with the words that cite it (copied from the text). A proposal is **kept only if**:

1. those words occur verbatim in the (masked) document the model saw, and contain no mask token;
2. they contain the provision's number and every sub-part: "section 8(1)(a)" needs `8`, `(1)` and `(a)`;
3. the instrument is named in those words or earlier in the document ("the Code", "General Code of
   Conduct", "FAIS Act" …; the aliases are in `scripts/extract_decisions.py`, `ALIASES`);
4. the instrument is on the list (the schema pattern) and the section number is in its real range.

Everything else is **dropped and counted** (`rules_proposed`, `rules_dropped` per record, the reason in
`local/decisions-progress.jsonl`). A regex pass over the text is merged in; it is verbatim by
construction. `scripts/check_decisions.py` re-verifies every stored entry with its own code; the gate
is zero unverified entries.

**What this guarantees and what it does not.** It guarantees that the text *contains* the number near a
section keyword, with the instrument named earlier. It does not prove the number belongs to that
instrument: "section 8" in a paragraph about the Code and "section 8" of the FAIS Act are both found.
Precision is therefore checked by hand on the sample, below.

## Recall and precision, measured (Sonnet 5.5 gate, 20 documents, 2026-11-23)

Full detail and every miss: `notes/decision-sample.md` §5.

| | NFO (9 documents) | FAIS (11 documents) |
|---|---|---|
| entries kept | 4 | 104 |
| **wrong, or not supported by the text** | **0** | **0** |
| model proposed | 3 | 100 |
| of those, dropped by the text check | 1 (`instrument_not_named`) | 10 (all `instrument_not_named`) |
| entries only the model found | 1 | 26 |
| entries only the regex found | 2 | 14 |
| documents whose in-list citations are all captured | **8 of 9** | **10 of 11** |
| documents where the regex alone was complete | 8 of 9 | 5 of 11 |

- **The model proposal is what makes FAIS complete.** FAIS determinations discuss the General Code
  under a heading, with the instrument named once before a list of section numbers, which the regex
  cannot attach. Alone, the regex found a complete list for 5 of 11; with the model, 10 of 11. For NFO
  the regex is nearly enough, because case reports rarely cite a section.
- **The 11 proposals dropped are `instrument_not_named`.** Ten of them are captions cut off before the
  instrument ("SECTION 28(1) OF THE FINANCIAL ADVISORY AND", the model's 100-character limit), and the
  regex finds the same provision anyway, so they cost nothing. One is a real loss: `nfo-fd-50`'s
  "Rule 3.2.5", where the text never names the NFO's rules.
- **Misses, both documents of 20:** that Rule 3.2.5 (instrument unnamed, dropped by design), and a
  "Section 7(1)" cross-reference inside a quoted provision (`fais-d-9a74e28e5f71`).
- **Outside the instrument list, so correctly absent:** a group scheme's own rules, a policy's
  "clause 5.2", the Inspection of Financial Institutions Act, the Financial Institutions (Protection of
  Funds) Act, Board Notice 104. If the full run shows these are common, the list grows.
- **Rules added by the gate.** (1) A regex "Rule N.N" in an NFO document needs the instrument named at or
  before it, and "our Rule" names the NFO's own rules. (2) A model proposal whose citing words name a
  *different* instrument is dropped (`cite_names_other_instrument`); one such proposal was seen, caught
  only by luck, and the rule did not fire on this sample. (3) The partial names "financial advisory and
  intermediary" and "financial sector regulation" count as naming the FAIS Act and the FSR Act.
- **The sample is small.** 108 entries over 20 documents say the method is sound, not that a 0 is the
  true error rate. The full run's `check_decisions.py` re-verifies every entry.
