"""Stage 2: repair the three Quartz-damaged NFO determinations (cases 56, 57, 58) per font.

The damage: macOS Quartz subsets each font with codes assigned from 33 upward, and writes a ToUnicode
CMap that leaves the ligature glyphs (ti, tt, ...) out. poppler then falls back to WinAnsi for those
codes, so code 56 comes out as '8', code 74 as 'J', and so on. Which code carries which ligature
differs per font *object* (a file can hold three Calibri subsets), and the fallback characters
collide with real text: '8' is also a digit in amounts like `R8 000` (from a different, mapped code
in a different subset). So there is no character-level map that is safe on the extracted text.

The repair therefore never touches the text. It fixes the font: for each (font object, unmapped
code) it adds a ToUnicode entry to a *copy* of the PDF and re-extracts with the same
`pdftotext -layout` call Stage 1 used. Codes that were mapped are untouched by construction, so a
real digit cannot be rewritten.

  pass 1  map every hole to its own private-use char (U+E000 + i) -> text/repair/<id>.pass1.txt.
          Replacing each PUA char by its WinAnsi fallback must give back text/raw/<id>.txt exactly,
          which proves the patch changed nothing but the hole codes.
  vote    for each hole, try every candidate ligature (and the fallback char itself) in every word it
          occurs in; the candidate that turns the most occurrences into wordlist words wins. The
          wordlist is the corpus's own clean native text plus /usr/share/dict/cracklib-small.
  pass 2  map each hole to its winner -> text/final/<id>.txt.
  checks  stand-in tokens gone, 'ti' present, wordlist hit rate before/after, and every digit run in
          the final text equals, in order, the digit runs of pass 1 (the raw text minus stand-ins).

Writes text/repair/<id>.json with the per-font map and the checks. Never writes into pdf/ or text/raw/.
"""
import base64
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from normalize import normalize  # noqa: E402

DAMAGED = {"nfo-5862": "Final Determinations 2023 – Case 56",
           "nfo-5863": "Final Determinations 2023 – Case 57",
           "nfo-6787": "Final Determinations 2024 – Case 58"}
CANDIDATES = ["ti", "tt", "tti", "tf", "ft", "fi", "fl", "ff", "ffi", "ffl", "fft", "fj", "th"]
WORK = os.path.join(ROOT, "text", "repair")
PUA = 0xE000
TOKEN = re.compile(r"[A-Za-z-]+")
BAD = re.compile(r"condi8on|par8cipant|Interpreta\(on|aJached|underwriJen")


def run(cmd, **kw):
    """qpdf exits 3 for 'succeeded with warnings'; anything else non-zero is a failure."""
    p = subprocess.run(cmd, capture_output=True, **kw)
    if p.returncode not in (0, 3):
        raise RuntimeError(f"{cmd[0]} rc={p.returncode}: {p.stderr.decode('utf-8', 'replace')[:300]}")
    return p


def qpdf_objects(pdf):
    out = run(["qpdf", "--json=2", "--json-key=qpdf", "--json-stream-data=none", pdf]).stdout
    return json.loads(out)["qpdf"][1]


def resolve(objs, v):
    if isinstance(v, str) and re.fullmatch(r"\d+ \d+ R", v):
        o = objs.get(f"obj:{v}")
        return None if o is None else o.get("value", o.get("stream", {}).get("dict"))
    return v


def cmap_codes(text):
    codes = set()
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src in re.findall(r"<([0-9A-Fa-f]+)>\s*<[0-9A-Fa-f]*>", block):
            codes.add(int(src, 16))
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for lo, hi in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(?:<[0-9A-Fa-f]*>|\[[^\]]*\])", block):
            codes.update(range(int(lo, 16), int(hi, 16) + 1))
    return codes


def fonts_with_holes(pdf):
    """-> [{obj, base, tu_ref, tu_text, holes:[code]}] for simple fonts with a ToUnicode map."""
    objs = qpdf_objects(pdf)
    out = []
    for key, o in objs.items():
        d = o.get("value") if isinstance(o, dict) else None
        if not isinstance(d, dict) or d.get("/Type") != "/Font" or d.get("/Subtype") not in ("/TrueType", "/Type1"):
            continue
        tu = d.get("/ToUnicode")
        fc, lc = resolve(objs, d.get("/FirstChar")), resolve(objs, d.get("/LastChar"))
        widths = resolve(objs, d.get("/Widths"))
        if not (isinstance(tu, str) and isinstance(fc, int) and isinstance(lc, int) and isinstance(widths, list)):
            continue
        ref = tu.split()[0]
        tu_text = run(["qpdf", f"--show-object={ref}", "--filtered-stream-data", pdf]).stdout.decode("latin-1")
        mapped = cmap_codes(tu_text)
        holes = [c for c in range(fc, lc + 1)
                 if c != 32 and c not in mapped and isinstance(resolve(objs, widths[c - fc]), (int, float))
                 and resolve(objs, widths[c - fc]) > 0]
        out.append({"obj": key[4:].split()[0], "base": d.get("/BaseFont", "?").lstrip("/"),
                    "tu_ref": ref, "tu_text": tu_text, "holes": holes})
    return out


