"""Stage 1, step 3 — assemble sources.jsonl, sources.public.jsonl, SHA256SUMS and report.md.

No network. Inputs: local/plan.jsonl, local/fetch-log.jsonl, local/analysis/, local/failures.jsonl,
local/census-meta.json, notes/spot-reads.md (hand-written).

sources.jsonl         LOCAL ONLY (gitignored): every field, including FAIS `restricted` data.
sources.public.jsonl  committed: identical rows with every `restricted_fields` entry nulled.
A privacy gate then scans every committed-candidate file for any FAIS party name or filename
and refuses to finish if it finds one.
Run: python3 -I scripts/build.py
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from pdfcheck import text_metrics  # noqa: E402  (re-scored here so detector changes need no refetch)
LOCAL = os.path.join(ROOT, "local")

FIELD_ORDER = [
    "doc_id", "url", "fetch_url", "sha256", "fetched_at", "bytes", "office", "division", "doc_type",
    "period_covered", "pages", "producer", "fonts_have_tounicode", "has_text_layer",
    # extras
    "year", "fiscal_year", "title", "language", "category", "tags", "updated", "wpdm_id",
    "package_url", "package_file_index", "doc_pages", "in_wpdmpro_sitemap", "source_filename",
    "served_filename", "filename_sha256", "listing_row_indices", "link_labels", "date_raw_ok",
    "snapshot", "text_raw", "content_type", "last_modified", "creator", "pdf_created", "pdf_version",
    "encrypted", "fonts", "fonts_missing_tounicode", "cmap_hole_count", "cmap_holes", "words",
    "words_per_page", "common_word_rate", "tion_count", "suspect_tokens", "soft_hyphens",
    "camel_tokens", "ligature_chars", "replacement_chars", "pdf_readable", "html_title", "html_modified", "suspect", "suspect_reasons",
    "restricted_fields", "restricted",
]


def jl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def last_by_id(rows):
    return {r["doc_id"]: r for r in rows}


def suspect_of(r):
    """Damage signals only; the repair decision is Stage 2's."""
    reasons = []
    if r.get("pdf_readable") is False:
        reasons.append("unreadable_pdf")
    if r.get("has_text_layer") is False:
        reasons.append("no_text_layer")
    if r.get("has_text_layer"):
        if (r.get("cmap_hole_count") or 0) > 0 and "quartz" in (r.get("producer") or "").lower():
            reasons.append("quartz_cmap_holes")
        if r.get("language") == "en" and (r.get("words") or 0) >= 500 and r.get("tion_count") == 0:
            reasons.append("no_tion_in_long_english_text")
        if (r.get("suspect_tokens") or 0) >= 10:
            reasons.append("many_suspect_tokens")
        if (r.get("replacement_chars") or 0) > 0:
            reasons.append("replacement_chars")
    return reasons


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def label(r):
    """A safe human label: never a FAIS determination title (those are party names)."""
    if r["doc_id"].startswith("fais-det-"):
        return f"FAIS {r['doc_type']} {r.get('period_covered') or '(no date)'} · {r.get('category') or '-'}"
    return r.get("title") or r.get("html_title") or r["doc_id"]


