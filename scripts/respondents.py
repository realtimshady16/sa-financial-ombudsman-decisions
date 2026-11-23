"""Respondent names: which ones may be published, which must be withheld.

The decision (Tim, Stage 3): **publish entities, withhold natural persons.** A sole adviser is a
person. The FAIS table names the respondents of each determination as one free-text string
("X Brokers CC and Jan Smith", "Jan Smith t/a Smith Financial Services"). This module splits that
string into parties and keeps only the ones that are demonstrably entities.

A party is an *entity* when it ends in a legal-form word, or in a business word that is not
carried by a person-like name:

  strong   (Pty) Ltd, Limited, CC, BK, Bpk, Inc, NPC, SOC, Corporation, Company, Insurers,
           Insurance, Assurance, Bank, Underwriters, Holdings, Proprietary
  weak     Brokers, Consultants, Services, Administrators, Group, Trust, Fund, Scheme,
           Association, Society, Investments, Management, Managers, Capital, Securities
           -- accepted only if the rest of the name does not look like a person's
           (an initial, a particle such as "du/van/de/von", or three or more words before the marker)

Everything else is withheld: a name with no marker ("Anna Quillfeather"), a "t/a" whose
*left* side (the legal person) is not an entity ("Peter Quillfeather t/a Quillfeather Financial
Services": the trade name of a person is still a person), and the person half of "X CC and Y".
For "X CC t/a Z" the entity is X; Z is dropped. Withholding errs one way: a false 'withheld'
costs a name, a false 'published' puts a sole trader's name on the web.

This is a heuristic with a known residual risk, not a register: a person whose surname-plus-
"Brokers" is a trade name ("Surname Brokers") passes the weak-marker screen. Stage 6 (the firm
register) is where that is closed. `python3 -I scripts/respondents.py` runs the self-test.
"""
import re

STRONG = r"(?:pty|ltd|limited|cc|bk|bpk|inc|npc|soc|corporation|company|insurers?|insurance|assurance|bank|underwriters?|holdings|proprietary)"
WEAK = r"(?:brokers?|consultants?|consulting|services|administrators?|group|trust|fund|scheme|association|society|investments?|management|managers|capital|securities)"
PARTICLE = re.compile(r"\b(?:du|van|de|der|den|von|le|la|ter|ten|di|dos|da|mc|mac)\b", re.I)
TRADING = re.compile(r"\s+(?:t/a|t\\a|ta|trading as|h/a|handelend as|obo|o/b/o|on behalf of)\s+", re.I)
SEP = re.compile(r"\s*(?:,|;|/|&|\band\b|\ben\b)\s*", re.I)
# a legal-form word that ends one party and lets us split safely after it
LEGAL_END = re.compile(r"(?:\(\s*pty\s*\)\s*\(?\s*ltd\)?|\bltd\.?|\blimited|\bcc|\bbk|\bbpk|\binc|\bnpc|\bsoc)\s*$", re.I)
TAIL_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def _words(s):
    return re.findall(r"[^\W\d_][\w'’.-]*|\d+", s)


def _tail(s):
    """Drop trailing '(FSP NO. 123)' / '(OMLACSA)' parentheticals, but not '(Pty) Ltd' itself."""
    s = s.strip(" ,.;")
    while True:
        m = TAIL_PAREN.search(s)
        if m and not re.fullmatch(r"\s*\(\s*(?:pty|ltd|proprietary)\s*\)\s*", m.group(0), re.I) \
                and not re.search(r"\(\s*pty\s*\)\s*$", s, re.I):
            s = s[:m.start()].rstrip(" ,.;")
        else:
            return s


