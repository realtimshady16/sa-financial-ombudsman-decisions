"""Stage 1 verification. No network. Prints one line per check; exits non-zero on any failure.

Run: python3 -I scripts/check.py
"""
import json
import os
import subprocess
import sys

from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def jl(p):
    with open(os.path.join(ROOT, p)) as f:
        return [json.loads(l) for l in f]


rows = jl("sources.jsonl")
pub = jl("sources.public.jsonl")
pdf_files = sorted(os.listdir(os.path.join(ROOT, "pdf")))
html_files = sorted(os.listdir(os.path.join(ROOT, "html")))
pdf_rows = [r for r in rows if r["snapshot"].startswith("pdf/")]
html_rows = [r for r in rows if r["snapshot"].startswith("html/")]

check("sources.jsonl parses", True, f"{len(rows)} rows")
check("rows == files on disk", len(rows) == len(pdf_files) + len(html_files),
      f"{len(rows)} rows; pdf/ {len(pdf_files)} + html/ {len(html_files)}")
check("pdf/ rows == ls pdf/", len(pdf_rows) == len(pdf_files), f"{len(pdf_rows)} vs {len(pdf_files)}")
check("every row's snapshot exists, names match doc_id",
      {r["snapshot"] for r in rows} == {f"pdf/{f}" for f in pdf_files} | {f"html/{f}" for f in html_files})
check("doc_ids unique", len({r["doc_id"] for r in rows}) == len(rows))

p = subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=ROOT, capture_output=True, text=True)
n_sums = sum(1 for _ in open(os.path.join(ROOT, "SHA256SUMS")))
check("sha256sum -c SHA256SUMS", p.returncode == 0 and n_sums == len(rows),
      f"{n_sums} entries" + (f"; {p.stdout.strip()[:200]}" if p.returncode else ""))

v = Draft202012Validator(json.load(open(os.path.join(ROOT, "schema", "document.schema.json"))))
errs = [(r["doc_id"], e.message[:120]) for r in rows for e in v.iter_errors(r)]
check("sources.jsonl validates against schema/document.schema.json", not errs, f"{len(errs)} errors {errs[:3]}")
errs = [(r["doc_id"], e.message[:120]) for r in pub for e in v.iter_errors(r)]
check("sources.public.jsonl validates", not errs, f"{len(errs)} errors {errs[:3]}")
check("public rows carry no restricted data",
      all("restricted" not in r and all(r.get(k) is None for k in r["restricted_fields"]) for r in pub))
check("same rows in public and local", [r["doc_id"] for r in pub] == [r["doc_id"] for r in rows])
txt = [r for r in rows if r["snapshot"].endswith(".pdf")]
check("text/raw/<doc_id>.txt exists for every PDF",
      all(os.path.exists(os.path.join(ROOT, "text", "raw", r["doc_id"] + ".txt")) for r in txt),
      f"{len(txt)} PDFs")
sys.exit(0 if ok else 1)
