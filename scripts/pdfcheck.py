"""Per-PDF extraction-health diagnostics. No repair happens here (that is Stage 2).

Records, per file:
  pdfinfo  : pages, producer, creator, created, encrypted, pdf_version
  pdffonts : every font with its type / embedded / subset / has-ToUnicode flags
  qpdf     : ToUnicode *holes* per simple font — codes in FirstChar..LastChar with a non-zero
             width but no CMap entry. A font can say "uni yes" in pdffonts and still have holes;
             that is exactly the Quartz ligature failure (NFO case 58).
  text     : pdftotext -layout -> text/raw/<doc_id>.txt, plus cheap damage signals.
"""
import json
import os
import re
import subprocess
from collections import Counter

COMMON = set("""the of and to a in is that for it as with was on be by this are or at from
not an which have has but were been their they its any all can if no may will would there
other such these also must should than into who our more one under did does when what made
being because where shall only after before between those then them about upon he she his her
we you your out so do had over within against same each further time claim policy complaint
""".split())

# A digit or bracket inside a lowercase run (`condi8on`, `par(cipant`): the Quartz stand-in shape.
SUSPECT_RE = re.compile(r"[a-z]{2,}[0-9(\[][a-z]{2,}")
# A capital inside a lowercase run (`maJer`, `ApplicaAon`) is also a stand-in shape, but it is
# ordinary in Nguni orthography (`loMlamuli`), brand names (`BrightRock`) and surnames, so it is
# recorded for Stage 2 and never used as a flag on its own.
CAMEL_RE = re.compile(r"[a-z]{2,}[A-Z][a-z]{2,}")
WORD_RE = re.compile(r"[^\W\d_]+")


def run(cmd, timeout=300):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def pdfinfo(path):
    rc, out, err = run(["pdfinfo", "-isodates", path])
    info = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    pages = info.get("Pages")
    return {
        "pages": int(pages) if pages and pages.isdigit() else None,
        "producer": info.get("Producer") or None,
        "creator": info.get("Creator") or None,
        "pdf_created": info.get("CreationDate") or None,
        "encrypted": (info.get("Encrypted", "no").split()[0] == "yes"),
        "pdf_version": info.get("PDF version"),
        "pdfinfo_error": err.strip()[:300] if rc else None,
    }


def pdffonts(path):
    rc, out, err = run(["pdffonts", path])
    lines = out.splitlines()
    fonts = []
    if len(lines) >= 2 and lines[1].startswith("---"):
        # column extents from the dashes row
        spans, i = [], 0
        dash = lines[1]
        while i < len(dash):
            if dash[i] == "-":
                j = i
                while j < len(dash) and dash[j] == "-":
                    j += 1
                spans.append((i, j))
                i = j
            else:
                i += 1
        for line in lines[2:]:
            cols = [line[a:b + 1].strip() for a, b in spans]
            if len(cols) < 6:
                continue
            fonts.append({"name": cols[0], "type": cols[1], "encoding": cols[2],
                          "emb": cols[3] == "yes", "sub": cols[4] == "yes", "uni": cols[5] == "yes"})
    return fonts, (err.strip()[:300] if rc else None)


# ---------------------------------------------------------------- ToUnicode holes via qpdf

def _resolve(objs, v):
    if isinstance(v, str) and re.fullmatch(r"\d+ \d+ R", v):
        o = objs.get(f"obj:{v}")
        if o is None:
            return None
        return o.get("value", o.get("stream", {}).get("dict"))
    return v


def _cmap_codes(text):
    codes = set()
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src in re.findall(r"<([0-9A-Fa-f]+)>\s*<[0-9A-Fa-f]*>", block):
            codes.add(int(src, 16))
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for lo, hi in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(?:<[0-9A-Fa-f]*>|\[[^\]]*\])", block):
            codes.update(range(int(lo, 16), int(hi, 16) + 1))
    return codes


