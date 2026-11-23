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

## Recall, per office (to be filled from the Sonnet 5.5 gate)

Not yet measured for the v2 prompt: see `notes/decision-sample.md` once the gate has run. The v1
baseline, from the regex alone on the same 20 documents, was **NFO 9/9 and FAIS 4/11 documents with a
complete list**; FAIS determinations discuss the Code under a heading, so a regex that needs the
instrument in the same phrase misses most of them. That gap is what the model proposal is meant to close.
