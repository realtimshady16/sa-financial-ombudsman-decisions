"""Stage 3: the decisions index. One structured, name-free, citable record per determination.

    python3 -I scripts/extract_decisions.py --make-sample          # draw the 20-document sample
    python3 -I scripts/extract_decisions.py --sample               # extract the sample's records
    python3 -I scripts/extract_decisions.py --queue codebook/queue-decisions.jsonl [--limit N]
    python3 -I scripts/extract_decisions.py DOC_ID [DOC_ID ...]    # specific documents
    python3 -I scripts/extract_decisions.py --make-queue           # everything not in the sample
    python3 -I scripts/extract_decisions.py --publish-only         # rebuild decisions.public.jsonl
      options: --force (re-extract even if a record exists)  --model PROVIDER/ID  --dry-run
               --reprocess (rebuild records from the saved model replies in local/extract/:
                            no model call; for when a rule changes)

Unit of work: one census document (doc_type == determination). Its decision is one record per
*distinct file*: byte-identical copies (7 pairs: 3 NFO packages that duplicate a case page, 4 FAIS
files linked from two table rows) resolve to one decision_id, listed in `duplicate_doc_ids`.

Where each field comes from — and the rule that binds them: **no number is ever read from OCR or
HTML text**. Determinations are read for words.

  office, division, doc_id, text_source, citation_*  census + text_manifest (deterministic)
  year, date, fiscal_year, product_line             FAIS: the official table; NFO: the title
  respondent_*                                     FAIS: the official table; NFO: the model, kept
                                                   only if the string is found in the text
  respondent_public                                the entity names only (scripts/respondents.py);
                                                   null for a natural person. respondent_raw and
                                                   respondent_canonical stay local
  rules_cited                                      the model PROPOSES (instrument, provision and the
                                                   verbatim words citing it); the text VERIFIES: kept
                                                   only if those words are in the document, carry the
                                                   provision's number, and the instrument is named at
                                                   or before them. Unverifiable proposals are dropped
                                                   and counted. A regex pass over the text is added
                                                   (verbatim by construction)
  outcome                                          model, cross-checked by a rule over the order
  topic_defence, topic_conduct                     model, two axes, each constrained to its own
                                                   vocabulary in codebook/topics.md
  page_anchor                                      the page where the model's verbatim outcome
                                                   quote is actually found

Text goes to the model *masked* (scripts/redact.py): FAIS bodies name complainants.

Resumable and idempotent: a decision_id that already has a record is skipped. A record is
appended, flushed, then **re-read, parsed and schema-validated** before the document is logged as
done in local/decisions-progress.jsonl; a write that cannot be read back stops the run with an
error. Nothing is ever logged as done that is not on disk.
"""
import hashlib
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from redact import mask  # noqa: E402
import respondents  # noqa: E402

import jsonschema  # noqa: E402

VERSION = "extract_decisions/2.0"
DEFAULT_MODEL = "anthropic/claude-sonnet-5-5"
LOCAL_OUT = os.path.join(ROOT, "decisions.jsonl")             # gitignored: restricted fields
PUBLIC_OUT = os.path.join(ROOT, "decisions.public.jsonl")     # committed
PROGRESS = os.path.join(ROOT, "local", "decisions-progress.jsonl")
WORK = os.path.join(ROOT, "local", "extract")                 # masked model inputs + raw replies
SAMPLE = os.path.join(ROOT, "codebook", "sample-decisions.jsonl")
QUEUE = os.path.join(ROOT, "codebook", "queue-decisions.jsonl")
SCHEMA = os.path.join(ROOT, "schema", "decision.schema.json")
FAIS_LIST = "https://www.faisombud.co.za/determinations/"
MIN_GAP_S = 2.0          # rate limit between model calls (sequential anyway)

DEFENCE = {   # axis 1: the insurer's (or product provider's) reason in a dispute over a claim or policy decision
    "claim_not_paid": "a claim was not paid or paid late with no specific contractual defence in dispute (plain non-payment, insurer-binder dispute, unpaid funeral claims)",
    "non_disclosure": "claim declined or policy avoided because the insured did not disclose or misrepresented information at application",
    "exclusion_clause": "claim declined under an exclusion: pre-existing condition, suicide, a named exclusion, or risk materialised before cover",
    "late_notification": "claim or notice lodged outside a contractual time limit; whether the lateness can be condoned",
    "policy_interpretation": "what the policy wording means: definitions (dependant, cousin, extended family, insurable interest), commencement, waiting period, benefit calculation, overlapping cover",
    "disability_assessment": "whether the insured meets the disability/incapacity definition (own or alternative occupation); termination, review or level of disability/income benefits",
    "lapse_and_cancellation": "the policy or cover on a life lapsed, was cancelled or terminated, or reinstatement was refused",
    "service_and_compensation": "poor service, administrative error or delay; compensation for distress or inconvenience; interest on late payment",
    "beneficiary_and_cession": "who is entitled to the money: beneficiary nominations, cession, payment to the wrong person",
    "other": "an insurer's defence or a claim/policy dispute that fits none of the above",
}
CONDUCT = {   # axis 2: what the adviser / intermediary / provider did wrong, as the ombud found it
    "advice_suitability": "advice not appropriate to the client's needs, circumstances or risk tolerance; no proper needs analysis or explanation of risk; includes replacement advice (cash in A, buy B), and an adviser who sold a scheme in which he or his firm had a conflicting interest or ran it, when the finding is about the advice and not about money taken",
    "misappropriation_fraud": "the ombud FINDS that the provider/representative took, diverted or never invested the client's money, or ran a fraudulent or fictitious scheme. Running or having an interest in a scheme is not enough on its own: there must be a finding of taking, diversion or fraud",
    "unlicensed_provider": "the respondent rendered financial services or carried on insurance business without a licence/registration, and the finding turns on that; typically premiums collected, claims never paid",
    "mandate_breach": "acted without, beyond or contrary to the client's instructions, or failed to carry out instructions in time (unauthorised switches, surrenders, paid-up, cover removed or kept)",
    "fees_and_charges": "the core complaint is undisclosed, excessive or wrongly levied costs, commission or penalties",
    "intermediary_cover_failure": "a broker/intermediary failed to arrange, renew, update or correctly specify cover (incl. under-insurance), so a claim failed or was reduced",
    "sale_disclosure": "at the point of sale the product's nature, terms or conditions were misrepresented or not disclosed; the question is what was agreed (no consensus, accidental cover sold as life cover, a condition never mentioned), not suitability of advice",
    "other": "provider or intermediary conduct that fits none of the above",
}
TOPICS = {**DEFENCE, **CONDUCT}   # kept for callers that want every term
OUTCOMES = {
    "upheld": "the complainant gets the relief at issue — an order to pay/compensate/assess the claim/reinstate/refund — even if the word 'upheld' is never used; includes a merits-only finding with quantum left to the parties",
    "partly_upheld": "some relief granted and some expressly refused, or the award expressly reduced for the complainant's own conduct (not merely capped)",
    "dismissed": "the complaint fails, including dismissal on prescription or jurisdiction when the order says dismissed",
    "referred": "the ombud declines to decide the merits and sends the matter to a court or another body without dismissing it",
    "settled": "the parties settled and the document records the settlement instead of deciding",
    "amendment": "the document only corrects or amends an earlier determination or recommendation",
    "no_ruling": "the file contains no ruling at all (a chart, annexure or covering letter)",
}

