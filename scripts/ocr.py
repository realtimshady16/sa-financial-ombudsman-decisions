"""Stage 2: OCR the image-only PDFs. Sequential, resumable, local only.

  python3 scripts/ocr.py                 # every row with has_text_layer == false
  python3 scripts/ocr.py DOC_ID [...]    # just these (the gate sample)

Per document, into text/ocr/ (gitignored):
  <doc_id>/page-NNNN.txt   tesseract text for one page
  <doc_id>/page-NNNN.tsv   tesseract word boxes + confidence for that page
  <doc_id>.txt             pages joined with \\f, the way pdftotext separates pages
  <doc_id>.json            done-marker: pages, words, mean confidence, timing

Resumable at two levels: a document with a .json is skipped; inside a document, a page whose
.txt and .tsv both exist is not redone. Pages are rasterised one at a time at 300 dpi, grayscale,
into a temp dir that is deleted per page, so the run never holds more than one page image.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "text", "ocr")
DPI = 300
LANG = "eng"  # the only traineddata installed; every image-only row is language 'en' in the census


def page_conf(tsv_path):
    """-> (word count, sum of confidences) over level-5 (word) rows with conf >= 0 and text."""
    n, s = 0, 0.0
    with open(tsv_path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row.get("level") != "5" or not (row.get("text") or "").strip():
                continue
            try:
                c = float(row["conf"])
            except (TypeError, ValueError):
                continue
            if c >= 0:
                n += 1
                s += c
    return n, s


def ocr_doc(doc_id, pdf, pages):
    d = os.path.join(OUT, doc_id)
    os.makedirs(d, exist_ok=True)
    t0 = time.time()
    texts, nwords, csum, failed = [], 0, 0.0, []
    for p in range(1, pages + 1):
        base = os.path.join(d, f"page-{p:04d}")
        if not (os.path.exists(base + ".txt") and os.path.exists(base + ".tsv")):
            tmp = tempfile.mkdtemp(prefix="ocr-", dir=OUT)
            try:
                r = subprocess.run(["pdftoppm", "-r", str(DPI), "-gray", "-png", "-f", str(p), "-l", str(p),
                                    pdf, os.path.join(tmp, "p")], capture_output=True, timeout=300)
                imgs = [x for x in os.listdir(tmp) if x.endswith(".png")]
                if r.returncode or not imgs:
                    failed.append({"page": p, "stage": "pdftoppm", "err": r.stderr.decode()[:200]})
                    open(base + ".txt", "w").close()
                    open(base + ".tsv", "w").close()
                else:
                    r = subprocess.run(["tesseract", os.path.join(tmp, imgs[0]), base, "-l", LANG, "txt", "tsv"],
                                       capture_output=True, timeout=600,
                                       env={**os.environ, "OMP_THREAD_LIMIT": "1"})
                    if r.returncode:
                        failed.append({"page": p, "stage": "tesseract", "err": r.stderr.decode()[:200]})
                        for ext in (".txt", ".tsv"):
                            if not os.path.exists(base + ext):
                                open(base + ext, "w").close()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        with open(base + ".txt", encoding="utf-8", errors="replace") as f:
            texts.append(f.read())
        n, s = page_conf(base + ".tsv") if os.path.getsize(base + ".tsv") else (0, 0.0)
        nwords += n
        csum += s
    with open(os.path.join(OUT, doc_id + ".txt"), "w", encoding="utf-8") as f:
        f.write("\f".join(texts))
    meta = {"doc_id": doc_id, "pages": pages, "dpi": DPI, "lang": LANG,
            "ocr_words": nwords,
            "ocr_mean_confidence": round(csum / nwords, 2) if nwords else None,
            "failed_pages": failed, "seconds": round(time.time() - t0, 1),
            "tesseract": subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.split("\n")[0]}
    with open(os.path.join(OUT, doc_id + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta


def main(argv):
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "sources.jsonl"))]
    by_id = {r["doc_id"]: r for r in rows}
    ids = argv or [r["doc_id"] for r in rows if r.get("has_text_layer") is False]
    os.makedirs(OUT, exist_ok=True)
    todo = [i for i in ids if not os.path.exists(os.path.join(OUT, i + ".json"))]
    print(f"{len(ids)} requested, {len(ids) - len(todo)} already done, {len(todo)} to do", flush=True)
    for k, doc_id in enumerate(todo, 1):
        r = by_id[doc_id]
        m = ocr_doc(doc_id, os.path.join(ROOT, r["snapshot"]), r["pages"])
        print(f"[{k}/{len(todo)}] {doc_id} pages={m['pages']} words={m['ocr_words']} "
              f"conf={m['ocr_mean_confidence']} failed={len(m['failed_pages'])} {m['seconds']}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
