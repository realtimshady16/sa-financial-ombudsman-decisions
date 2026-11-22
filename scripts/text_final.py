"""Stage 2: assemble text/final/ and text_manifest.jsonl. Local only; reads, never rewrites, text/raw/.

One manifest row per census row (1004). `text_source`:
  native     PDF text layer: text/raw/<id>.txt (Stage 1's pdftotext -layout) + normalize.py
  repaired   the three Quartz-damaged NFO determinations, re-extracted from a font-patched copy
             (scripts/repair.py writes their text/final file; this script only records them)
  converted  legacy .doc via `libreoffice --convert-to txt`; the one .ppt via libreoffice -> PDF ->
             pdftotext -layout (Impress has no plain-text export filter)
  ocr        an image-only PDF whose OCR passed the gate and was promoted to text/final
  none       no text in text/final yet: image-only PDFs while OCR is gated, PDFs truncated at the
             source, and HTML-only pages (their text stays in html/; not extracted in Stage 2)

`common_word_rate` and `words` are computed on the text/final file with Stage 1's own
`pdfcheck.text_metrics`, so the numbers are comparable with sources.jsonl.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from normalize import normalize  # noqa: E402
from pdfcheck import text_metrics  # noqa: E402
from repair import DAMAGED  # noqa: E402

FINAL = os.path.join(ROOT, "text", "final")
CONV = os.path.join(ROOT, "text", "converted")
OCR = os.path.join(ROOT, "text", "ocr")
OCR_PROMOTED = os.path.join(ROOT, "text", "ocr", "PROMOTED")  # list of doc_ids cleared for text/final

# Found in Stage 2 by page-level checks (notes/text-quality.md §1–2); carried into the manifest notes
# so a downstream reader of a "native" row knows its text is incomplete.
KNOWN = {
    "fais-det-15c2696c4e68": "text layer is only a PDF-XChange trial watermark on each page; the ruling is a scan: needs OCR",
    "fais-det-2bc1a054c329": "one-page group-structure chart linked as the 'Determination'; the ruling text is not in this file",
    "nfo-8202": "61 of 65 pages are images of text with no text layer: needs OCR",
    "nfo-11308": "70 of 75 pages are images of text with no text layer: needs OCR",
    "nfo-3146": "10 of 12 pages are images of text with no text layer: needs OCR",
}
for _d in ("fais-det-0b57feb5bc19", "fais-det-170de4935c92", "fais-det-5fced554b462",
           "fais-det-cf6db343bfa5", "fais-det-d8f54f31c416", "fais-det-df08d4efe364"):
    KNOWN[_d] = "one page is an embedded image holding ~140-270 words and ~30-40 numbers: needs page-level OCR before amounts are read"


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def write_final(doc_id, text):
    with open(os.path.join(FINAL, doc_id + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)


def main():
    os.makedirs(FINAL, exist_ok=True)
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "sources.jsonl"))]
    promoted = set(read(OCR_PROMOTED).split()) if os.path.exists(OCR_PROMOTED) else set()
    out = []
    for r in rows:
        d, snap = r["doc_id"], r["snapshot"]
        m = {"doc_id": d, "text_source": None, "pages": r.get("pages"), "words": None,
             "common_word_rate": None, "ocr_mean_confidence": None, "repair_fonts": None, "notes": None}
        ocr_meta = os.path.join(OCR, d + ".json")
        if os.path.exists(ocr_meta):
            m["ocr_mean_confidence"] = json.load(open(ocr_meta))["ocr_mean_confidence"]
        if d in DAMAGED:
            rec = json.load(open(os.path.join(ROOT, "text", "repair", d + ".json")))
            fonts = {}
            for e in rec["font_map"]:
                if e["changed"]:
                    fonts.setdefault((e["font"], e["font_obj"]), {})[e["shows_as"]] = e["repaired_to"]
            m["text_source"] = "repaired"
            m["repair_fonts"] = [{"font": f, "obj": o, "map": mp} for (f, o), mp in fonts.items()]
            n = sum(e["glyphs"] for e in rec["font_map"] if e["changed"])
            m["notes"] = (f"{n} stand-in glyphs re-mapped by patching each font's ToUnicode in a copy and "
                          f"re-running pdftotext -layout; digit runs identical to raw minus "
                          f"{rec['checks']['standin_digit_glyphs_removed']} stand-in glyphs that showed as digits")
        elif snap.endswith((".doc", ".ppt")):
            if snap.endswith(".doc"):
                src = os.path.join(CONV, d + ".txt")
                how = "libreoffice --headless --convert-to txt (Writer, UTF-8)"
            else:
                pdf = os.path.join(CONV, d + ".pdf")
                src = os.path.join(CONV, d + ".txt")
                subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", pdf, src], check=True)
                p = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
                m["pages"] = next((int(l.split()[-1]) for l in p.splitlines() if l.startswith("Pages:")), None)
                how = "libreoffice --headless --convert-to pdf (Impress has no txt filter), then pdftotext -layout; pages = slides"
            text, norm = normalize(read(src).lstrip("﻿"))
            write_final(d, text)
            m["text_source"] = "converted"
            m["notes"] = how
        elif snap.startswith("html/"):
            m["text_source"] = "none"
            m["notes"] = "HTML-only page (digest); text stays in html/, not extracted in Stage 2"
        elif r.get("pdf_readable") is False:
            m["text_source"] = "none"
            m["notes"] = "PDF truncated at the source (no trailer, no catalog); qpdf recovery fails; permanent gap unless re-served"
        elif r.get("has_text_layer"):
            text, norm = normalize(read(os.path.join(ROOT, "text", "raw", d + ".txt")))
            write_final(d, text)
            m["text_source"] = "native"
            bits = [f"{k.replace('_', ' ')}: {v}" for k, v in norm.items() if v]
            m["notes"] = "; ".join(bits) or None
        elif d in promoted:
            text, norm = normalize(read(os.path.join(OCR, d + ".txt")))
            write_final(d, text)
            m["text_source"] = "ocr"
            m["notes"] = "tesseract 5.5.3 eng, 300 dpi grayscale"
        else:
            m["text_source"] = "none"
            if os.path.exists(ocr_meta):
                m["notes"] = "image-only; OCR'd in the gate sample (text/ocr/), not promoted: gate failed, see notes/ocr-sample.md"
            else:
                m["notes"] = "image-only; OCR not run: gate failed, see notes/ocr-sample.md"
        if d in KNOWN:
            m["notes"] = "; ".join(x for x in (m["notes"], KNOWN[d]) if x)
        fp = os.path.join(FINAL, d + ".txt")
        if m["text_source"] != "none" and os.path.exists(fp):
            tm = text_metrics(read(fp), r.get("language"))
            m["words"], m["common_word_rate"] = tm["words"], tm["common_word_rate"]
        out.append(m)
    with open(os.path.join(ROOT, "text_manifest.jsonl"), "w") as f:
        for m in out:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    from collections import Counter
    print("text_manifest.jsonl:", len(out), "rows;", dict(Counter(m["text_source"] for m in out)))
    print("text/final files:", len(os.listdir(FINAL)))


if __name__ == "__main__":
    main()