INSTRUMENTS_LIST = ("FAIS Act, General Code, FSOS Act, FSR Act, LTIA, STIA, PPR, FAIS Ombud Rules, "
                    "OLTI Rules, Prescription Act, CPA, NCA, PFA, CISCA, Companies Act, Insurance Act, MSA")

SYSTEM = """You index South African financial-ombud determinations for a research dataset. You read
one determination (its text, with personal names replaced by [X]) and return ONE JSON object, nothing
else. You classify words only. Never invent text; quote exactly.

Return exactly these keys:
{"is_ruling": true|false,
 "outcome": <one outcome value>,
 "outcome_quote": "<the sentence(s) in the text that state the outcome, copied character for character, at most 300 characters>",
 "topic_defence": <one DEFENCE value, or null>,
 "topic_conduct": <one CONDUCT value, or null>,
 "rules_cited": [ {"instrument": <one instrument label>, "kind": "s"|"r", "number": "<e.g. 8(1)(a)>", "cite": "<the words in the text that cite it, copied character for character, at most 100 characters, including the number>"} , ...],
 "respondent_name": "<NFO only: the insurer's name exactly as written in the text, or null if it is not named; FAIS: null>",
 "certainty": "high"|"medium"|"low",
 "doubt": "<at most 25 words on anything that made this hard, or empty>"}

OUTCOME values (read from the complainant's side, from what the ombud ORDERED):
""" + "\n".join(f"- {k}: {v}" for k, v in OUTCOMES.items()) + """

Outcome traps:
- "leave to appeal is granted" is boilerplate, never the outcome.
- The order is usually just before "DATED AT ..."; OCR'd files often end with annexures (forms, tables) after it.
- NFO case reports end with an "Outcome"/"Result" paragraph on what the insurer did later; the outcome is what the ombud decided.
- Read whose appeal it is: the insurer's appeal failing means the complaint is upheld.
- "The insurer's decision is upheld/confirmed" means the complaint is dismissed.

TWO TOPIC AXES. Fill each one on its own; either may be null, both may be filled.
topic_defence = what the INSURER'S side said in a dispute over a claim or a policy decision, and what the ombud
rules on. null when no insurer decision is in dispute (a pure adviser-misconduct case).
DEFENCE values:
""" + "\n".join(f"- {k}: {v}" for k, v in DEFENCE.items()) + """

topic_conduct = what the ADVISER, BROKER or PROVIDER did wrong, as the ombud found it. null when no conduct
finding is made (an insurer-decision case with nothing wrong found on the intermediary's side).
CONDUCT values:
""" + "\n".join(f"- {k}: {v}" for k, v in CONDUCT.items()) + """

Conduct precedence when several fit: misappropriation_fraud only on a finding that money was taken,
diverted, never invested, or the scheme was fraudulent or fictitious; then unlicensed_provider; then the
issue the finding actually turns on. If the document has no ruling (outcome amendment or no_ruling), both
topics are null.

rules_cited: list the provisions of these instruments that the document cites, each as it is cited:
""" + INSTRUMENTS_LIST + """.
Use "kind" "s" for a section/clause/paragraph of an Act or the Code, "r" for a numbered rule. "number" is the
section number with its sub-parts as written, no spaces: "8(1)(a)", "3(1)(b)", "28(1)". "cite" is
copied from the text exactly, including the number; it need not name the instrument. A provision whose
instrument is not in the list is omitted. A section you only infer, or that is not written in the text, is
omitted. At most 40 entries; one entry per distinct provision.
"""
PROMPT_SHA = hashlib.sha256(SYSTEM.encode()).hexdigest()
INSTRUCTION = ("The file above is one determination. Page breaks are marked '=== page N ==='. "
               "Return the JSON object only.")


# ----------------------------------------------------------------------------- data

def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load():
    census = jl(os.path.join(ROOT, "sources.jsonl"))
    manifest = {m["doc_id"]: m for m in jl(os.path.join(ROOT, "text_manifest.jsonl"))}
    rows = {r["row_index"]: r for r in jl(os.path.join(ROOT, "local", "fais-determination-rows.jsonl"))}
    return census, manifest, rows


def plan(census):
    """Map every determination doc_id to its decision: (decision_id, canonical doc_id, duplicates)."""
    det = [r for r in census if r["doc_type"] == "determination"]
    by_sha = defaultdict(list)
    for r in det:
        by_sha[r["sha256"]].append(r)
    out = {}
    for group in by_sha.values():
        def rank(r):  # NFO: prefer the per-case doc page over a yearly package; then doc_id
            has_case = bool(re.search(r"Case\s+\d+", r.get("title") or ""))
            return (0 if has_case else 1, r["doc_id"])
        group = sorted(group, key=rank)
        canon = group[0]
        if canon["office"] == "NFO":
            m = re.search(r"Case\s+(\d+)", canon.get("title") or "")
            if not m:
                raise SystemExit(f"no case number for NFO determination {canon['doc_id']}")
            did = f"nfo-fd-{int(m.group(1))}"
        else:
            did = "fais-d-" + canon["doc_id"][len("fais-det-"):]
        dups = [r["doc_id"] for r in group[1:]]
        for r in group:
            out[r["doc_id"]] = (did, canon["doc_id"], dups)
    return out


# ----------------------------------------------------------------------------- D1 citation

GENERIC_FILENAME_TOKENS = {
    "fais", "det", "determination", "determinations", "redacted", "final", "case", "no", "nr",
    "v", "vs", "and", "en", "pdf", "signed", "amended", "amendment", "recommendation", "ruling",
    "the", "of", "gp", "wc", "kzn", "ec", "fs", "lp", "mp", "nw", "nc", "kz", "ltd", "pty", "cc"}


def filename_is_name_free(filename):
    """D1: a FAIS filename may be linked directly only if every letter run in it is a generic
    word (case-numbered files). Conservative by construction: one unknown token means 'hash'."""
    stem = re.sub(r"\.pdf$", "", filename or "", flags=re.I)
    toks = re.findall(r"[^\W\d_]+", stem)
    return bool(toks) and all(t.lower() in GENERIC_FILENAME_TOKENS for t in toks) or not toks


def citation(r, rows):
    if r["office"] == "NFO":
        return "direct", r["url"]
    names = [f["filename"] for i in r.get("listing_row_indices") or [] for f in rows[i]["files"]
             if f["filename_sha256"] == r["filename_sha256"]]
    if names and all(filename_is_name_free(n) for n in names):
        return "direct", r["fetch_url"]
    return "hash", FAIS_LIST


# ----------------------------------------------------------------------------- respondent

canonical_name = respondents.canonical_name


# ----------------------------------------------------------------------------- rules cited