def party_kind(part):
    """-> 'entity' | 'person' | 'unclear' for one party string (no t/a inside)."""
    s = _tail(part)
    if not s:
        return "person"
    last = re.findall(r"[^\W\d_]+\.?|\)", s)
    end = s.lower().rstrip(").")
    if re.search(r"\b" + STRONG + r"\s*\)?\s*\)?$", s, re.I) or LEGAL_END.search(s):
        return "entity"
    wm = re.search(r"\b" + WEAK + r"$", s, re.I)
    if wm:
        pre = _words(s[:wm.start()])
        if not pre:
            return "unclear"
        initial = any(re.fullmatch(r"[A-Z]\.?|[A-Z]{2,3}", w) for w in pre[:1]) and len(pre) >= 2
        if PARTICLE.search(" ".join(pre)) or initial or len(pre) >= 3:
            return "unclear"
        return "entity"
    if re.search(r"\b" + STRONG + r"\b|\b" + WEAK + r"\b", s, re.I):
        return "unclear"        # a marker word that is not at the end: "X Brokers and Jan Smith"
    return "person"


def split_parties(raw):
    """Split the table string into [(party_text, trading_as_text|None)]. A party is cut after a
    legal-form word ('... CC and Jan Smith' -> 2), never inside a name ('Luvuyo Burial and
    Consulting (PTY) LTD' stays one)."""
    s = re.sub(r"\s+", " ", raw or "").strip()
    s = re.sub(r"\s+and\s+\d+\s+others?$", "", s, flags=re.I)
    out, buf = [], s
    # cut after a legal-form word followed by a separator
    pieces, start = [], 0
    for m in re.finditer(r"(?:\(\s*pty\s*\)\s*\(?\s*ltd\)?|\bltd\.?|\blimited|\bcc|\bbk|\bbpk|\binc|\bnpc|\bsoc)"
                         r"(\s*\([^)]*\))?\s*(?:,|;|/|&|\band\b|\ben\b)\s+", s, re.I):
        pieces.append(s[start:m.end()].rstrip(" ,;/&"))
        start = m.end()
    pieces.append(s[start:])
    parts = []
    for p in pieces:
        p = re.sub(r"\s*(?:,|;|/|&|\band\b|\ben\b)\s*$", "", p.strip(), flags=re.I)
        segs = re.split(r"\s*(?:,|;)\s+", p) if TRADING.search(p) or "," in p else [p]
        for seg in segs:
            if seg.strip():
                parts.append(seg.strip())
    for seg in parts:
        m = TRADING.search(seg)
        if m and not re.match(r"\s+(?:obo|o/b/o|on behalf of)\s+", m.group(0), re.I):
            trade, rest = seg[m.end():].strip(), None
            m2 = re.search(r"\s+(?:and|&|en)\s+", trade, re.I)     # "... t/a Z and <another party>"
            if m2:
                trade, rest = trade[:m2.start()].strip(), trade[m2.end():].strip()
            out.append((seg[:m.start()].strip(), trade))
            if rest:
                out.append((rest, "~"))        # never published: only counted as "another party"
        elif m:
            out.append((seg[:m.start()].strip(), None))
        else:
            out.append((seg, None))
    return out


def classify(raw, text=None):
    """-> (party_type, [entity names as written]) ; party_type in juristic|mixed|natural|unknown|None.
    'juristic' = every party is an entity; 'natural' = no party is an entity and none even looks
    like a business; 'unknown' = no entity, but some business-looking party we refused; 'mixed'
    = at least one entity and at least one other party."""
    if not raw or not raw.strip():
        return None, []
    kinds, ents = [], []
    for left, trade in split_parties(raw):
        k = party_kind(left)
        if trade == "~":
            k = "unclear" if k == "entity" else k
        elif trade is not None and k != "entity":
            k = "person" if k == "person" else "unclear"
        kinds.append(k)
        if k == "entity":
            ents.append(_tail(left) if not re.search(r"\(\s*pty\s*\)\s*$", left, re.I) else left.strip(" ,.;"))
    if not ents and text and len(raw) >= 8:
        # the document itself calls the whole string a company: "X and Y, a company ..."
        flat = re.sub(r"\s+", " ", text)
        pat = re.escape(re.sub(r"\s+", " ", raw).strip()) + r"\W{0,3}[^.]{0,60}?(?:a company|a close corporation|a private company|incorporated in terms of)"
        if re.search(pat, flat, re.I):
            return "juristic", [re.sub(r"\s+", " ", raw).strip()]
    if ents and all(k == "entity" for k in kinds):
        return "juristic", ents
    if ents:
        return "mixed", ents
    if all(k == "person" for k in kinds):
        return "natural", []
    return "unknown", []