def tounicode_holes(path):
    """-> (list of {font, holes:[codes as chars]}, error). Simple fonts only; Type0 skipped."""
    rc, out, err = run(["qpdf", "--json=2", "--json-key=qpdf", "--json-stream-data=none", path], timeout=600)
    if rc not in (0, 3):
        return None, f"qpdf rc={rc}: {err.strip()[:200]}"
    try:
        objs = json.loads(out)["qpdf"][1]
    except (ValueError, KeyError, IndexError) as e:
        return None, f"qpdf json: {e}"
    results = []
    cmap_cache = {}
    for key, o in objs.items():
        d = o.get("value") if isinstance(o, dict) else None
        if not isinstance(d, dict) or d.get("/Type") != "/Font":
            continue
        if d.get("/Subtype") not in ("/TrueType", "/Type1", "/MMType1"):
            continue
        tu = d.get("/ToUnicode")
        fc, lc = _resolve(objs, d.get("/FirstChar")), _resolve(objs, d.get("/LastChar"))
        widths = _resolve(objs, d.get("/Widths"))
        if not (isinstance(tu, str) and isinstance(fc, int) and isinstance(lc, int)
                and isinstance(widths, list)):
            continue
        ref = tu.split()[0]
        if ref not in cmap_cache:
            rc2, cm, _ = run(["qpdf", f"--show-object={ref}", "--filtered-stream-data", path])
            cmap_cache[ref] = _cmap_codes(cm) if rc2 in (0, 3) else None
        mapped = cmap_cache[ref]
        if mapped is None:
            continue
        holes = []
        for c in range(fc, lc + 1):
            w = widths[c - fc] if c - fc < len(widths) else 0
            w = _resolve(objs, w)
            if isinstance(w, (int, float)) and w > 0 and c not in mapped and c != 32:
                holes.append(c)
        if holes:
            results.append({"font": str(d.get("/BaseFont", "?")).lstrip("/"),
                            "holes": [chr(c) if 33 <= c < 127 else f"0x{c:02x}" for c in holes]})
    return results, None


# ---------------------------------------------------------------- text

def text_metrics(text, language):
    words = WORD_RE.findall(text)
    lower = [w.lower() for w in words]
    n = len(words)
    tokens = text.split()
    def plain(t):
        return "http" not in t and "@" not in t and "www" not in t
    suspect = [t for t in tokens if SUSPECT_RE.search(t) and plain(t)]
    camel = [t for t in tokens if CAMEL_RE.search(t) and plain(t)]
    return {
        "words": n,
        "common_word_rate": round(sum(1 for w in lower if w in COMMON) / n, 4) if n else None,
        "tion_count": sum(w.count("tion") for w in lower),
        "suspect_tokens": len(suspect),
        "camel_tokens": len(camel),
        "soft_hyphens": text.count("­"),
        "ligature_chars": sum(text.count(c) for c in "ﬀﬁﬂﬃﬄﬅﬆ"),
        "replacement_chars": text.count("�"),
    }


def analyse(pdf_path, txt_out, language="en"):
    a = pdfinfo(pdf_path)
    fonts, ferr = pdffonts(pdf_path)
    a["fonts"] = fonts
    a["pdffonts_error"] = ferr
    a["fonts_missing_tounicode"] = sorted({f["name"] for f in fonts if not f["uni"]})
    a["fonts_have_tounicode"] = (all(f["uni"] for f in fonts) if fonts else None)
    try:
        holes, herr = tounicode_holes(pdf_path)
    except subprocess.TimeoutExpired:
        holes, herr = None, "qpdf timeout"
    a["cmap_holes"] = holes
    a["cmap_hole_count"] = (sum(len(h["holes"]) for h in holes) if holes is not None else None)
    a["cmap_error"] = herr
    rc, _, err = run(["pdftotext", "-layout", "-enc", "UTF-8", pdf_path, txt_out], timeout=600)
    a["pdftotext_error"] = err.strip()[:300] if rc else None
    a["pdf_readable"] = os.path.exists(txt_out)
    if not a["pdf_readable"]:  # poppler could not open it: keep an empty raw-text file, flag it
        open(txt_out, "w").close()
    with open(txt_out, encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = text_metrics(text, language)
    a.update(m)
    pages = a.get("pages") or 0
    a["words_per_page"] = round(m["words"] / pages, 1) if pages else None
    a["has_text_layer"] = (m["words"] >= 20) if a["pdf_readable"] else None
    return a
