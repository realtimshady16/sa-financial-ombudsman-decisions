"""Best-effort name masking for determination text, before it is shown to a person or sent to a model.

FAIS determinations name complainants in the body, and the office's own redaction (FY2024/25 on) is
incomplete (report.md §6). Stage 3 reads determinations for *words* (topic, outcome, rules), never
for who the parties are, so names can be masked before the text goes anywhere — a terminal, a
transcript, a model API. Masking is layered, and each layer catches what the one before misses:

  1. every token of every FAIS complainant and respondent string in the restricted table
     (local/fais-determination-rows.jsonl), so a known party's name is masked in *any* document,
     unless the token is everyday prose in this corpus (seen 50+ times in lower case: "Policy");
  2. any capitalised token right after an honorific (Mr, Mrs, Ms, Miss, Dr, Adv, Prof, Pastor ...);
  3. any capitalised token whose lower-case form is not attested in lower case somewhere in the
     corpus's own text (names are almost never written in lower case) and is not on the domain
     allowlist (FAIS, FSP, Ombud, the main insurers ...);
  4. street addresses and postal boxes ("36 Something Road", "P O Box 41"), and SA identity
     numbers (13 digits). This last layer is applied at every level, light included.

An English dictionary is deliberately *not* used for layer 3: cracklib-small carries thousands of
first names (Gloria, Stefan, Warren...). Layer 3 masks some firm names and some rare capitalised
words too; for FAIS that costs nothing, because the respondent comes from the official table, not
from the text. It is still best-effort: a surname that is also everyday prose ("Brown", "Storm")
passes layer 3 and is caught only if it is in the table. Treat masked text as *less* identifying,
not as anonymous.

    python3 -I scripts/redact.py DOC_ID [--pages 1-3]   # print masked text/final/<DOC_ID>.txt
"""
import json
import os
import re
import sys
from collections import Counter
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = os.path.join(ROOT, "local", "fais-determination-rows.jsonl")
FINAL = os.path.join(ROOT, "text", "final")
MASK = "[X]"
LOWER_MIN = 8          # a word must occur this often in lower case to count as prose

HONORIFICS = r"(?:Mr|Mrs|Ms|Miss|Dr|Adv|Advocate|Prof|Mnr|Mev|Mej|Pastor|Rev|Judge|Ds)\.?"
# Domain words that are capitalised, rare in lower case, and carry no personal information.
ALLOW = set("""
FAIS FSP FSPs FSB FSCA FSOS FSR NFO OLTI OBS OSTI CO PFA SARB CIPC JSE NCR NCA LISP LISPs PHI
Ombud Ombudsman Ombud's Ombudsman's Ombuds Respondent Respondents Complainant Complainants
Complainant's Respondent's Ltd Pty CC Bpk Inc NPC RF SA Act Acts Code Codes Rules Rule Board
Sanlam Hollard Liberty Momentum Discovery Metropolitan Assupol Absa Nedbank Capitec FNB PPS
Coronation Investec Stanlib Glacier Sygnia BrightRock Clientele Avbob Santam Outsurance
Telesure Guardrisk Zurich Old Mutual PSG Sharemax Picvest Realcor Regulations Regulation Section
Schedule Annexure Part Chapter Paragraph Clause Policy Contract Determination Recommendation
January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday South Africa African Pretoria
Johannesburg Cape Town Durban Gauteng KwaZulu Natal Limpopo Mpumalanga Free State Western
Eastern Northern Province Republic Rand ZAR Pension Funds Fund Long Short Term Tribunal Appeal
Registrar Minister Court High Supreme Constitutional Magistrate's Practice Note Adjudicator
""".split())
STREET = (r"(?:Street|Str|Road|Rd|Avenue|Ave|Crescent|Drive|Lane|Close|Way|Place|Boulevard|"
          r"Laan|Straat|Weg|Rylaan|Singel|Park|Estate|Village|Gardens|Court|Square|Ridge|Glen|Hill)")
# SA identity numbers (13 digits: YYMMDD SSSS C A Z), possibly spaced; plus passport-style runs
# after "identity/ID/passport number". Found in an OCR'd FAIS determination in the Stage 3 sample.
IDNUM = re.compile(r"\b\d{6}\s?\d{4}\s?\d{2}\s?\d\b"
                   r"|(?i:\b(?:identity|id|passport)\s+(?:number|no\.?)\s*:?\s*)[A-Z0-9]{6,}")