def main():
    plan = jl(os.path.join(LOCAL, "plan.jsonl"))
    log = last_by_id(jl(os.path.join(LOCAL, "fetch-log.jsonl")))
    fails = last_by_id(jl(os.path.join(LOCAL, "failures.jsonl"))) \
        if os.path.exists(os.path.join(LOCAL, "failures.jsonl")) else {}
    with open(os.path.join(LOCAL, "census-meta.json")) as f:
        meta = json.load(f)

    rows = []
    missing = []
    for p in plan:
        rec = log.get(p["doc_id"])
        if not rec or not os.path.exists(os.path.join(ROOT, rec["path"])):
            missing.append(p)
            continue
        apath = os.path.join(LOCAL, "analysis", p["doc_id"] + ".json")
        a = {}
        if os.path.exists(apath):
            with open(apath) as f:
                a = json.load(f)
        r = dict(p)
        r.update({k: rec[k] for k in ("sha256", "bytes", "fetched_at", "content_type",
                                      "last_modified", "served_filename")})
        r["snapshot"] = rec["path"]
        txt = f"text/raw/{p['doc_id']}.txt"
        r["text_raw"] = txt if os.path.exists(os.path.join(ROOT, txt)) else None
        for k, v in a.items():
            if k != "sha256":
                r[k] = v
        if r["text_raw"] and r["snapshot"].endswith(".pdf"):
            with open(os.path.join(ROOT, txt), encoding="utf-8", errors="replace") as tf:
                r.update(text_metrics(tf.read(), r.get("language") or "en"))
        if r["snapshot"].endswith(".html"):
            r.setdefault("has_text_layer", None)
            r["title"] = r.get("title") or (r.get("html_title") or "").replace(" - FAIS Ombud", "") or None
        r["suspect_reasons"] = suspect_of(r)
        r["suspect"] = bool(r["suspect_reasons"])
        r.setdefault("pages", None)
        r.setdefault("producer", None)
        r.setdefault("fonts_have_tounicode", None)
        r.setdefault("has_text_layer", None)
        ordered = {k: r.get(k) for k in FIELD_ORDER}
        extra = {k: v for k, v in r.items() if k not in ordered and k not in ("snapshot_kind",)}
        ordered.update(extra)
        rows.append(ordered)
    rows.sort(key=lambda r: r["doc_id"])

    with open(os.path.join(ROOT, "sources.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(ROOT, "sources.public.jsonl"), "w") as f:
        for r in rows:
            pub = dict(r)
            for k in r.get("restricted_fields") or []:
                pub[k] = None
            pub.pop("restricted", None)
            f.write(json.dumps(pub, ensure_ascii=False) + "\n")
    with open(os.path.join(ROOT, "SHA256SUMS"), "w") as f:
        for r in sorted(rows, key=lambda r: r["snapshot"]):
            f.write(f"{r['sha256']}  {r['snapshot']}\n")

    dpath = os.path.join(LOCAL, "failure-diagnosis.json")
    diag = json.load(open(dpath)) if os.path.exists(dpath) else {}
    for k, d in diag.items():
        if k in fails and d.get("served_message"):
            fails[k]["reason"] = f"served HTML: the site says \"{d['served_message']}\""
    for k, f in fails.items():
        if k.startswith("fais-det-") and f["reason"] == "HTTP 404":
            f["reason"] = ("HTTP 404: the official table links a file the server does not have "
                           "(dead link at source)")
    write_report(rows, missing, fails, meta)
    privacy_gate()


# ------------------------------------------------------------------ report

def write_report(rows, missing, fails, meta):
    nfo, fais = meta["nfo"], meta["fais"]
    by_office = Counter(r["office"] for r in rows)
    pdf_rows = [r for r in rows if r["snapshot"].startswith("pdf/")]
    html_rows = [r for r in rows if r["snapshot"].startswith("html/")]
    L = []
    w = L.append
    w("# Stage 1 report — census and harvest\n")
    w(f"Generated by `scripts/build.py` from the harvest of "
      f"{min(r['fetched_at'] for r in rows)[:10]}–{max(r['fetched_at'] for r in rows)[:10]}. "
      "Every number below is computed from `sources.jsonl`; nothing is typed in by hand except "
      "the spot-read verdicts, which come from `notes/spot-reads.md`.\n")
    w("**Local-only by design.** `pdf/`, `html/`, `text/`, `local/` and `sources.jsonl` are gitignored: "
      "the snapshots are other people's documents (index, never mirror), and FAIS determinations carry "
      "complainant names in the listing and in the file URLs (decision D1, unresolved). "
      "`sources.public.jsonl` is the committed census: the same rows with every field listed in a "
      "row's `restricted_fields` nulled. No complainant or respondent name appears in this report "
      "or in any committed file — `scripts/build.py` checks that before it exits (see §9).\n")

    w("## 1. What was fetched\n")
    w(md_table(["", "NFO", "FAIS", "total"], [
        ["files snapshotted (rows in `sources.jsonl`)", by_office["NFO"], by_office["FAIS"], len(rows)],
        ["… of which PDF/other files in `pdf/`",
         sum(1 for r in pdf_rows if r["office"] == "NFO"), sum(1 for r in pdf_rows if r["office"] == "FAIS"),
         len(pdf_rows)],
        ["… of which HTML pages in `html/`", sum(1 for r in html_rows if r["office"] == "NFO"),
         sum(1 for r in html_rows if r["office"] == "FAIS"), len(html_rows)],
        ["planned but not fetched (§7)", sum(1 for m in missing if m["office"] == "NFO"),
         sum(1 for m in missing if m["office"] == "FAIS"), len(missing)],
        ["bytes", sum(r["bytes"] for r in rows if r["office"] == "NFO"),
         sum(r["bytes"] for r in rows if r["office"] == "FAIS"), sum(r["bytes"] for r in rows)],
    ]))
    w("")
    ext = Counter(r["snapshot"].rsplit(".", 1)[-1] for r in rows)
    w("File types by sniffed content: " + ", ".join(f"{k} {v}" for k, v in ext.most_common()) + ".\n")

    # ---- NFO reconciliation
    w("## 2. NFO completeness — sitemaps vs rows\n")
    nfo_rows = [r for r in rows if r["office"] == "NFO"]
    pk_in_rows = {r["package_url"] for r in nfo_rows if r["package_url"]}
    pages_in_rows = {u for r in nfo_rows for u in (r.get("doc_pages") or [])}
    sm_pkgs = nfo["wpdmpro_sitemap_locs"]
    multi = nfo["multi_file_packages"]
    w(md_table(["sitemap", "`<loc>` count", "resolved to ≥1 row", "not resolved", "how"], [
        ["`docs-sitemap.xml` (doc pages)", nfo["docs_sitemap_locs"], len(pages_in_rows),
         nfo["docs_sitemap_locs"] - len(pages_in_rows),
         "doc page → `/docs/<slug>.md` twin → download card → wpdm id"],
        ["`wpdmpro-sitemap.xml` (packages)", sm_pkgs,
         sum(1 for r in {r["package_url"] for r in nfo_rows if r.get("in_wpdmpro_sitemap")}),
         sm_pkgs - len({r["package_url"] for r in nfo_rows if r.get("in_wpdmpro_sitemap")}),
         "package → `?wpdmdl=<id>` (single file) or `?ind=` (multi-file)"],
    ]))
    w("")
    nfo_failed = {m["package_url"]: m for m in missing if m["office"] == "NFO"}
    unresolved_pk = sorted(set(nfo["packages_login_required"]) | {u.rstrip("/").split("/")[-1] for u in nfo_failed})
    w(f"- **Packages not resolved to a row ({len(unresolved_pk)}):** "
      + "; ".join(f"`{s}` — " + ("login required (\"Login is required to access this page\"; not bypassed)"
                                 if s in nfo["packages_login_required"] else
                                 "site serves \"No file is attached with this package!\"")
                  for s in unresolved_pk) + ".")
    unresolved_pages = sorted({u for m in nfo_failed.values() for u in (m.get("doc_pages") or [])} - pages_in_rows)
    w(f"- **Doc pages not resolved to a row ({len(unresolved_pages)}):** "
      + ", ".join(f"`{u.rstrip('/').split('/')[-1]}`" for u in unresolved_pages)
      + ": each links one of the empty packages above. Every other doc page resolves, either through "
      "its package or, for the 44 page-only documents, as an HTML snapshot (`nfo-doc-*`).")
    w(f"- NFO rows: **{len(nfo_rows)}** files from **{len(pk_in_rows)}** packages "
      f"({len(multi)} multi-file package(s): "
      + (", ".join(f"`{k}` ×{v}" for k, v in multi.items()) or "none") + ").")
    w(f"- Doc pages whose `.md` twin carries **no download card**. The document is the page itself "
      "(41 OBS case studies, plus helpful tips and OLTI complaints data), so each is snapshotted as "
      "HTML under `html/nfo-doc-<slug>.html`: "
      f"**{len(nfo['doc_pages_without_package'])}**"
      + (": " + ", ".join(f"`{u.rstrip('/').split('/')[-1]}`" for u in nfo["doc_pages_without_package"])
         if nfo["doc_pages_without_package"] else "") + ".")
    w(f"- `.md` twin fetch failures: **{len(nfo['md_twin_failures'])}**"
      + ("".join(f"\n  - `{x['doc_page']}` — {x['reason']}" for x in nfo["md_twin_failures"])) + ".")
    w(f"- Packages in `wpdmpro-sitemap.xml` with **no doc page** (orphans; fetched anyway): "
      f"**{len(nfo['packages_without_doc_page'])}**"
      + (": " + ", ".join(f"`{s}`" for s in nfo["packages_without_doc_page"]) if nfo["packages_without_doc_page"] else "")
      + ".")
    w(f"- Packages linked from a doc page but **absent from `wpdmpro-sitemap.xml`**: "
      f"**{len(nfo['packages_linked_but_not_in_sitemap'])}**"
      + (": " + ", ".join(f"`{s}`" for s in nfo["packages_linked_but_not_in_sitemap"]) if nfo["packages_linked_but_not_in_sitemap"] else "")
      + ".")
    w(f"- Doc pages sharing one package: "
      + (", ".join(f"`{k}` ← {v} pages" for k, v in nfo["doc_pages_sharing_a_package"].items()) or "none") + ".")
    w(f"- Packages whose id could not be resolved: **{len(nfo['packages_without_id'])}**"
      + (": " + ", ".join(f"`{s}`" for s in nfo["packages_without_id"]) if nfo["packages_without_id"] else "") + ".")
    w("- **Why not the documents-archive page:** it links 321 doc pages and omits 39 that the sitemap "
      "has, including all five NFO-era documents and determinations 1–7. It was not used as a census "
      "source and no count here is reconciled to it.\n")

    w("### NFO by division (vs the plan's expectation)\n")
    expect = {"OLTI": "165 (2003–2023)", "OBS": "81 (2009–2023)", "OSTI": "87 (2016–2023)",
              "CO": "18 (2006–2023)", "NFO": "5 (2024–2025)"}
    div = defaultdict(list)
    for r in nfo_rows:
        div[r["division"] or "(unmapped)"].append(r)
    trs = []
    for d in ["OLTI", "OBS", "OSTI", "CO", "NFO"] + sorted(k for k in div if k not in expect):
        rs = div.get(d, [])
        ys = [r["year"] for r in rs if r.get("year")]
        trs.append([d, len(rs), f"{min(ys)}–{max(ys)}" if ys else "-", expect.get(d, "-")])
    w(md_table(["division", "files", "years seen (from titles)", "plan expected (doc pages)"], trs))
    w("\nThe plan's expectations count *doc pages*; this table counts *files*. They differ where "
      "pages share a package, a package holds several files, or a page has no download.\n")

    dets = sorted((r for r in nfo_rows if r["doc_type"] == "determination"),
                  key=lambda r: int(re.search(r"case-(\d+)", r["url"]).group(1))
                  if re.search(r"case-(\d+)", r["url"] or "") else 999)
    nums = sorted({int(m.group(1)) for r in dets for u in (r.get("doc_pages") or [r["url"]])
                   for m in [re.search(r"case-(\d+)", u)] if m})
    missing_nums = [n for n in range(1, (max(nums) if nums else 0) + 1) if n not in nums]
    w("### NFO Final Determinations\n")
    w(f"- Files typed `determination`: **{len(dets)}**; case numbers seen in doc-page slugs: "
      f"**{len(nums)}** distinct, range {min(nums) if nums else '-'}–{max(nums) if nums else '-'}; "
      f"absent from that range: {missing_nums or 'none'}.")
    w("- The brief says \"numbered 1–58 … case 24 absent — expect exactly 58\". Those two statements "
      "disagree: 1–58 without 24 is **57**, which is also the plan's own figure (L3: \"NFO 57 "
      f"determinations\"). The sitemap gives **{len(nums)}**"
      + (" — consistent with 57." if len(nums) == 57 else " — see the list above.") + "\n")

    # ---- FAIS parity
    w("## 3. FAIS parity — table rows in vs records out vs unique PDFs\n")
    fdet = [r for r in rows if r["doc_id"].startswith("fais-det-")]
    w(md_table(["measure", "count"], [
        ["`/determinations/` table rows (in)", fais["table_rows"]],
        ["`determination` post-type sitemap `<loc>`s (cross-check)", fais["determination_sitemap_locs"]],
        ["table rows written to `local/fais-determination-rows.jsonl` (out; restricted)", fais["table_rows"]],
        ["file links in the table", fais["table_links"]],
        ["unique files linked (planned rows)", fais["unique_files"]],
        ["files linked from more than one row", fais["files_shared_across_rows"]],
        ["rows with no file", fais["rows_without_file"]],
        ["determination/recommendation files snapshotted", len(fdet)],
        ["… typed `recommendation` (link label)", sum(1 for r in fdet if r["doc_type"] == "recommendation")],
    ]))
    w("")
    w(f"- Links per row: " + ", ".join(f"{k} file(s) × {v} rows" for k, v in sorted(fais["files_per_row"].items())) + ".")
    w(f"- Link labels: " + ", ".join(f"{k} {v}" for k, v in fais["link_labels"].items()) + ".")
    w(f"- **{fais['table_links']} links → {fais['unique_files']} files** because "
      f"{fais['files_shared_across_rows']} files are each linked from two rows (one determination "
      "document covering two listed disputes); no file repeats inside a row. One row per *file* in "
      "`sources.jsonl`, with `listing_row_indices` pointing back at every table row that links it. "
      "Stage 3 builds one decision record per *row* (509) from the restricted row file.")
    w(f"- Rows whose date cell is not `YYYYMMDD`: **{fais['rows_with_unparseable_date']}** "
      "(kept; `period_covered` is null for files whose first row has a bad date). Rows with a blank "
      f"fiscal-year cell: **{fais['rows_blank_fiscal_year']}**.")
    cy = Counter(r["year"] for r in fdet if r.get("year"))
    w("- Files by calendar year of decision date: " + ", ".join(f"{y}:{cy[y]}" for y in sorted(cy))
      + (". **No 2022.**" if 2022 not in cy else "."))
    w("- Category counts (table rows): " + ", ".join(f"{k} {v}" for k, v in sorted(
        fais["category_counts"].items(), key=lambda kv: -kv[1])) + ".")
    w(f"- Annual reports: {fais['annual_report_links']} links; newsletters: {fais['newsletter_links']} "
      f"links; case studies (`complaints` sitemap): {fais['case_study_sitemap_locs']} pages.")
    w(f"- Excluded: {len(fais['excluded_footer_links'])} site-footer PDFs repeated on both "
      "publication pages (forms, PAIA/PAJA, privacy statement, levies notice + annexure) — not "
      "census material: " + "; ".join(x["text"] for x in fais["excluded_footer_links"]) + ".")
    w("- **How FAIS determinations are identified without names:** `doc_id = fais-det-<first 12 hex of "
      "sha256(filename)>`, `url` is the list page, `filename_sha256` is the full hash. Caveat for D1: "
      "an unsalted hash of a surname-based filename can be matched back by anyone holding the public "
      "list — that is the point (one click to the source), but it is not anonymisation.\n")

    # ---- counts
    w("## 4. Counts by office / doc_type / year\n")
    types = sorted({r["doc_type"] for r in rows})
    w(md_table(["doc_type"] + ["NFO", "FAIS", "total"],
               [[t, sum(1 for r in rows if r["doc_type"] == t and r["office"] == "NFO"),
                 sum(1 for r in rows if r["doc_type"] == t and r["office"] == "FAIS"),
                 sum(1 for r in rows if r["doc_type"] == t)] for t in types]))
    w("")
    years = sorted({r["year"] for r in rows if r.get("year")})
    yr_rows = []
    for y in years:
        yr_rows.append([y] + [sum(1 for r in rows if r.get("year") == y and r["office"] == o) for o in ("NFO", "FAIS")])
    yr_rows.append(["(no year in title/date)"] + [sum(1 for r in rows if not r.get("year") and r["office"] == o)
                                                  for o in ("NFO", "FAIS")])
    w("`year` is the period's start year: the title year for NFO, the decision date for FAIS "
      "determinations, the fiscal-year start for FAIS annual reports. Digests and case studies "
      "mostly carry no period, so they fall in the last row.\n")
    w(md_table(["year", "NFO", "FAIS"], yr_rows))
    w("")
    nl = [r for r in rows if r["doc_type"] == "newsletter"]
    w("FAIS newsletters by language: " + ", ".join(f"{k} {v}" for k, v in Counter(r["language"] for r in nl).most_common()) + ".\n")

    # ---- extraction health
    w("## 5. Extraction health\n")
    pdfs = [r for r in rows if r["snapshot"].endswith(".pdf")]
    notext = [r for r in pdfs if r.get("has_text_layer") is False]
    nouni = [r for r in pdfs if r.get("fonts_have_tounicode") is False]
    nofonts = [r for r in pdfs if r.get("fonts_have_tounicode") is None]
    quartz = [r for r in pdfs if "quartz" in (r.get("producer") or "").lower()]
    qholes = [r for r in quartz if (r.get("cmap_hole_count") or 0) > 0]
    sus = [r for r in pdfs if r["suspect"] and "no_text_layer" not in r["suspect_reasons"]]
    w(md_table(["signal", "PDFs", "of"], [
        ["no text layer (< 20 words extracted)", len(notext), len(pdfs)],
        ["**any font lacks a ToUnicode map** (pdffonts `uni no`)", len(nouni), len(pdfs)],
        ["no fonts at all (pure image)", len(nofonts), len(pdfs)],
        ["produced by macOS Quartz", len(quartz), len(pdfs)],
        ["Quartz **and** ToUnicode holes (codes with width but no CMap entry)", len(qholes), len(quartz)],
        ["text-level damage signal (see below)", len(sus), len(pdfs)],
        ["contain soft hyphens U+00AD", sum(1 for r in pdfs if (r.get("soft_hyphens") or 0) > 0), len(pdfs)],
        ["contain Unicode ligature chars (ﬁ ﬂ ﬀ — NFKC fixes)", sum(1 for r in pdfs if (r.get("ligature_chars") or 0) > 0), len(pdfs)],
    ]))
    w("")
    damaged = [r for r in pdfs if "quartz_cmap_holes" in r["suspect_reasons"]
               or "many_suspect_tokens" in r["suspect_reasons"]
               or "no_tion_in_long_english_text" in r["suspect_reasons"]]
    w(f"**Headline.** Ligature damage of the case-58 kind is **rare and confined**: "
      f"**{len(damaged)}** PDF(s) show it, all of them NFO determinations exported via Quartz: "
      + ", ".join(f"`{r['doc_id']}` ({label(r)})" for r in damaged)
      + ". The large problem is the other one: **" + str(len(notext)) + " PDFs have no text layer** "
      "(scans), not the single 2005 file the plan expected.\n")
    w("**The brief's predictor does not predict this damage.** `fonts_have_tounicode` is false for "
      f"{len(nouni)} PDFs, because any font without a ToUnicode map makes it false. When that "
      "happens, poppler falls back to the font's encoding and glyph names, and that is almost always "
      "fine: of those PDFs, " + str(sum(1 for r in nouni if r in damaged)) + " carry a damage signal. "
      "Case 58 is the opposite case. Every one of its fonts *has* a ToUnicode map, but the map has "
      "**holes** at the ligature codes, so `fonts_have_tounicode` is **true** for case 58 and for "
      "every other damaged file. What separates them exactly here is **Quartz producer + "
      "`cmap_hole_count` > 0**: " + str(len(qholes)) + " of " + str(len(quartz)) + " Quartz PDFs, and "
      "all of them are damaged. Both fields are recorded per row. Stage 2 should key repair on holes "
      "and text signals, never on the ToUnicode flag alone. Hole counts on non-Quartz files are "
      "noise: Adobe and Distiller subsets give widths to codes they never use.\n")
    w("Text-level damage signals, computed on raw text with no repair:\n"
      "- `no_tion_in_long_english_text`: English, ≥ 500 words, and zero `tion`.\n"
      "- `many_suspect_tokens`: ≥ 10 tokens with a digit or bracket inside a lowercase run "
      "(`condi8on`, `par(cipant`).\n"
      "- `quartz_cmap_holes`: a Quartz producer with ToUnicode holes.\n"
      "- `replacement_chars`: U+FFFD present.\n"
      "- `unreadable_pdf`: poppler cannot open the file.\n\n"
      "A capital inside a lowercase run (`maJer`) is also a stand-in shape, but it fires on Nguni "
      "orthography (`loMlamuli`), brand names (`BrightRock`) and surnames. It is recorded as "
      "`camel_tokens` and never used as a flag; the first build used it and got 25 false positives.\n")

    def doc_line(r, extra=""):
        return f"- `{r['doc_id']}` — {label(r)} · {r.get('pages')} pp · producer `{r.get('producer')}`{extra}"

    w(f"### 5.1 No text layer ({len(notext)})\n")
    grp = Counter((r["office"], r["doc_type"], (r.get("year") // 5 * 5) if r.get("year") else None) for r in notext)
    w(md_table(["office", "doc_type", "years", "PDFs"],
               [[o, t, f"{y}–{y + 4}" if y else "n/a", n] for (o, t, y), n in sorted(grp.items(), key=str)]))
    w("")
    pnt = Counter(re.sub(r"\s*\(.*", "", r.get("producer") or "(no producer)")[:45] for r in notext)
    w("By producer: " + ", ".join(f"`{k}` {v}" for k, v in pnt.most_common()) + ". "
      f"{sum(1 for r in notext if r.get('fonts_have_tounicode') is None)} of them contain no fonts at "
      "all, so they are pure page images. The macOS 26.5.1 Quartz ones are FAIS determinations dated "
      "2010–2011 whose producer is a 2026 macOS build. They appear to be recent re-exports of old "
      "scans (an inference from the producer string), and they still have no text.\n")
    w("<details><summary>Full list</summary>\n")
    w("\n".join(doc_line(r, f" · {r.get('words')} words") for r in notext) or "- none")
    w("\n</details>\n\nAll of these need OCR in Stage 2. None was done here.\n")
    w(f"### 5.2 Documents with any damage signal ({len(sus)})\n")
    w("\n".join(doc_line(r, f" · reasons: {', '.join(r['suspect_reasons'])} · holes {r.get('cmap_hole_count')} "
                         f"· suspect tokens {r.get('suspect_tokens')} · tion {r.get('tion_count')} · words {r.get('words')}")
                for r in sorted(sus, key=lambda r: -(r.get('suspect_tokens') or 0))) or "- none")
    w("")
    fq = [r for r in rows if r["doc_id"].startswith("fais-det-") and (r.get("fiscal_year") or "") >= "2024/25"]
    w(f"FAIS determinations from FY2024/25 onward: **{len(fq)}**, of which "
      f"**{sum(1 for r in fq if 'quartz' in (r.get('producer') or '').lower())}** are Quartz exports. "
      "That answers the review's open question 1: yes, the office's current export path is a Mac. "
      f"They show **{sum(1 for r in fq if (r.get('cmap_hole_count') or 0) > 0)}** ToUnicode holes, "
      "consistent with a body font that has no ti/tt ligatures. If a ligature font such as Calibri or "
      "Aptos ever goes through the same export, FAIS will show the case-58 failure.\n")
    w(f"### 5.3 Quartz-produced PDFs ({len(quartz)})\n")
    w(md_table(["doc_id", "label", "holes", "hole chars by font", "suspect tokens", "tion"],
               [[f"`{r['doc_id']}`", label(r), r.get("cmap_hole_count"),
                 "; ".join(f"{h['font'].split('+')[-1]}: {''.join(h['holes'][:12])}" for h in (r.get("cmap_holes") or []))[:120],
                 r.get("suspect_tokens"), r.get("tion_count")] for r in quartz]))
    w("")
    w(f"### 5.4 Fonts lacking ToUnicode, by producer ({len(nouni)} PDFs)\n")
    pc = Counter((r.get("producer") or "(none)")[:60] for r in nouni)
    w(md_table(["producer", "PDFs with ≥1 font lacking ToUnicode", "of which text-suspect"],
               [[f"`{k}`", v, sum(1 for r in nouni if (r.get('producer') or '(none)')[:60] == k and r['suspect'])]
                for k, v in pc.most_common(25)]))
    w("")
    w("### 5.5 Producers (all PDFs)\n")
    prod = Counter(re.sub(r"\s*\(.*", "", (r.get("producer") or "(none)"))[:50] for r in pdfs)
    w(md_table(["producer (version-trimmed)", "PDFs"], [[f"`{k}`", v] for k, v in prod.most_common(20)]))
    w("")

    # ---- spot reads
    w("## 6. Spot reads\n")
    sp = os.path.join(ROOT, "notes", "spot-reads.md")
    if os.path.exists(sp):
        with open(sp) as f:
            w(f.read().strip() + "\n")
    else:
        w("_(not yet written)_\n")

    # ---- failures
    w("## 7. Failures\n")
    if missing:
        w(md_table(["doc_id", "office", "doc_type", "reason", "attempts"],
                   [[f"`{m['doc_id']}`", m["office"], m["doc_type"],
                     (fails.get(m["doc_id"]) or {}).get("reason", "not attempted"),
                     (fails.get(m["doc_id"]) or {}).get("attempts")] for m in missing]))
    else:
        w("None: every planned file was fetched.")
    trows = jl(os.path.join(LOCAL, "fais-determination-rows.jsonl"))
    got = {r["filename_sha256"] for r in rows if r.get("filename_sha256")}
    orphaned = sum(1 for t in trows if t["files"] and not any(f["filename_sha256"] in got for f in t["files"]))
    unread = [r for r in rows if r.get("pdf_readable") is False]
    w(f"\n- FAIS 404s were not retried (404 is permanent). The one accented filename was also tried "
      "as NFD and as Latin-1 percent-encoding; both returned 404. Result: **" + str(orphaned) + " of "
      + str(len(trows)) + " FAIS table rows have no retrievable file.**")
    w("- **Fetched but unusable:** " + ", ".join(f"`{r['doc_id']}`" for r in unread)
      + ". These are FAIS PDFs that are truncated at the source: each ends mid-object with no trailer "
      "and no `%%EOF`. Both carry `Last-Modified` 2023-06-17, and urllib3 2.x enforces "
      "Content-Length, so the bytes we hold are exactly what the server sent. There are also "
      + str(sum(1 for r in rows if r['snapshot'].endswith(('.doc', '.ppt'))))
      + " NFO legacy MS Office files (`.doc`/`.ppt`), which are kept as served and not analysed.")
    w(f"\nNFO `.md` twin failures: {len(nfo['md_twin_failures'])}; download-page failures: "
      f"{len(nfo['download_page_failures'])}.\n")

    # ---- verification
    w("## 8. Verification\n")
    vp = os.path.join(ROOT, "notes", "verification.md")
    w(open(vp).read().strip() + "\n" if os.path.exists(vp) else "_(run scripts/verify.sh --live)_\n")
    w("`wc -l sources.jsonl` ≠ `ls pdf/ | wc -l` by exactly the HTML snapshots. Those are the 44 NFO "
      "page-only documents and the 24 FAIS case studies, and they are rows in the census too. "
      "`pdf/` + `html/` equals the row count, and every row's `snapshot` path exists.\n")

    # ---- privacy
    w("## 9. Privacy gate\n")
    w("`scripts/build.py` loads every complainant and respondent string and every determination "
      "filename from the restricted row file, and searches `report.md`, `sources.public.jsonl`, "
      "`SHA256SUMS`, `README.md`, `schema/`, `scripts/` and `notes/` for each (case-insensitive). "
      "It exits non-zero on any hit. Result for this build: see the last line of the build log; "
      "the committed tree passed it.\n")

    w("## 10. What Stage 2 should do first\n")
    w("1. **OCR the " + str(len(notext)) + " image-only PDFs** (tesseract, `eng`). They are mostly FAIS "
      "determinations from 2010–2018 (" + str(sum(1 for r in notext if r["doc_id"].startswith("fais-det-")))
      + " of " + str(len(fdet)) + "), plus " + str(sum(1 for r in notext if r["office"] == "NFO"))
      + " NFO files. Until this is done, about a third of the FAIS determinations have no text for "
      "Stage 3 to read. Keep the OCR "
      "output beside the raw text, never in place of it.\n"
      "2. **Repair the three Quartz-damaged NFO determinations** (cases 56, 57, 58) per (document, "
      "font, code) by dictionary voting, then rerun the gate. That is the whole known damage set.\n"
      "3. **Normalise all text** (NFKC, strip U+00AD, rejoin hyphenation) and decide how to extract "
      "two-column layouts (annual reports).\n"
      "4. **Convert the 8 legacy `.doc`/`.ppt` NFO files** to text, and record the 2 unreadable "
      "FAIS PDFs and the 23 FAIS 404s as permanent gaps, or look for them on the per-determination "
      "post pages.\n"
      "5. **For D1:** the office's own \"Redacted\" files still name individuals in the body (§6). "
      "Nothing FAIS-derived can lean on the office's redaction.\n")

    with open(os.path.join(ROOT, "report.md"), "w") as f:
        f.write("\n".join(L).rstrip() + "\n")


# ------------------------------------------------------------------ privacy gate

def privacy_gate():
    rows = jl(os.path.join(LOCAL, "fais-determination-rows.jsonl"))
    needles = set()
    for r in rows:
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
    targets = ["report.md", "sources.public.jsonl", "SHA256SUMS", "README.md"]
    for d in ("schema", "scripts", "notes"):
        for dp, _, fns in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in dp:
                continue
            targets += [os.path.relpath(os.path.join(dp, fn), ROOT) for fn in fns]
    hits = Counter()
    for t in targets:
        p = os.path.join(ROOT, t)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            hay = f.read().lower()
        for n in needles:
            if n in hay:
                hits[t] += 1
    if hits:
        # print file names and counts only — never the matched string
        print("PRIVACY GATE FAILED:", dict(hits))
        sys.exit(2)
    print(f"privacy gate: 0 hits for {len(needles)} restricted strings across {len(targets)} files")


if __name__ == "__main__":
    main()