def utf16hex(s):
    return s.encode("utf-16-be").hex().upper()


def patch(pdf, fonts, mapping, out_pdf):
    """mapping: {(font obj, code): replacement string}. Adds bfchar entries to each font's own CMap."""
    upd = {}
    for f in fonts:
        entries = [(c, mapping[(f["obj"], c)]) for c in f["holes"] if (f["obj"], c) in mapping]
        if not entries:
            continue
        add = f"{len(entries)} beginbfchar\n" + "".join(f"<{c:02X}> <{utf16hex(s)}>\n" for c, s in entries) + "endbfchar\n"
        text = f["tu_text"]
        i = text.rfind("endcmap")
        assert i > 0, f"no endcmap in ToUnicode {f['tu_ref']}"
        new = text[:i] + add + text[i:]
        upd[f"obj:{f['tu_ref']} 0 R"] = {"stream": {"dict": {}, "data": base64.b64encode(new.encode("latin-1")).decode()}}
    j = {"qpdf": [{"jsonversion": 2, "pushedinheritedpageresources": False, "calledgetallpages": False,
                   "maxobjectid": 0}, upd]}
    jpath = out_pdf + ".update.json"
    with open(jpath, "w") as fh:
        json.dump(j, fh)
    run(["qpdf", pdf, out_pdf, f"--update-from-json={jpath}"])
    os.remove(jpath)


def extract(pdf, txt):
    run(["pdftotext", "-layout", "-enc", "UTF-8", pdf, txt])
    with open(txt, encoding="utf-8") as fh:
        return fh.read()


def fallback(code):
    return bytes([code]).decode("cp1252", errors="replace")


def build_wordlist():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "sources.jsonl"))]
    freq = Counter()
    for r in rows:
        if (r.get("has_text_layer") and r.get("language") == "en" and not r.get("suspect")
                and (r.get("common_word_rate") or 0) >= 0.3 and r["doc_id"] not in DAMAGED):
            with open(os.path.join(ROOT, "text", "raw", r["doc_id"] + ".txt"), encoding="utf-8", errors="replace") as fh:
                freq.update(w.lower() for w in re.findall(r"[A-Za-z]+", normalize(fh.read())[0]))
    words = {w for w, n in freq.items() if n >= 2}
    with open("/usr/share/dict/cracklib-small", encoding="utf-8", errors="replace") as fh:
        words |= {l.strip().lower() for l in fh if l.strip().isalpha()}
    return words, freq


def vote(pass1, holes_by_pua, words, freq):
    """-> {pua char: (winner, votes, words holding it, runner_up)}; votes and words count tokens, not glyphs"""
    toks = TOKEN.findall(pass1)
    with_pua = [t for t in toks if any(PUA <= ord(c) < PUA + 256 for c in t)]
    # round 1 on tokens holding a single distinct PUA char, round 2 fills multi-PUA tokens with round-1 winners
    best = {}
    for rnd in (1, 2):
        scores = defaultdict(Counter)
        occ = Counter()
        for t in with_pua:
            puas = {c for c in t if PUA <= ord(c) < PUA + 256}
            if rnd == 1 and len(puas) > 1:
                continue
            for p in puas:
                occ[p] += 1
                others = {q: best.get(q, (fallback(holes_by_pua[q][1]),))[0] for q in puas if q != p}
                base = "".join(others.get(c, c) for c in t)
                for cand in CANDIDATES + [fallback(holes_by_pua[p][1])]:
                    w = base.replace(p, cand).lower()
                    if w in words:
                        scores[p][cand] += 1
        for p in holes_by_pua:
            ranked = scores[p].most_common()
            if ranked:
                # tie-break by corpus frequency of the words the candidate produces
                top = ranked[0][1]
                tied = [c for c, s in ranked if s == top]
                win = max(tied, key=lambda c: sum(freq[t.replace(p, c).lower()] for t in with_pua if p in t))
                runner = next((f"{c}:{s}" for c, s in ranked if c != win), None)
                best[p] = (win, top, occ[p], runner)
            elif p not in best:
                best[p] = (fallback(holes_by_pua[p][1]), 0, occ[p], None)
    return best