def canonical_name(s):
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip(" ,.;")
    s = re.sub(r"\s*&\s*", " and ", s)
    s = re.sub(r"\(\s*pty\s*\)\s*\(?\s*ltd\)?", "(Pty) Ltd", s, flags=re.I)
    s = re.sub(r"\(\s*pty\s*\)", "(Pty)", s, flags=re.I)
    s = re.sub(r"\bltd\b\.?", "Ltd", s, flags=re.I)
    s = re.sub(r"\blimited\b", "Limited", s, flags=re.I)
    s = re.sub(r"\bcc\b", "CC", s, flags=re.I)
    if s.isupper():
        s = s.title().replace("(Pty)", "(Pty)").replace(" Cc", " CC")
    return s


def public_name(raw, text=None):
    """The name to publish for a table respondent string, or None."""
    ptype, ents = classify(raw, text)
    if not ents:
        return None, ptype
    return " | ".join(dict.fromkeys(canonical_name(e) for e in ents)), ptype


if __name__ == "__main__":
    # synthetic names only: this file is committed, and no real respondent may appear in it
    cases = [
        ("Zorbex Capital (PTY) Ltd and Anna Maria Quillfeather", "mixed", ["Zorbex Capital (Pty) Ltd"]),
        ("Zorbex Capital (PTY) LTD, Anna Maria Quillfeather and John Doe", "mixed", ["Zorbex Capital (Pty) Ltd"]),
        ("ACME SOLUTIONS CC & PETER QUILLFEATHER", "mixed", ["Acme Solutions CC"]),
        ("Northwind Burial and Consulting (PTY) LTD", "juristic", ["Northwind Burial and Consulting (Pty) Ltd"]),
        ("Example Insurance Brokers PTY (LTD)", "juristic", None),
        ("Samplecorp life limited", "juristic", ["Samplecorp life Limited"]),
        ("EXAMPLE MUTUAL LIFE ASSURANCE COMPANY & SOUTH AFRICA LIMITED (EMLACSA)", "juristic", None),
        ("Fabrikam Advisory Services (PTY) LTD (FSP NO. 00000)", "juristic", None),
        ("Anna Maria Quillfeather", "natural", []),
        ("Peter Quillfeather t/a Quillfeather Financial Services", "natural", []),
        ("Peter Quillfeather ta Quillfeather Brokers", "natural", []),
        ("ANNA MARIA QUILLFEATHER BROKERS", "unknown", []),
        ("Anna du Quill Financial Services", "unknown", []),
        ("PQ van der Merwe/ Sample Plan Brokers", "unknown", []),
        ("Fabrikam Brokers and Anna Quillfeather", "unknown", []),
        ("Contoso Makelaars CC t/a The Example Group and Peter Quillfeather", "mixed", ["Contoso Makelaars CC"]),
        ("Tailspin Trading 509 CC t/a Sample Invest and Anna Quillfeather", "mixed", ["Tailspin Trading 509 CC"]),
        ("Globex Brokers", "juristic", None),
        ("XYZ Brokers", "juristic", None),
        ("Brokers", "unknown", []),
        ("Initech Wealth t/a Sample Investments and 3 Others", "natural", []),
    ]
    bad = 0
    for raw, want_t, want_e in cases:
        t, e = classify(raw)
        pub, _ = public_name(raw)
        ok = t == want_t and (want_e is None or [canonical_name(x) for x in e] == want_e)
        bad += not ok
        print("ok  " if ok else "FAIL", f"{want_t:9s} got {t:9s} pub={pub!r:50.50}  <- {raw[:60]}")
    raise SystemExit(1 if bad else 0)
