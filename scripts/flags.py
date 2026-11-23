"""Split the overloaded `suspect` flag into what it was actually conflating.

`suspect` was one boolean doing two jobs: "this document has no text layer, so it needs OCR" and
"this document's extracted text is damaged". 185 rows were the first kind and ~4 the second, so a
report that said "191 suspect documents" overstated damage sixtyfold.

This script derives, from `suspect_reasons` (the vocabulary harvest.py already records):

  needs_ocr     no_text_layer                 — image-only, awaiting OCR
  damaged       quartz_cmap_holes | no_tion_in_long_english_text | replacement_chars |
                many_suspect_tokens           — text present but corrupt
  unreadable    unreadable_pdf                — neither, and permanent

and keeps `suspect` untouched for continuity. Rewrites sources.jsonl and the name-free
sources.public.jsonl in place, preserving row order.

  python3 scripts/flags.py [--check]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sources.jsonl")
PUB = os.path.join(ROOT, "sources.public.jsonl")

OCR_REASONS = {"no_text_layer"}
DAMAGE_REASONS = {"quartz_cmap_holes", "no_tion_in_long_english_text", "replacement_chars",
                  "many_suspect_tokens"}
UNREADABLE_REASONS = {"unreadable_pdf"}


def classify(row):
    reasons = set(row.get("suspect_reasons") or [])
    return {
        "needs_ocr": bool(reasons & OCR_REASONS),
        "damaged": bool(reasons & DAMAGE_REASONS),
        "unreadable": bool(reasons & UNREADABLE_REASONS),
        "damage_reasons": sorted(reasons & (DAMAGE_REASONS | UNREADABLE_REASONS)) or None,
    }


def rewrite(path, check):
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    for row in rows:
        row.update(classify(row))
    counts = {
        "rows": len(rows),
        "needs_ocr": sum(r["needs_ocr"] for r in rows),
        "damaged": sum(r["damaged"] for r in rows),
        "unreadable": sum(r["unreadable"] for r in rows),
        "suspect": sum(1 for r in rows if r.get("suspect")),
    }
    if not check:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return counts


def main(argv):
    check = "--check" in argv
    for path in (SRC, PUB):
        if not os.path.exists(path):
            print(f"skip (absent): {os.path.basename(path)}")
            continue
        c = rewrite(path, check)
        print(f"{os.path.basename(path)}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