ADDRESS = re.compile(r"\b\d{1,5}[A-Za-z]?,?\s+(?:[A-Z][\w'’-]*\s+){1,3}" + STREET + r"\b"
                     r"|\bP\.?\s?O\.?\s?Box\s+\d+|\bPrivate\s+Bag\s+X?\d+|\bStand\s+[A-Z]?\d+")


@lru_cache(maxsize=1)
def party_tokens():
    """Lower-cased tokens (>= 3 letters) from every FAIS complainant/respondent string. Local data;
    never printed."""
    toks = set()
    if os.path.exists(ROWS):
        for line in open(ROWS, encoding="utf-8"):
            r = json.loads(line)
            for k in ("complainant", "respondent"):
                for t in re.findall(r"[^\W\d_]+", r.get(k) or ""):
                    if len(t) >= 3:
                        toks.add(t.lower())
    return frozenset(toks)


@lru_cache(maxsize=1)
def lowercase_vocab():
    """How often each word occurs *in lower case* across all of text/final. A word written in
    lower case is prose; names essentially never are."""
    vocab = Counter()
    if os.path.isdir(FINAL):
        for fn in os.listdir(FINAL):
            with open(os.path.join(FINAL, fn), encoding="utf-8", errors="replace") as f:
                vocab.update(re.findall(r"(?<![\w'’])[a-z]{3,}(?![\w])", f.read()))
    return vocab


TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
HON = re.compile(r"\b" + HONORIFICS + r"\s+((?:[A-Z]\.?\s*){0,3}[A-Z][^\W\d_]+)")


def mask(text, extra=(), level="full"):
    """Return text with likely personal names and addresses replaced by [X]. `extra` adds strings
    to mask everywhere (e.g. this document's own complainant string from the table).

    level="full" applies all four layers (FAIS text). level="light" applies only the honorific and
    address layers (2 and 4) plus `extra`: for NFO determinations, which the office writes with
    initials ("Ms B", "Mr N") and whose insurer names (Liberty, Hollard...) are also FAIS respondent
    tokens and must survive for the respondent field."""
    low = lowercase_vocab()
    for s in extra:
        for t in re.findall(r"[^\W\d_]+", s or ""):
            # this document's own parties, in any case -- except firm words that are everyday prose
            # ("Insurance", "Company", "Financial") and the allowlist ("South", "Africa")
            if len(t) >= 3 and low.get(t.lower(), 0) < 300 and t.capitalize() not in ALLOW \
                    and t not in ALLOW:
                text = re.sub(r"(?<![^\W\d_])" + re.escape(t) + r"(?![^\W\d_])", MASK, text,
                              flags=re.I)
    text = IDNUM.sub(MASK, text)
    text = ADDRESS.sub(MASK, text)
    text = HON.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + MASK, text)
    if level == "light":
        return text
    party = party_tokens()

    def one(m):
        w = m.group(0)
        base = re.sub(r"['’]s$", "", w)
        lw = base.lower()
        if not base[:1].isupper():
            return w                      # names are capitalised; a lower-case word is prose
        n = low.get(lw, 0)
        if base in ALLOW or base.capitalize() in ALLOW or len(base) <= 2:
            return w
        if lw in party and n < 50:        # a known party token, unless it is everyday prose
            return MASK
        if base.isupper() and len(base) <= 4 and n < LOWER_MIN:
            return w                      # an acronym (ABSA, NW, GP); never a whole surname here
        return w if n >= LOWER_MIN else MASK

    return TOKEN.sub(one, text)


def pages(text):
    """Split text/final into pages on form feeds (pdftotext and ocr.py both emit \\f)."""
    return text.split("\f")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    doc = argv[0]
    rng = None
    if "--pages" in argv:
        a, _, b = argv[argv.index("--pages") + 1].partition("-")
        rng = (int(a), int(b or a))
    text = open(os.path.join(FINAL, doc + ".txt"), encoding="utf-8").read()
    ps = pages(text)
    for i, p in enumerate(ps, 1):
        if rng and not (rng[0] <= i <= rng[1]):
            continue
        print(f"===== page {i}/{len(ps)} =====")
        print(mask(p))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