INSTRUMENTS = [  # (regex on the instrument name, canonical label); order matters (longest first)
    (r"general code(?: of conduct)?(?: for authori[sz]ed financial services? providers(?: and representatives)?)?|(?:the )?code\b", "General Code"),
    (r"financial advisory and intermediary services act|fais act", "FAIS Act"),
    (r"financial services? ombud schemes act|fsos act", "FSOS Act"),
    (r"financial sector regulation act|fsr act|fsra\b", "FSR Act"),
    (r"long[- ]term insurance act|ltia\b", "LTIA"),
    (r"short[- ]term insurance act|stia\b", "STIA"),
    (r"policyholder protection rules|\bppr\b", "PPR"),
    (r"rules on proceedings(?: of (?:this|the) office)?(?: of the ombud(?: for financial services providers)?)?", "FAIS Ombud Rules"),
    (r"prescription act", "Prescription Act"),
    (r"consumer protection act|\bcpa\b", "CPA"),
    (r"national credit act|\bnca\b", "NCA"),
    (r"pension funds act", "PFA"),
    (r"collective investment schemes control act|cisca\b", "CISCA"),
    (r"companies act", "Companies Act"),
    (r"medical schemes act", "MSA"),
    (r"insurance act", "Insurance Act"),
]
INSTR_RE = "|".join(f"(?:{p})" for p, _ in INSTRUMENTS)
_PAR = r"\(\s*[0-9a-z]{1,4}\s*\)"
_ONE = r"\d{1,3}[A-Z]?(?:\s*" + _PAR + r")*(?:\s*(?:,|and|or|to)\s*" + _PAR + r")*"
# "section 8(1)(c) of the Code"; enumerations "sections 7, 8, 9 and 11 of the General Code";
# sibling paragraphs "section 8 (1) (a), (b) and (c) of The Code"
SECTION = re.compile(
    r"\b(sections?|sec\.|ss?\.?|rules?)\s*(" + _ONE + r"(?:\s*(?:,|and|or|&)\s*" + _ONE + r")*)"
    r"\s+(?:of|in terms of|under)\s+(?:the\s+)?(" + INSTR_RE + r"|act\b|rules\b)", re.I)


def _expand(listing):
    """'8 (1) (a), (b) and (c)' -> ['8(1)(a)', '8(1)(b)', '8(1)(c)']; '7, 8 and 11' -> ['7','8','11'].
    A range yields its two ends: '(a) to (d)' -> (a), (d) -- what is literally in the text."""
    out, cur = [], None
    rng = False      # "(a) to (d)" yields (a) and (d) only: a letter in between is not in the text
    for tok in re.findall(r"\d{1,3}[A-Z]?|\(\s*[0-9a-z]{1,4}\s*\)|,|\band\b|\bor\b|\bto\b|&", listing, re.I):
        if tok.lower() == "to":
            rng, sep = True, True
            continue
        if re.fullmatch(r"\d{1,3}[A-Z]?", tok):
            if cur:
                out.append(cur)
            cur, sep = [tok.upper(), []], False
        elif tok.startswith("("):
            par = "(" + re.sub(r"[\s()]", "", tok).lower() + ")"
            if cur is None:
                continue
            if sep and cur[1]:      # a sibling: same depth as the last paragraph
                out.append(cur)
                cur = [cur[0], cur[1][:-1] + [par]]
            else:
                cur[1].append(par)
            rng = sep = False
        else:
            sep = True
    if cur:
        out.append(cur)
    return [n + "".join(ps) for n, ps in out]
RULE = re.compile(r"\brules?\s+(\d{1,2}[A-Z]?(?:\.\d{1,3}[A-Z]?){1,4}(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*)", re.I)
MAX_SECTION = {"FAIS Act": 51, "General Code": 20, "FSOS Act": 20, "LTIA": 80, "STIA": 80,
               "FSR Act": 300, "Prescription Act": 25}


def _label(instr, office):
    low = instr.lower()
    for p, lab in INSTRUMENTS:
        if re.fullmatch(p, low, re.I):
            return lab
    if low == "act":
        return "FAIS Act" if office == "FAIS" else None    # FAIS defines 'the Act' in every caption
    if low == "rules":
        return "FAIS Ombud Rules" if office == "FAIS" else "OLTI Rules"
    return None


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}
SIGNED = re.compile(r"DATED\s+(?:AT\s+\w+\s+)?(?:ON\s+)?(?:THIS\s+)?(?:THE\s+)?(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
                    r"(?:DAY\s+)?(?:OF\s+)?([A-Za-z]+),?\s+((?:19|20)\d\d)", re.I)


def signed_date(text):
    """ISO date of the last 'DATED AT ... <day> <Month> <year>' line, or None. Native text only."""
    t = re.sub(r"\s+", " ", text)
    for m in reversed(list(SIGNED.finditer(t))):
        mon = MONTHS.get(m.group(2).lower())
        if mon:
            try:
                return datetime(int(m.group(3)), mon, int(m.group(1))).strftime("%Y-%m-%d")
            except ValueError:
                return None
    return None


