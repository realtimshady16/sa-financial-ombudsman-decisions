"""Stage 2 verification. No network. One line per check; exits non-zero on any failure.

Run: python3 -I scripts/check_text.py
Also writes local/restricted-needles.txt (gitignored): every FAIS party name (>= 6 chars) and
determination filename from the restricted row file, one per line, so the name-leak check can be
run by hand as  git grep -i -c -F -f local/restricted-needles.txt HEAD | wc -l
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True
SOURCES = {"native", "ocr", "repaired", "converted", "none"}
REPAIRED = ["nfo-5862", "nfo-5863", "nfo-6787"]


def standin_forms(doc_id):
    """Every damaged word exactly as it appears in the raw text (`jus@fy`, `occupa>on`, `condi8on`):
    the pass-1 tokens that hold a hole code, with each hole shown as its WinAnsi fallback char."""
    p1 = open(os.path.join(ROOT, "text", "repair", doc_id + ".pass1.txt"), encoding="utf-8").read()
    rec = json.load(open(os.path.join(ROOT, "text", "repair", doc_id + ".json")))
    holes = [(f["obj"], c) for f in rec["fonts"] for c in f["holes"]]
    fb = {chr(0xE000 + i): bytes([c]).decode("cp1252", "replace") for i, (_, c) in enumerate(holes)}
    toks = re.findall(r"[A-Za-z\uE000-\uE0FF]+", p1)
    return sorted({"".join(fb.get(ch, ch) for ch in t) for t in toks if any(ch in fb for ch in t)})


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def jl(p):
    with open(os.path.join(ROOT, p)) as f:
        return [json.loads(l) for l in f]


rows = jl("sources.jsonl")
man = jl("text_manifest.jsonl")
final = set(f[:-4] for f in os.listdir(os.path.join(ROOT, "text", "final")))
raw = set(f[:-4] for f in os.listdir(os.path.join(ROOT, "text", "raw")))

check("text_manifest.jsonl parses", True, f"{len(man)} rows")
check("one manifest row per census row, same order", [m["doc_id"] for m in man] == [r["doc_id"] for r in rows])
check("every row has a valid text_source", all(m.get("text_source") in SOURCES for m in man))
want = {m["doc_id"] for m in man if m["text_source"] != "none"}
check("text/final/<id>.txt exists exactly for rows with text", want == final,
      f"{len(final)} files; missing {sorted(want - final)[:3]}; extra {sorted(final - want)[:3]}")
check("manifest carries no restricted field names", all(set(m) == {"doc_id", "text_source", "pages", "words",
      "common_word_rate", "ocr_mean_confidence", "repair_fonts", "notes"} for m in man))
raw_mt = max(os.path.getmtime(os.path.join(ROOT, "text", "raw", f)) for f in os.listdir(os.path.join(ROOT, "text", "raw")))
fin_mt = min(os.path.getmtime(os.path.join(ROOT, "text", "final", f)) for f in os.listdir(os.path.join(ROOT, "text", "final")))
check("text/raw untouched (every raw file older than every final file)", raw_mt < fin_mt, f"{len(raw)} raw files")

def count_forms(forms, text):
    return sum(len(re.findall(r"(?<![A-Za-z])" + re.escape(f) + r"(?![A-Za-z])", text)) for f in forms)


for d in REPAIRED:
    t = open(os.path.join(ROOT, "text", "final", d + ".txt"), encoding="utf-8").read()
    r = open(os.path.join(ROOT, "text", "raw", d + ".txt"), encoding="utf-8").read()
    brief = len(re.findall(r"condi8on|par8cipant|Interpreta\(on|aJached|underwriJen", t))
    forms = standin_forms(d)
    own_raw, own_fin = count_forms(forms, r), count_forms(forms, t)
    rec = json.load(open(os.path.join(ROOT, "text", "repair", d + ".json")))["checks"]
    check(f"{d} repaired: brief's stand-in grep 0, its own {len(forms)} damaged word forms {own_raw}->{own_fin}, "
          f"'ti' {r.count('ti')}->{t.count('ti')}",
          brief == 0 and own_fin == 0 and t.count("ti") > 0 and rec["roundtrip_pass1_equals_raw"]
          and rec["digit_runs_final_equal_pass1"] and rec["amounts_identical"])

# ---- privacy: FAIS party names and determination filenames must not appear in anything committed
needles = set()
for r in jl(os.path.join("local", "fais-determination-rows.jsonl")):
    for k in ("complainant", "respondent"):
        v = (r.get(k) or "").strip()
        if len(v) >= 6:
            needles.add(v.lower())
    for fobj in r["files"]:
        fn = fobj["filename"]
        needles.add(fn.lower())
        stem = re.sub(r"\.pdf$", "", fn, flags=re.I)
        if len(stem) >= 6:
            needles.add(stem.lower())
with open(os.path.join(ROOT, "local", "restricted-needles.txt"), "w") as f:
    f.write("\n".join(sorted(needles)) + "\n")
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
targets = sorted(set(tracked + untracked))
hits = {}
for t in targets:
    p = os.path.join(ROOT, t)
    if not os.path.isfile(p):
        continue
    with open(p, encoding="utf-8", errors="replace") as f:
        hay = f.read().lower()
    n = sum(1 for s in needles if s in hay)
    if n:
        hits[t] = n  # file name and count only, never the matched string
check("privacy: no FAIS party name or filename in any committable file", not hits,
      f"{len(needles)} restricted strings x {len(targets)} files; hits {hits}")
sys.exit(0 if ok else 1)