def repair(doc_id, words, freq):
    os.makedirs(WORK, exist_ok=True)
    pdf = os.path.join(ROOT, "pdf", doc_id + ".pdf")
    raw = open(os.path.join(ROOT, "text", "raw", doc_id + ".txt"), encoding="utf-8").read()
    fonts = fonts_with_holes(pdf)
    holes = [(f["obj"], c) for f in fonts for c in f["holes"]]
    pua_of = {h: chr(PUA + i) for i, h in enumerate(holes)}
    holes_by_pua = {v: k for k, v in pua_of.items()}
    base_of = {f["obj"]: f["base"] for f in fonts}

    p1pdf = os.path.join(WORK, doc_id + ".pass1.pdf")
    patch(pdf, fonts, pua_of, p1pdf)
    pass1 = extract(p1pdf, os.path.join(WORK, doc_id + ".pass1.txt"))
    roundtrip = "".join(fallback(holes_by_pua[c][1]) if c in holes_by_pua else c for c in pass1)
    roundtrip_ok = roundtrip == raw

    best = vote(pass1, holes_by_pua, words, freq)
    mapping = {}
    font_map = []
    for p, (win, score, n, runner) in best.items():
        obj, code = holes_by_pua[p]
        fb = fallback(code)
        font_map.append({"font_obj": obj, "font": base_of[obj], "code": code, "shows_as": fb,
                         "glyphs": pass1.count(p), "occurrences": n, "repaired_to": win, "votes": score,
                         "runner_up": runner, "changed": win != fb})
        if win != fb:
            mapping[(obj, code)] = win
    p2pdf = os.path.join(WORK, doc_id + ".pass2.pdf")
    patch(pdf, fonts, mapping, p2pdf)
    fixed_raw = extract(p2pdf, os.path.join(WORK, doc_id + ".pass2.txt"))
    final, norm = normalize(fixed_raw)

    def wl_rate(t):
        ws = [w.lower() for w in re.findall(r"[A-Za-z]+", t)]
        return round(sum(w in words for w in ws) / len(ws), 4) if ws else None

    digits_raw = re.findall(r"\d+", raw)
    digits_p1 = re.findall(r"\d+", pass1)
    digits_final = re.findall(r"\d+", final)
    standin_digits = [c for c in pass1 if c in holes_by_pua and fallback(holes_by_pua[c][1]).isdigit()]
    checks = {
        "roundtrip_pass1_equals_raw": roundtrip_ok,
        "bad_tokens_raw": len(BAD.findall(raw)),
        "bad_tokens_final": len(BAD.findall(final)),
        "ti_raw": raw.count("ti"), "ti_final": final.count("ti"),
        "tion_raw": raw.count("tion"), "tion_final": final.count("tion"),
        "wordlist_rate_raw": wl_rate(raw), "wordlist_rate_final": wl_rate(final),
        "digit_runs_raw": len(digits_raw), "digit_runs_final": len(digits_final),
        "standin_digit_glyphs_removed": len(standin_digits),
        "digit_runs_final_equal_pass1": digits_final == digits_p1,
        "amounts_raw": re.findall(r"R\s?\d[\d ,.]*\d", raw),
        "amounts_final": re.findall(r"R\s?\d[\d ,.]*\d", final),
        "unresolved_holes": [m for m in font_map if m["votes"] == 0 and m["occurrences"] > 0],
    }
    checks["amounts_identical"] = checks["amounts_raw"] == checks["amounts_final"]
    with open(os.path.join(ROOT, "text", "final", doc_id + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(final)
    rec = {"doc_id": doc_id, "label": DAMAGED[doc_id], "fonts": [{"obj": f["obj"], "font": f["base"],
           "holes": f["holes"]} for f in fonts], "font_map": font_map, "normalize": norm, "checks": checks}
    with open(os.path.join(WORK, doc_id + ".json"), "w") as fh:
        json.dump(rec, fh, indent=1, ensure_ascii=False)
    return rec


def main():
    os.makedirs(os.path.join(ROOT, "text", "final"), exist_ok=True)
    words, freq = build_wordlist()
    print(f"wordlist: {len(words)} words", flush=True)
    for d in DAMAGED:
        r = repair(d, words, freq)
        c = r["checks"]
        print(f"{d}: roundtrip={c['roundtrip_pass1_equals_raw']} bad {c['bad_tokens_raw']}->{c['bad_tokens_final']} "
              f"ti {c['ti_raw']}->{c['ti_final']} tion {c['tion_raw']}->{c['tion_final']} "
              f"wordlist {c['wordlist_rate_raw']}->{c['wordlist_rate_final']} "
              f"digits {c['digit_runs_raw']}->{c['digit_runs_final']} (stand-ins {c['standin_digit_glyphs_removed']}, "
              f"equal_pass1={c['digit_runs_final_equal_pass1']}) amounts_identical={c['amounts_identical']} "
              f"unresolved={len(c['unresolved_holes'])}")
        for m in r["font_map"]:
            print(f"   {m['font_obj']:>3} {m['font']:<22} code {m['code']:>3} '{m['shows_as']}' glyphs={m['glyphs']:<3} words={m['occurrences']:<3}"
                  f" -> '{m['repaired_to']}' votes={m['votes']} runner_up={m['runner_up']}")


if __name__ == "__main__":
    main()