def _add_days(iso, n):
    from datetime import timedelta
    return (datetime.strptime(iso, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def rules_cited(text, office):
    t = re.sub(r"\s+", " ", text)
    found, flags = [], set()
    for m in SECTION.finditer(t):
        lab = _label(m.group(3), office)
        if not lab:
            continue
        kind = "r" if m.group(1).lower().startswith("rule") else "s"
        if kind == "r" and lab not in ("FAIS Ombud Rules", "OLTI Rules", "PPR"):
            continue
        for one in _expand(m.group(2)):
            n = int(re.match(r"\d+", one).group(0))
            if lab in MAX_SECTION and not (1 <= n <= MAX_SECTION[lab]):
                flags.add("rule_out_of_range")
                continue
            found.append(f"{lab} {kind}{one}")
    for m in RULE.finditer(t):
        after = t[m.end(): m.end() + 60].lower()
        lab = "PPR" if "policyholder protection" in after or re.match(r"\d+[A-Z]\.", m.group(1)) \
            else ("OLTI Rules" if office == "NFO" else None)
        if not lab:
            continue
        # the instrument must be named in the text at or before the rule (the same test the model's
        # proposals pass). An NFO document that says "Rule 3.2.5" and never says "Rules" does not
        # name its instrument, so the entry is not verifiable and is not emitted.
        if not re.search(ALIASES[lab], t[: m.end() + 60], re.I):
            continue
        num = re.sub(r"[ ]+", "", m.group(1))
        num = re.sub(r"\([0-9a-zA-Z]{1,4}\)", lambda x: x.group(0).lower(), num)
        # the dotted part is "2A.8.1": the letter after a number is a capital (the RULE regex is
        # case-insensitive, so "rule 2a.8" would otherwise yield a lower-case twin of "2A.8")
        num = re.sub(r"(?<=\d)[a-z](?=\.|\(|$)", lambda x: x.group(0).upper(), num)
        found.append(f"{lab} r{num}")
    seen, out = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out, flags


# ----------------------------------------------------------------------------- rules: model proposes, text verifies

ALIASES = {   # an instrument counts as "named" if one of these occurs in the document at or before the citing words
    "General Code": r"general code|\bthe code\b|\bcode of conduct\b|\bcode\b",
    "FAIS Act": r"fais act|financial advisory and intermediary|\bthe act\b",
    "FSOS Act": r"fsos act|ombud schemes act",
    "FSR Act": r"fsr act|fsra\b|financial sector regulation",
    "LTIA": r"ltia\b|long[- ]term insurance act",
    "STIA": r"stia\b|short[- ]term insurance act",
    "PPR": r"\bppr\b|policyholder protection",
    "FAIS Ombud Rules": r"rules on proceedings|\brules\b",
    "OLTI Rules": r"\brules\b|\bolti\b|\bour rules?\b",
    "Prescription Act": r"prescription act",
    "CPA": r"consumer protection act|\bcpa\b",
    "NCA": r"national credit act|\bnca\b",
    "PFA": r"pension funds act",
    "CISCA": r"collective investment schemes|cisca\b",
    "Companies Act": r"companies act",
    "Insurance Act": r"insurance act",
    "MSA": r"medical schemes act|\bmsa\b",
}
FULL_NAMES = {   # an instrument written out in full: if the citing words carry one, they cannot belong to another
    "General Code": r"general code of conduct",
    "FAIS Act": r"fais act|financial advisory and intermediary",
    "FSOS Act": r"fsos act|ombud schemes",
    "FSR Act": r"fsr act|financial sector regulation",
    "LTIA": r"ltia\b|long[- ]term insurance act",
    "STIA": r"stia\b|short[- ]term insurance act",
    "PPR": r"policyholder protection rules",
    "Prescription Act": r"prescription act",
    "CPA": r"consumer protection act",
    "NCA": r"national credit act",
    "PFA": r"pension funds act",
    "Companies Act": r"companies act",
    "MSA": r"medical schemes act",
}
RULE_KINDS = {"FAIS Ombud Rules", "OLTI Rules", "PPR"}        # instruments whose provisions are "rules"
_PARENS = re.compile(r"\(\s*([0-9a-z]{1,4})\s*\)")
_NUM = re.compile(r"^(\d{1,3}[a-z]?(?:\.\d{1,3}[a-z]?)*)((?:\([0-9a-z]{1,4}\))*)$")


def _flat(s):
    return _PARENS.sub(r"(\1)", _norm(s))


def verify_rule_proposals(props, mpages):
    """props: the model's rules_cited list. -> (kept_cites, n_proposed, n_dropped, reasons Counter).
    A proposal is kept only if (1) its `cite` words occur verbatim in the (masked) text the model saw,
    without a mask token; (2) the provision's section number and every sub-part appear in those words;
    (3) the instrument is named at or before them (in the words or earlier in the document); (4) the
    instrument is one we know and the section number is in the real range. Nothing else is kept,
    and every drop is counted."""
    flat = _flat(" ".join(mpages))
    kept, reasons, n = [], Counter(), 0
    if not isinstance(props, list):
        return [], 0, 0, reasons
    for pr in props[:60]:
        n += 1
        if not isinstance(pr, dict):
            reasons["malformed"] += 1
            continue
        lab, kind = pr.get("instrument"), (pr.get("kind") or "").lower()
        num = _PARENS.sub(r"(\1)", re.sub(r"\s+", "", str(pr.get("number") or "")).lower())
        num = re.sub(r"^(?:s|r|section|rule)\.?", "", num)
        cite = _flat(str(pr.get("cite") or "")).strip(' ."')
        if lab not in ALIASES:
            reasons["instrument_unknown"] += 1
            continue
        if kind not in ("s", "r") or (lab not in RULE_KINDS and kind == "r"):
            reasons["kind"] += 1
            continue
        m = _NUM.match(num)
        if not m:
            reasons["number_malformed"] += 1
            continue
        base, subs = m.group(1), re.findall(r"\([0-9a-z]{1,4}\)", m.group(2))
        if lab in MAX_SECTION and kind == "s" and not (1 <= int(re.match(r"\d+", base).group(0)) <= MAX_SECTION[lab]):
            reasons["out_of_range"] += 1
            continue
        if len(cite) < 4 or "[x]" in cite:
            reasons["cite_empty_or_masked"] += 1
            continue
        pos = flat.find(cite)
        if pos < 0:
            reasons["cite_not_in_text"] += 1
            continue
        if not re.search(r"(?<![\d.])" + re.escape(base) + r"(?!\d|\.\d)", cite) or any(x not in cite for x in subs):
            reasons["number_not_in_cite"] += 1
            continue
        if not re.search(ALIASES[lab], flat[: pos + len(cite)]):
            reasons["instrument_not_named"] += 1
            continue
        if any(re.search(pat, cite) for other, pat in FULL_NAMES.items() if other != lab) \
                and not re.search(FULL_NAMES.get(lab, r"(?!)"), cite):
            reasons["cite_names_other_instrument"] += 1     # "SECTION 28(1) OF THE FINANCIAL ADVISORY ..." filed under Ombud Rules
            continue
        # a letter after a digit in the dotted number is a capital ("2A.8"), at any depth, not only last
        kept.append(f"{lab} {kind}{re.sub(r'(?<=\d)[a-z]', lambda x: x.group(0).upper(), base)}{''.join(subs)}")
    return list(dict.fromkeys(kept)), n, sum(reasons.values()), reasons


def _sort_key(c):
    lab, _, rest = c.rpartition(" ")
    m = re.match(r"[sr](\d+)", rest)
    return (lab, int(m.group(1)) if m else 0, rest)


# ----------------------------------------------------------------------------- rule outcome

STD = re.compile(r"(?:complaints?|claims?|matter)\s+(?:against [\w ]{1,40}?\s+)?(?:is|are|was|were|must be|"
                 r"should be|be|is hereby|are hereby|stands? to be|falls? to be)\s+"
                 r"(?:(partially|partly|in part)\s+|(?:hereby|accordingly|therefore|thus|consequently|only)\s+)?"
                 r"(upheld|dismissed|rejected|not upheld|succeeds?|referred)", re.I)
AMEND = re.compile(r"order should read thus|(?:is|are) hereby amended|amended as follows|hereby amend|"
                   r"corrigendum|should read as follows", re.I)
PAY = re.compile(r"ordered[^.]{0,160}?to (?:pay|compensate|refund|reimburse)|"
                 r"(?:respondents?|insurer) (?:is|are) (?:hereby )?(?:ordered|directed|instructed) to", re.I)
REFER = re.compile(r"not finally determined|be dealt with by a court|referred to (?:a |the )?court", re.I)
DATED = re.compile(r"\bDATED\s+(?:AT|THIS|ON)\b|\bDated at\b|\bSigned at\b", re.I)
NFO_UP = re.compile(r"instructed to (?:pay|assess|reinstate|refund|comply|calculate)|directed to (?:pay|assess)|"
                    r"(?:should|must) (?:now )?(?:assess|pay|admit|reinstate|refund)|"
                    r"provisional (?:ruling|determination)[^.]{0,80}?(?:confirmed|made final|became final|has become final|upheld)|"
                    r"(?:complaint|appeal) (?:should be|is|was) upheld|condoned|cannot repudiate|not justified|"
                    r"failed to discharge the onus|ordered to (?:pay|refund)|has to pay|"
                    r"compensat\w+ (?:of|amount)|appeal cannot succeed", re.I)
NFO_DOWN = re.compile(r"(?:complaint|claim) (?:is|was) (?:dismissed|not upheld|rejected)|"
                      r"insurer'?s? (?:decision|repudiation) (?:is|was) (?:upheld|confirmed|justified|correct)|"
                      r"unable to (?:assist|uphold)", re.I)


def rule_outcome(pages, office):
    """A deliberately simple cross-check of the model, never the final word.
    -> (value|None, page|None)"""
    flat, offs = "", []
    for i, p in enumerate(pages, 1):
        offs.append((len(flat), i))
        flat += re.sub(r"\s+", " ", p) + " "

    def page_of(pos):
        pg = 1
        for o, i in offs:
            if o <= pos:
                pg = i
        return pg

    if len(pages) <= 3 and AMEND.search(flat):
        return "amendment", page_of(AMEND.search(flat).start())
    if office == "FAIS":
        ds = [m.start() for m in DATED.finditer(flat)]
        end = ds[-1] if ds else len(flat)
        # the determination's own DATED line, not an annexure's: last one in the body
        start = max(0, end - 3500)
        win = flat[start:end]
        o = max(win.rfind("ORDER"), win.rfind("Order"))
        seg = win[o:] if o >= 0 else win
        base = start + (o if o >= 0 else 0)
        segs = [m for m in STD.finditer(seg) if "appeal" not in seg[max(0, m.start() - 30):m.start()].lower()]
        if segs:
            m = segs[0]
            word = m.group(2).lower()
            val = {"upheld": "upheld", "succeeds": "upheld", "succeed": "upheld", "dismissed": "dismissed",
                   "rejected": "dismissed", "not upheld": "dismissed", "referred": "referred"}[word]
            if m.group(1) and val == "upheld":
                val = "partly_upheld"
            return val, page_of(base + m.start())
        if REFER.search(seg):
            return "referred", page_of(base + REFER.search(seg).start())
        if PAY.search(seg):
            return "upheld", page_of(base + PAY.search(seg).start())
        return None, None
    tail_start = int(len(flat) * 0.55)
    tail = flat[tail_start:]
    up, down = list(NFO_UP.finditer(tail)), list(NFO_DOWN.finditer(tail))
    if up and not down:
        return "upheld", page_of(tail_start + up[-1].start())
    if down and not up:
        return "dismissed", page_of(tail_start + down[-1].start())
    return None, None


# ----------------------------------------------------------------------------- model

def _norm(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐‑‒–—]", "-", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def anchor(quote, pages):
    """1-based page where the quote occurs (whitespace/quote-insensitive). When it occurs on
    several pages, the LAST one wins: NFO reports restate the provisional ruling before the final
    one, in the same words. If the whole quote is not found, its first and last 60 characters are
    tried; if those land on different pages the model stitched two passages together, and the
    suffix (the later, operative part) is used. -> (page|None, how)"""
    if not quote:
        return None, "no_quote"
    q = _norm(quote).strip(' ."')
    np_ = [_norm(p) for p in pages]
    full = [i for i, p in enumerate(np_, 1) if q and q in p]
    if full:
        return full[-1], "exact"
    pre = [i for i, p in enumerate(np_, 1) if len(q) >= 60 and q[:60] in p]
    suf = [i for i, p in enumerate(np_, 1) if len(q) >= 60 and q[-60:] in p]
    if pre and suf and pre[-1] != suf[-1]:
        return suf[-1], "stitched"
    if suf:
        return suf[-1], "suffix"
    if pre:
        return pre[-1], "prefix"
    joined = " ".join(np_)          # a quote may straddle a page break
    if q and q in joined:
        pos, acc = joined.rfind(q), 0
        for i, p in enumerate(np_, 1):
            acc += len(p) + 1
            if acc > pos:
                return i, "straddle"
    return None, "not_found"


_last_call = [0.0]


def _runner_for(model):
    """Two doors to the same model, and they use different credentials.

    `pi -p --model anthropic/*` uses pi's own OAuth in ~/.pi/agent/auth.json.
    `claude -p --model claude-*` uses the Claude Code CLI's sign-in, which is also what T3's
    claudeAgent provider uses. When one expires the other still works, so the runner follows the
    model name: claude-* goes through the CLI, anything else through pi.
    """
    return "claude" if str(model).startswith("claude") else "pi"


def call_model(model, input_path, retries=2):
    """One document per call, through pi or the Claude Code CLI (see _runner_for).
    -> (parsed_json|None, meta)"""
    runner = _runner_for(model)
    meta = {"model": model, "runner": runner, "attempts": 0}
    if runner == "claude":
        with open(input_path, encoding="utf-8") as f:
            prompt = INSTRUCTION + "\n\n--- DOCUMENT ---\n\n" + f.read()
        # A lean invocation: the extraction prompt is the whole system prompt, no tools, no skills,
        # no MCP servers, no settings or project context files, no saved session. The default CLI
        # carries ~30k tokens of its own prompt and tool definitions per call: measured on one
        # document, 34.8k input tokens and $0.145 against 5.8k and $0.026, with an identical answer.
        cmd = [os.environ.get("CLAUDE_BIN", "claude"), "-p", "--model", model,
               "--output-format", "json", "--tools", "", "--system-prompt", SYSTEM,
               "--disable-slash-commands", "--strict-mcp-config", "--setting-sources", "",
               "--no-session-persistence"]
        stdin_text = prompt
    else:
        cmd = [os.environ.get("PI_BIN", "pi"), "-p", "--mode", "json", "--no-tools",
               "--no-session", "--no-context-files", "--no-skills", "--no-extensions",
               "--no-mcp", "--no-prompt-templates", "--no-themes",
               "--model", model, "--system-prompt", SYSTEM, "@" + input_path, INSTRUCTION]
        stdin_text = ""

    for attempt in range(retries + 1):
        gap = time.time() - _last_call[0]
        if gap < MIN_GAP_S:
            time.sleep(MIN_GAP_S - gap)
        _last_call[0] = time.time()
        meta["attempts"] = attempt + 1
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=WORK,
                               input=stdin_text)
        except subprocess.TimeoutExpired:
            meta["error"] = "timeout"
            continue

        reply, usage = None, None
        if runner == "claude":
            try:
                ev = json.loads(p.stdout or "{}")
            except ValueError:
                meta["error"] = f"unparseable runner output (rc={p.returncode}): {p.stdout[-300:]}"
                continue
            if ev.get("is_error"):
                err = str(ev.get("result") or "")[:300]
                meta["error"] = f"runner error: {err}"
                # A usage/credential limit is not a document problem: retrying the same document
                # 500 times writes 500 empty records and calls it progress. Surface it and stop.
                fatal = bool(ev.get("api_error")) and ev.get("api_error_status") in (401, 403, 429)
                if fatal or "usage_limit" in err or "limit" in err.lower():
                    meta["fatal"] = f"{ev.get('api_error') or 'runner'}: {err}"
                    return None, meta
                continue
            reply = ev.get("result")
            usage = ev.get("usage")
            meta["cost_usd"] = ev.get("total_cost_usd")
            meta["duration_ms"] = ev.get("duration_ms")
            mu = ev.get("modelUsage") or {}
            if mu:
                # The CLI may run a small internal step on a cheap model and the real work on the
                # one asked for; record the requested model when present, else the biggest
                # output-token consumer. Never "whichever key came first" — that labelled a
                # Sonnet extraction as haiku.
                def _out(v):
                    return (v or {}).get("outputTokens") or (v or {}).get("output_tokens") or 0
                meta["model_reported"] = model if model in mu else max(mu, key=lambda k: _out(mu.get(k)))
                meta["models_all"] = sorted(mu)
            meta["stop"] = ev.get("stop_reason")
        else:
            for line in p.stdout.splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") == "message_end" and ev.get("message", {}).get("role") == "assistant":
                    msg = ev["message"]
                    reply = "".join(c.get("text", "") for c in msg.get("content", [])
                                    if c.get("type") == "text")
                    usage = msg.get("usage")
                    meta["model_reported"] = f"{msg.get('provider')}/{msg.get('model')}"
                    meta["stop"] = msg.get("stopReason")

        meta["usage"] = usage
        meta["returncode"] = p.returncode
        if reply is None:
            meta["error"] = f"no assistant message (rc={p.returncode}): {p.stderr[-300:]}"
            continue
        txt = reply.strip()
        txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            # strict=False: the model copies line breaks from the text into 'cite' strings, and a raw
            # newline inside a JSON string is rejected by the default parser (3 of the first 20
            # calls needed a retry for exactly that)
            return json.loads(m.group(0) if m else txt, strict=False), meta
        except (ValueError, AttributeError):
            meta["error"] = "unparseable reply"
            meta["raw_reply"] = reply[:2000]
    return None, meta


# ----------------------------------------------------------------------------- one document

def read_text(doc_id):
    p = os.path.join(ROOT, "text", "final", doc_id + ".txt")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def extract(doc_id, census_by_id, manifest, rows, mapping, model, dry_run=False, reprocess=False):
    r = census_by_id[doc_id]
    did, canon_id, dups = mapping[doc_id]
    r = census_by_id[canon_id]
    m = manifest[canon_id]
    office = r["office"]
    flags, fsrc = set(), {}
    t0 = time.time()

    rec = {"decision_id": did, "schema_version": "decision/1", "office": office,
           "division": r.get("division"), "kind": "determination", "doc_id": canon_id,
           "duplicate_doc_ids": dups}

    # ---- deterministic: dates, product line, citation, respondent (FAIS)
    trows = [rows[i] for i in (r.get("listing_row_indices") or [])]
    if office == "FAIS":
        dates = sorted({x["date_raw"] for x in trows if re.fullmatch(r"\d{8}", x.get("date_raw") or "")})
        rec["date"] = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]}" if dates else None
        rec["year"] = r.get("year") if r.get("year") else (int(dates[0][:4]) if dates else None)
        fys = sorted({x["fiscal_year"] for x in trows if x.get("fiscal_year")})
        rec["fiscal_year"] = fys[0] if fys else None
        cats = sorted({x["category"] for x in trows if x.get("category")})
        rec["product_line"] = " | ".join(cats) or None
        fsrc.update(year="fais_table", date="fais_table", product_line="fais_table")
        if len(trows) > 1:
            flags.add("file_serves_two_table_rows")
        resp = " | ".join(dict.fromkeys(x["respondent"].strip() for x in trows if x.get("respondent")))
        rec["respondent_raw"] = resp or None
        rec["respondent_canonical"] = canonical_name(resp) if resp else None
        rec["respondent_public"], rec["respondent_party_type"] = respondents.public_name(resp)   # refined against the text below
        rec["respondent_source"] = "fais_table" if resp else None
        fsrc["respondent"] = "fais_table"
    else:
        rec["date"] = None
        rec["year"] = r.get("year")
        rec["fiscal_year"] = None
        rec["product_line"] = "Long-term"
        fsrc.update(year="census_title", product_line="division")
    pol, url = citation(r, rows)
    rec["citation_policy"], rec["citation_url"] = pol, url
    rec["filename_sha256"] = r.get("filename_sha256")
    rec["text_source"] = m["text_source"]
    rec["restricted_fields"] = ["respondent_raw", "respondent_canonical", "outcome_quote"]

    text = read_text(canon_id)
    cwr = m.get("common_word_rate")
    usable = bool(text) and m["text_source"] != "none" and (cwr is None or cwr >= 0.10)
    if m["text_source"] in ("ocr", "html"):
        flags.add("words_only_text")
    if m.get("notes") and "page-level OCR" in m["notes"]:
        flags.add("image_page_not_ocrd")

    if not usable:
        flags.add("no_usable_text")
        if office == "FAIS":
            rec["listed_date"] = rec.get("date")
        rec.update(topic_defence=None, topic_conduct=None, outcome=None, rules_cited=[], rules_proposed=None,
                   rules_dropped=None, page_anchor=None, outcome_quote=None, extraction_method="none", extraction_model=None,
                   extraction_confidence="low", prompt_sha256=None)
        if office == "NFO":
            rec.update(respondent_raw=None, respondent_canonical=None, respondent_public=None,
                       respondent_party_type=None, respondent_source=None)
        if rec.get("year") is None and office == "FAIS":
            flags.add("year_unknown")
        return finish(rec, flags, fsrc, t0, {"model": None})

    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]

    # ---- rules cited, part 1: regex over the unmasked text (verbatim by construction; the model's
    # verified proposals are added below)
    rc, rflags = rules_cited(text, office)
    flags |= rflags

    if office == "FAIS" and rec.get("respondent_raw"):
        rec["respondent_public"], rec["respondent_party_type"] = respondents.public_name(rec["respondent_raw"], text)

    # ---- FAIS date: the official table's date is the *listing* date. In 301 of 321 native files
    # it equals the signed date, but a January 2021 bulk listing carries decisions signed in
    # 2019-2020. For native text, prefer the signed date (last "DATED ... <d> <Month> <yyyy>"),
    # unless it falls after the listing (then it belongs to an appended document). OCR/HTML text
    # is never read for digits, so those keep the table date.
    if office == "FAIS":
        rec["listed_date"] = rec.get("date")
        signed = signed_date(text) if m["text_source"] in ("native", "repaired", "converted") else None
        if signed and rec["listed_date"] and signed > _add_days(rec["listed_date"], 31):
            flags.add("signed_date_after_listing")
            signed = None
        if signed:
            if rec["listed_date"] and signed != rec["listed_date"]:
                flags.add("listed_date_differs")
            rec["date"], rec["year"] = signed, int(signed[:4])
            fsrc.update(year="native_signed_date", date="native_signed_date")
        elif m["text_source"] in ("ocr", "html"):
            flags.add("date_from_table_only")
        if rec["year"] and rec.get("fiscal_year"):
            a0 = int(rec["fiscal_year"][:4])
            if rec["date"] and not (f"{a0}-04-01" <= rec["date"] <= f"{a0 + 1}-03-31"):
                flags.add("fiscal_year_differs")

    # ---- year fallback: native text only (never OCR/HTML: no numbers from those)
    if rec.get("year") is None:
        if m["text_source"] in ("native", "repaired", "converted"):
            ys = re.findall(r"DATED[^\n]{0,80}?\b((?:19|20)\d\d)\b", text, re.I)
            if ys:
                rec["year"] = int(ys[-1])
                fsrc["year"] = "native_text_dated_line"
                flags.add("year_from_text")
        if rec.get("year") is None:
            flags.add("year_unknown")

    # ---- rule outcome (cross-check)
    r_out, r_page = rule_outcome(pages, office)

    # ---- model: masked text, one document per call
    extra = [x.get("complainant") for x in trows] + [x.get("respondent") for x in trows]
    level = "full" if office == "FAIS" else "light"
    mpages = [mask(p, extra=extra, level=level) for p in pages]
    os.makedirs(WORK, exist_ok=True)
    inp = os.path.join(WORK, canon_id + ".input.txt")
    with open(inp, "w", encoding="utf-8") as f:
        for i, p in enumerate(mpages, 1):
            f.write(f"=== page {i} ===\n{p}\n")
    if dry_run:
        return None
    reply_path = os.path.join(WORK, canon_id + ".reply.json")
    if reprocess:
        # deterministic re-run of everything except the model: same saved reply, current rules
        if not os.path.exists(reply_path):
            raise RuntimeError(f"{canon_id}: --reprocess needs {reply_path}")
        saved = json.load(open(reply_path, encoding="utf-8"))
        ans, meta = saved["answer"], dict(saved["meta"], reprocessed=True)
    else:
        ans, meta = call_model(model, inp)
        with open(reply_path, "w", encoding="utf-8") as f:
            json.dump({"answer": ans, "meta": meta}, f, ensure_ascii=False, indent=1)
    if meta.get("fatal"):
        raise SystemExit(f"extraction aborted: {meta['fatal']}\n"
                         f"  no record written for {canon_id}; records already on disk are kept and the run resumes")
    rec["extraction_model"] = meta.get("model_reported") or model
    rec["prompt_sha256"] = PROMPT_SHA

    if not isinstance(ans, dict) and meta.get("error") and not meta.get("raw_reply"):
        # No answer at all — transport down, timeout, or a limit that slipped through. That is not a
        # finding about the document, so write nothing and stop; the run resumes and retries it.
        # (A *bad* answer — unparseable but present — still becomes a flagged record; it is evidence.)
        try:
            os.remove(reply_path)
        except OSError:
            pass
        raise SystemExit(f"extraction deferred: no model answer for {canon_id} after "
                         f"{meta.get('attempts')} attempt(s): {meta['error']}\n"
                         f"  no record written; the run resumes and retries this document")
    if not isinstance(ans, dict):
        flags.add("model_invalid")
        ans = {}
    m_out = ans.get("outcome") if ans.get("outcome") in OUTCOMES else None
    m_def = ans.get("topic_defence") if ans.get("topic_defence") in DEFENCE else None
    m_con = ans.get("topic_conduct") if ans.get("topic_conduct") in CONDUCT else None
    if ans and ans.get("outcome") is not None and m_out is None:
        flags.add("model_outcome_off_vocab")
    if ans and ((ans.get("topic_defence") is not None and m_def is None)
                or (ans.get("topic_conduct") is not None and m_con is None)):
        flags.add("model_topic_off_vocab")
    if m_out in ("amendment", "no_ruling"):
        m_def, m_con = None, None
    elif ans and m_out and m_def is None and m_con is None:
        flags.add("no_topic_assigned")
    quote = (ans.get("outcome_quote") or "").strip()[:400] or None
    page, how = anchor(quote, mpages)
    if page is None:
        flags.add("quote_not_anchored")
    elif how == "stitched":
        flags.add("quote_stitched")
    elif how != "exact":
        flags.add(f"quote_anchored_{how}")
    if ans.get("certainty") == "low":
        flags.add("model_unsure")

    # outcome: the model decides; the rule only cross-checks
    if r_out is None:
        flags.add("rule_silent")
    elif m_out is not None and r_out != m_out:
        flags.add("rule_model_disagree")
    rec["outcome"] = m_out
    rec["topic_defence"] = m_def
    rec["topic_conduct"] = m_con
    mc, n_prop, n_drop, why = verify_rule_proposals(ans.get("rules_cited"), mpages)
    rec["rules_cited"] = sorted(set(rc) | set(mc), key=_sort_key)
    rec["rules_proposed"], rec["rules_dropped"] = n_prop, n_drop
    meta["rules_dropped_why"] = dict(why)
    meta["rules_model_only"] = sorted(set(mc) - set(rc))
    meta["rules_regex_only"] = sorted(set(rc) - set(mc))
    if n_drop:
        flags.add("rules_proposal_dropped")
    rec["outcome_quote"] = quote
    rec["page_anchor"] = page if page is not None else (r_page if r_out == m_out else None)
    if page is None and rec["page_anchor"] is not None:
        flags.add("page_from_rule")
    fsrc.update(outcome="model+rule_check", topic_defence="model", topic_conduct="model",
                rules_cited="model_proposed_text_verified+regex", page_anchor="anchored_quote")

    # ---- NFO respondent: the model's string, kept only if it is in the text
    if office == "NFO":
        name = (ans.get("respondent_name") or "").strip() or None
        if name and _norm(name) in _norm(text):
            rec["respondent_raw"] = name
            rec["respondent_canonical"] = canonical_name(name)
            rec["respondent_public"] = canonical_name(name)
            # the NFO's jurisdiction is over subscribing insurers, so the respondent is juristic
            rec["respondent_party_type"] = "juristic"
            rec["respondent_source"] = "text_anchored"
        else:
            if name:
                flags.add("respondent_not_anchored")
            else:
                flags.add("respondent_not_named")
            rec.update(respondent_raw=None, respondent_canonical=None, respondent_public=None,
                       respondent_party_type=None, respondent_source=None)
        fsrc["respondent"] = "model_anchored"

    rec["extraction_method"] = "model+rules" if ans else "rules"
    low = {"rule_model_disagree", "quote_not_anchored", "model_invalid", "model_outcome_off_vocab",
           "model_topic_off_vocab", "no_usable_text", "quote_stitched"}
    med = {"rule_silent", "model_unsure", "words_only_text", "respondent_not_anchored",
           "image_page_not_ocrd", "quote_anchored_prefix", "quote_anchored_suffix", "year_unknown"}
    rec["extraction_confidence"] = ("low" if flags & low else "medium" if flags & med else "high")
    meta["rule_outcome"] = r_out
    meta["model_doubt"] = ans.get("doubt")
    meta["model_certainty"] = ans.get("certainty")
    return finish(rec, flags, fsrc, t0, meta)


def finish(rec, flags, fsrc, t0, meta):
    rec["extraction_flags"] = sorted(flags)
    rec["field_sources"] = fsrc
    rec["extractor_version"] = VERSION
    rec["extracted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta["seconds"] = round(time.time() - t0, 2)
    return rec, meta


# ----------------------------------------------------------------------------- write + verify

def existing():
    if not os.path.exists(LOCAL_OUT):
        return {}
    out = {}
    for line in open(LOCAL_OUT, encoding="utf-8"):
        if line.strip():
            d = json.loads(line)
            out[d["decision_id"]] = d
    return out


def write_and_verify(rec, validator, replace=False):
    """Append (or replace) the record, fsync, re-read the file, parse, find the decision_id, and
    schema-validate what is on disk. Raises on any failure — never reports success it cannot see.
    The record is validated in memory FIRST, so a schema-invalid record never reaches the file
    (the Stage 3c gate found one appended and left behind when validation failed afterwards)."""
    validator.validate(rec)
    if replace and os.path.exists(LOCAL_OUT):
        keep = [l for l in open(LOCAL_OUT, encoding="utf-8")
                if l.strip() and json.loads(l)["decision_id"] != rec["decision_id"]]
        tmp = LOCAL_OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(keep)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, LOCAL_OUT)
    line = json.dumps(rec, ensure_ascii=False, sort_keys=False)
    with open(LOCAL_OUT, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    hits = [json.loads(l) for l in open(LOCAL_OUT, encoding="utf-8")
            if l.strip() and f'"decision_id": "{rec["decision_id"]}"' in l]
    if len(hits) != 1:
        raise RuntimeError(f"{rec['decision_id']}: expected exactly 1 record on disk, found {len(hits)}")
    on_disk = hits[0]
    if on_disk != rec:
        raise RuntimeError(f"{rec['decision_id']}: record on disk differs from the record written")
    validator.validate(on_disk)


def log_progress(entry):
    os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def publish():
    """decisions.public.jsonl: the local records with every restricted field nulled, sorted."""
    recs = sorted(existing().values(), key=lambda d: d["decision_id"])
    tmp = PUBLIC_OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for d in recs:
            p = dict(d)
            for k in d.get("restricted_fields", []):
                p[k] = None
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    os.replace(tmp, PUBLIC_OUT)
    return len(recs)


# ----------------------------------------------------------------------------- sample / queue

def make_sample(census, manifest, mapping, seed=20261123):
    """Stratified random draw, fixed seed: 9 NFO across 9 year bins, 11 FAIS across 11 year bins;
    canonical files with text only. Constraints from the brief: >= 8 NFO, >= 10 FAIS, 2009-2025,
    >= 3 OCR. (>= 1 HTML is unsatisfiable: no determination has HTML text.) The seed is bumped
    until the constraints hold, and the seed used is recorded."""
    det = [r for r in census if r["doc_type"] == "determination" and mapping[r["doc_id"]][1] == r["doc_id"]
           and manifest[r["doc_id"]]["text_source"] != "none" and r.get("year")]
    nfo_bins = [(2009, 2009), (2010, 2010), (2011, 2012), (2013, 2014), (2015, 2016), (2017, 2018),
                (2019, 2019), (2020, 2022), (2023, 2024)]
    fais_bins = [(2009, 2009), (2010, 2010), (2011, 2011), (2012, 2012), (2013, 2014), (2015, 2016),
                 (2017, 2018), (2019, 2020), (2021, 2021), (2023, 2024), (2025, 2025)]
    for s in range(seed, seed + 1000):
        rng = random.Random(s)
        pick = []
        for off, bins in (("NFO", nfo_bins), ("FAIS", fais_bins)):
            for a, b in bins:
                pool = sorted((r for r in det if r["office"] == off and a <= r["year"] <= b),
                              key=lambda r: r["doc_id"])
                pick.append(rng.choice(pool))
        ocr = sum(manifest[r["doc_id"]]["text_source"] == "ocr" for r in pick)
        years = {r["year"] for r in pick}
        if ocr >= 3 and min(years) <= 2009 and max(years) >= 2025:
            return pick, s
    raise SystemExit("no seed satisfied the sample constraints")


# ----------------------------------------------------------------------------- main

def main(argv):
    census, manifest, rows = load()
    by_id = {r["doc_id"]: r for r in census}
    mapping = plan(census)
    det_ids = [r["doc_id"] for r in census if r["doc_type"] == "determination"]
    model = DEFAULT_MODEL
    if "--model" in argv:
        model = argv[argv.index("--model") + 1]
    force, dry, reproc = "--force" in argv or "--reprocess" in argv, "--dry-run" in argv, "--reprocess" in argv

    if "--make-sample" in argv:
        pick, seed = make_sample(census, manifest, mapping)
        with open(SAMPLE, "w") as f:
            for r in pick:
                f.write(json.dumps({"doc_id": r["doc_id"]}) + "\n")
        c = Counter((r["office"], manifest[r["doc_id"]]["text_source"]) for r in pick)
        print(f"sample: {len(pick)} documents, seed {seed}; {dict(c)}; years "
              f"{sorted(r['year'] for r in pick)}")
        return 0
    if "--make-queue" in argv:
        sample = {d["doc_id"] for d in jl(SAMPLE)}
        q = [d for d in det_ids if d not in sample]
        with open(QUEUE, "w") as f:
            for d in q:
                f.write(json.dumps({"doc_id": d}) + "\n")
        print(f"queue: {len(q)} documents ({len(det_ids)} determinations - {len(sample)} sampled)")
        return 0
    if "--publish-only" in argv:
        print("decisions.public.jsonl:", publish(), "records")
        return 0

    if "--sample" in argv:
        todo = [d["doc_id"] for d in jl(SAMPLE)]
    elif "--queue" in argv:
        todo = [d["doc_id"] for d in jl(argv[argv.index("--queue") + 1])]
    else:
        todo = [a for a in argv if a in by_id]
    if "--limit" in argv:
        todo = todo[: int(argv[argv.index("--limit") + 1])]
    bad = [d for d in todo if d not in mapping]
    if bad:
        raise SystemExit(f"not determinations: {bad}")

    validator = jsonschema.Draft202012Validator(json.load(open(SCHEMA)),
                                                format_checker=jsonschema.FormatChecker())
    have = existing()
    secs, failed = [], []
    for n, doc_id in enumerate(todo, 1):
        did = mapping[doc_id][0]
        if did in have and not force:
            log_progress({"doc_id": doc_id, "decision_id": did, "status": "skipped_existing",
                          "at": datetime.now(timezone.utc).isoformat()})
            print(f"[{n}/{len(todo)}] {doc_id} -> {did}: record exists, skipped")
            continue
        out = extract(doc_id, by_id, manifest, rows, mapping, model, dry_run=dry, reprocess=reproc)
        if out is None:
            print(f"[{n}/{len(todo)}] {doc_id}: dry run, masked input written to local/extract/")
            continue
        rec, meta = out
        try:
            validator.validate(rec)
        except jsonschema.ValidationError as e:
            # a rule produced a schema-invalid record: skip this document, keep the run going.
            # The model reply is saved in local/extract/, so --reprocess recovers it after a fix.
            failed.append(did)
            log_progress({"doc_id": doc_id, "decision_id": did, "status": "failed_validation",
                          "error": e.message[:300], "seconds": meta.get("seconds"),
                          "at": datetime.now(timezone.utc).isoformat()})
            print(f"[{n}/{len(todo)}] {doc_id} -> {did}: SCHEMA-INVALID, not written: {e.message[:120]}")
            continue
        write_and_verify(rec, validator, replace=did in have)
        have[did] = rec
        log_progress({"doc_id": doc_id, "decision_id": did, "status": "reprocessed" if reproc else "done",
                      "seconds": meta.get("seconds"), "model": meta.get("model_reported") or meta.get("model"),
                      "usage": meta.get("usage"), "attempts": meta.get("attempts"),
                      "rule_outcome": meta.get("rule_outcome"), "error": meta.get("error"),
                      "rules_dropped_why": meta.get("rules_dropped_why"),
                      "rules_model_only": len(meta.get("rules_model_only") or []),
                      "rules_regex_only": len(meta.get("rules_regex_only") or []),
                      "at": datetime.now(timezone.utc).isoformat()})
        secs.append(meta.get("seconds") or 0)
        print(f"[{n}/{len(todo)}] {doc_id} -> {did}: {rec['outcome']} / {rec['topic_defence']} / {rec['topic_conduct']} "
              f"[{rec['extraction_confidence']}] {meta.get('seconds')}s {','.join(rec['extraction_flags'])}")
    n_pub = publish()
    if failed:
        print(f"SCHEMA-INVALID, not written ({len(failed)}): {failed}")
    if secs:
        print(f"extracted {len(secs)}; median {statistics.median(secs):.1f}s/doc; "
              f"decisions.public.jsonl: {n_pub} records")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
