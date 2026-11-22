"""Stage 1, step 1 — build the census plan from the sites' own enumerations.

NFO : docs-sitemap.xml (doc pages) + wpdmpro-sitemap.xml (download packages), joined through
      each doc page's /docs/<slug>.md twin (metadata + wpdm id). Never the documents-archive page.
FAIS: /determinations/ table (one row per determination, names in it), the annual-reports and
      newsletters pages, and the `complaints` (case-study) sitemap.

Writes (all under local/, which is gitignored because FAIS rows carry names):
  local/plan.jsonl          one planned file per line
  local/census-meta.json    enumeration counts, exclusions, orphans — the inputs to report.md
  local/fais-determination-rows.jsonl   the 509 table rows, RESTRICTED (complainant/respondent)

Every fetch is cached under local/raw/; re-running reuses the cache (resumable).
Run: python3 -I scripts/census.py   (from the repo root)
"""
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from urllib.parse import unquote, urljoin, urlparse

import yaml
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import polite  # noqa: E402

LOCAL = os.path.join(ROOT, "local")
RAW = os.path.join(LOCAL, "raw")

NFO = "https://nfosa.co.za"
FAIS = "https://www.faisombud.co.za"
FAIS_DET_LIST = FAIS + "/determinations/"

SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def cached_get(url, relpath, *, accept_status=(200,)):
    """Fetch url once; cache body at local/raw/<relpath>. Returns (status, bytes) or raises."""
    path = os.path.join(RAW, relpath)
    meta = path + ".meta.json"
    if os.path.exists(path) and os.path.exists(meta):
        with open(meta) as f:
            m = json.load(f)
        with open(path, "rb") as f:
            return m["status"], f.read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    r = polite.get(url, accept_status=accept_status)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, path)
    with open(meta, "w") as f:
        json.dump({"url": url, "final_url": r.url, "status": r.status_code,
                   "content_type": r.headers.get("content-type")}, f)
    return r.status_code, r.content


def sitemap_locs(xml_bytes):
    root = ET.fromstring(xml_bytes)
    return [e.text.strip() for e in root.findall("sm:url/sm:loc", SM_NS)]


def slug_of(url):
    return urlparse(url).path.rstrip("/").split("/")[-1]


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def slugify(s, maxlen=60):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:maxlen].rstrip("-")


# ---------------------------------------------------------------------------- NFO

NFO_DIVISIONS = [  # (prefix of the .md `category`, division code)
    ("Ombudsman for Long-Term Insurance", "OLTI"),
    ("Ombudsman for Long Term Insurance", "OLTI"),
    ("Ombudsman for Banking Services", "OBS"),
    ("Ombudsman for Short-Term Insurance", "OSTI"),
    ("Ombudsman for Short Term Insurance", "OSTI"),
    ("Credit Ombud", "CO"),
    ("Office of the Credit Ombudsman", "CO"),
    ("National Financial Ombud", "NFO"),
]


def nfo_division(category, slug, title=None):
    """From the source's own words only: the .md category, else the slug/title text.
    Never from wpdm-id adjacency or other inference; unmapped stays None."""
    for prefix, code in NFO_DIVISIONS:
        if category and category.lower().startswith(prefix.lower()):
            return code
    s = (slug + " " + (title or "")).lower()
    for key, code in (("nfo-", "NFO"), ("olti", "OLTI"), ("long-term-insurance", "OLTI"),
                      ("ombuzz", "OLTI"),  # Ombuzz is filed under OLTI / Newsletters on every doc page
                      ("obs", "OBS"), ("osti", "OSTI"), ("short-term-insurance", "OSTI"),
                      ("credit-ombud", "CO"), ("final-determination", "OLTI")):
        if s.startswith(key) or key in s:
            return code
    return None


def nfo_doc_type(category, slug, title):
    c = (category or "").lower()
    s = (slug + " " + (title or "")).lower()
    if "final determination" in c or "final-determination" in s:
        return "determination"
    if "financial-statements" in s or "financial statements" in s:
        return "financial_statements"
    if "trend-report" in s or "trend report" in s:
        return "trend_report"
    if "annual report" in c or "annual-report" in s:
        return "annual_report"
    return "digest"  # case studies, bulletins, Briefcase, Ombuzz, guides: the office's own retelling


def nfo_period(slug, title, doc_type):
    s = slug + " " + (title or "")
    m = re.search(r"jan-jun-(20\d\d)", s)
    if m:
        return f"{m.group(1)}-01/{m.group(1)}-06", int(m.group(1))
    m = re.search(r"(?<!\d)(19|20)(\d\d)(?!\d)", s)
    if m:
        y = int(m.group(1) + m.group(2))
        return str(y), y
    return None, None


def parse_md_twin(text):
    """Return (front_matter dict, [cards]) where card = {download_url, files, viewer_id}."""
    fm = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    body = text
    if m:
        body = text[m.end():]
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            for line in m.group(1).splitlines():
                mm = re.match(r"^(\w+):\s*\"?(.*?)\"?$", line)
                if mm:
                    fm[mm.group(1)] = mm.group(2)
    cards = []
    # each download card: ### [Title](https://nfosa.co.za/download/<slug>/) ... N file(s) ... viewer
    parts = re.split(r"(?m)^### \[", body)
    for part in parts[1:]:
        dm = re.search(r"\]\((https?://(?:www\.)?nfosa\.co\.za/download/[^)\s]+)\)", part)
        if not dm:
            continue
        fm_files = re.search(r"(\d+)\s+file\(s\)", part)
        vm = re.search(r"__wpdm_pdf_viewer=(\d+)", part)
        cards.append({
            "download_url": dm.group(1).replace("://www.", "://"),
            "files": int(fm_files.group(1)) if fm_files else None,
            "viewer_id": int(vm.group(1)) if vm else None,
        })
    return fm, cards


def parse_download_page(html):
    """Return {wpdm_id, title, modified, files:[{filename, ind}]} from a /download/<slug>/ page."""
    soup = BeautifulSoup(html, "html.parser")
    ids = Counter(int(x) for x in re.findall(r"wpdmdl=(\d+)", html))
    wpdm_id = ids.most_common(1)[0][0] if ids else None
    og = soup.find("meta", property="og:title")
    mod = soup.find("meta", property="article:modified_time")
    files = []
    seen = set()
    for a in soup.find_all("a", class_="inddl"):
        href = a.get("href", "")
        q = dict(re.findall(r"[?&](ind|filename|wpdmdl)=([^&]*)", href))
        key = (q.get("ind"), q.get("filename"))
        if key in seen:
            continue
        seen.add(key)
        files.append({"filename": unquote(q.get("filename", "")), "ind": q.get("ind")})
    title = og["content"].replace(" | NFOSA", "").strip() if og and og.get("content") else None
    login = "Login is required to access this page" in html
    return {"wpdm_id": None if login else wpdm_id, "title": title, "login_required": login,
            "modified": mod["content"] if mod and mod.get("content") else None, "files": files}


def census_nfo(meta):
    _, docs_xml = cached_get(NFO + "/docs-sitemap.xml", "nfo/docs-sitemap.xml")
    _, pk_xml = cached_get(NFO + "/wpdmpro-sitemap.xml", "nfo/wpdmpro-sitemap.xml")
    doc_locs = sitemap_locs(docs_xml)
    pk_locs = sitemap_locs(pk_xml)
    meta["nfo"] = {"docs_sitemap_locs": len(doc_locs), "wpdmpro_sitemap_locs": len(pk_locs),
                   "docs_sitemap_unique": len(set(doc_locs)), "wpdmpro_sitemap_unique": len(set(pk_locs))}

    pk_slugs = [slug_of(u) for u in pk_locs]
    pk_set = set(pk_slugs)

    # 1. every doc page's .md twin
    doc_pages = {}  # doc slug -> {fm, cards, status}
    md_fail = []
    for i, u in enumerate(doc_locs, 1):
        slug = slug_of(u)
        try:
            status, body = cached_get(f"{NFO}/docs/{slug}.md", f"nfo/md/{slug}.md",
                                      accept_status=(200, 404))
        except polite.FetchError as e:
            md_fail.append({"doc_page": u, "reason": e.reason})
            continue
        if status != 200 or not body.lstrip().startswith(b"---"):
            md_fail.append({"doc_page": u, "reason": f"md twin HTTP {status} / not front matter"})
            doc_pages[slug] = {"url": u, "fm": {}, "cards": [], "md_ok": False}
            continue
        fm, cards = parse_md_twin(body.decode("utf-8", "replace"))
        doc_pages[slug] = {"url": u, "fm": fm, "cards": cards, "md_ok": True}
        if i % 50 == 0:
            print(f"  nfo md {i}/{len(doc_locs)}", flush=True)
    meta["nfo"]["md_twin_failures"] = md_fail

    # 2. packages: what the .md twins tell us
    pkg = {}  # download slug -> info
    for dslug, d in doc_pages.items():
        for c in d["cards"]:
            ps = slug_of(c["download_url"])
            p = pkg.setdefault(ps, {"slug": ps, "doc_pages": [], "viewer_ids": set(), "files_md": set(),
                                    "in_sitemap": ps in pk_set})
            p["doc_pages"].append(d["url"])
            if c["viewer_id"]:
                p["viewer_ids"].add(c["viewer_id"])
            if c["files"] is not None:
                p["files_md"].add(c["files"])
    for ps in pk_slugs:
        pkg.setdefault(ps, {"slug": ps, "doc_pages": [], "viewer_ids": set(), "files_md": set(),
                            "in_sitemap": True})

    # 3. download pages only where the .md cannot settle id + single file
    dl_fail = []
    for ps, p in sorted(pkg.items()):
        single = p["files_md"] == {1} and len(p["viewer_ids"]) == 1
        if single:
            p["wpdm_id"] = next(iter(p["viewer_ids"]))
            p["files"] = [{"filename": None, "ind": None}]
            p["id_source"] = "md_twin"
            continue
        try:
            status, body = cached_get(f"{NFO}/download/{ps}/", f"nfo/download/{ps}.html",
                                      accept_status=(200, 404))
        except polite.FetchError as e:
            dl_fail.append({"package": ps, "reason": e.reason})
            p["wpdm_id"] = None
            p["files"] = []
            continue
        if status != 200:
            dl_fail.append({"package": ps, "reason": f"download page HTTP {status}"})
            p["wpdm_id"], p["files"] = None, []
            continue
        info = parse_download_page(body.decode("utf-8", "replace"))
        p["wpdm_id"] = info["wpdm_id"]
        p["files"] = info["files"] or [{"filename": None, "ind": None}]
        p["dl_title"] = info["title"]
        p["dl_modified"] = info["modified"]
        p["login_required"] = info["login_required"]
        p["id_source"] = "download_page"
    meta["nfo"]["download_page_failures"] = dl_fail

    # 4. plan rows, one per file
    rows = []
    for ps, p in sorted(pkg.items(), key=lambda kv: (kv[1].get("wpdm_id") or 0, kv[0])):
        if not p.get("wpdm_id"):
            continue
        first_doc = p["doc_pages"][0] if p["doc_pages"] else None
        d = doc_pages.get(slug_of(first_doc)) if first_doc else None
        fm = d["fm"] if d else {}
        title = fm.get("title") or p.get("dl_title")
        category = fm.get("category")
        category_source = "md_twin" if category else None
        if not category:  # orphan: inherit from a sibling package that differs only by a -N suffix
            base = re.sub(r"-\d+$", "", ps)
            for sib in (base, base + "-2", base + "-3", ps + "-2", ps + "-3"):
                sp = pkg.get(sib)
                if sib != ps and sp and sp["doc_pages"]:
                    sd = doc_pages.get(slug_of(sp["doc_pages"][0]))
                    if sd and sd["fm"].get("category"):
                        category, category_source = sd["fm"]["category"], f"sibling:{sib}"
                        break
        division = nfo_division(category, ps, title)
        doc_type = nfo_doc_type(category, ps, title)
        period, year = nfo_period(ps, title, doc_type)
        multi = len(p["files"]) > 1
        for n, f in enumerate(p["files"], 1):
            doc_id = f"nfo-{p['wpdm_id']}" + (f"-{n}" if multi else "")
            if multi:
                fetch = (f"{NFO}/download/{ps}/?ind={f['ind']}&filename="
                         f"{f['filename']}&wpdmdl={p['wpdm_id']}")
            else:
                fetch = f"{NFO}/?wpdmdl={p['wpdm_id']}"
            rows.append({
                "doc_id": doc_id, "office": "NFO", "division": division, "doc_type": doc_type,
                "title": title, "period_covered": period, "year": year, "language": "en",
                "url": first_doc or f"{NFO}/download/{ps}/",
                "fetch_url": fetch, "package_url": f"{NFO}/download/{ps}/",
                "wpdm_id": p["wpdm_id"], "package_file_index": n if multi else None,
                "source_filename": f["filename"], "doc_pages": p["doc_pages"],
                "category": category, "category_source": category_source,
                "tags": fm.get("tags"), "updated": fm.get("updated"),
                "in_wpdmpro_sitemap": p["in_sitemap"], "snapshot_kind": "file",
                "restricted_fields": [],
            })

    # 5. doc pages with no download card carry their content in the page itself (OBS case
    #    studies etc.): snapshot the page as HTML, one row each.
    pages_without_pkg = [d["url"] for d in doc_pages.values() if not d["cards"]]
    for u in pages_without_pkg:
        ds = slug_of(u)
        fm = doc_pages[ds]["fm"]
        category = fm.get("category")
        title = fm.get("title")
        period, year = nfo_period(ds, title, "digest")
        rows.append({
            "doc_id": f"nfo-doc-{slugify(ds, 80)}", "office": "NFO",
            "division": nfo_division(category, ds, title), "doc_type": "digest",
            "title": title, "period_covered": period, "year": year, "language": "en",
            "url": u, "fetch_url": u, "package_url": None, "wpdm_id": None,
            "doc_pages": [u], "category": category, "category_source": "md_twin" if category else None,
            "tags": fm.get("tags"), "updated": fm.get("updated"),
            "in_wpdmpro_sitemap": None, "snapshot_kind": "html", "restricted_fields": [],
        })

    # 6. reconciliation facts for the report
    pk_without_page = sorted(ps for ps, p in pkg.items() if p["in_sitemap"] and not p["doc_pages"])
    linked_not_in_sm = sorted(ps for ps, p in pkg.items() if not p["in_sitemap"])
    multi_pkgs = sorted(ps for ps, p in pkg.items() if len(p.get("files") or []) > 1)
    meta["nfo"].update({
        "doc_pages_without_package": pages_without_pkg,
        "packages_without_doc_page": pk_without_page,
        "packages_linked_but_not_in_sitemap": linked_not_in_sm,
        "multi_file_packages": {ps: len(pkg[ps]["files"]) for ps in multi_pkgs},
        "packages_total": len(pkg),
        "packages_without_id": sorted(ps for ps, p in pkg.items() if not p.get("wpdm_id")),
        "packages_login_required": sorted(ps for ps, p in pkg.items() if p.get("login_required")),
        "doc_pages_sharing_a_package": {ps: len(p["doc_pages"]) for ps, p in pkg.items()
                                        if len(p["doc_pages"]) > 1},
        "planned_files": len(rows),
    })
    return rows


# ---------------------------------------------------------------------------- FAIS

FAIS_LANGS = {
    "zulu": "zu", "isizulu": "zu", "xhosa": "xh", "isixhosa": "xh", "sesotho": "st", "sotho": "st",
    "setswana": "tn", "setswanna": "tn", "tswana": "tn", "sepedi": "nso", "tshivenda": "ve",
    "venda": "ve", "xitsonga": "ts", "isindebele": "nr", "isindevele": "nr", "ndebele": "nr",
    "siswati": "ss", "swati": "ss", "afrikaans": "af", "english": "en",
}


def fais_language(text):
    t = text.lower()
    for k in sorted(FAIS_LANGS, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){k}(?![a-z])", t):
            return FAIS_LANGS[k]
    return "en"


def fais_fy_from_date(d):
    """FAIS fiscal year runs April–March. 20250716 -> '2025/26'."""
    if not d or not re.fullmatch(r"\d{8}", d):
        return None
    y, mth = int(d[:4]), int(d[4:6])
    start = y if mth >= 4 else y - 1
    return f"{start}/{str(start + 1)[2:]}"


def census_fais(meta):
    _, det_html = cached_get(FAIS_DET_LIST, "fais/determinations.html")
    _, det_sm = cached_get(FAIS + "/wp-sitemap-posts-determination-1.xml",
                           "fais/wp-sitemap-posts-determination-1.xml")
    _, cs_sm = cached_get(FAIS + "/wp-sitemap-posts-complaints-1.xml",
                          "fais/wp-sitemap-posts-complaints-1.xml")
    _, ar_html = cached_get(FAIS + "/publications/annual-reports/", "fais/annual-reports.html")
    _, nl_html = cached_get(FAIS + "/publications/newsletters/", "fais/newsletters.html")

    # --- determinations table (RESTRICTED content: names)
    soup = BeautifulSoup(det_html.decode("utf-8", "replace"), "html.parser")
    table = soup.find("table", id="myDeterminations")
    headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
    trs = [tr for tr in table.find_all("tr") if tr.find("td")]
    table_rows = []
    by_file = defaultdict(list)  # filename -> [(row_index, link_label)]
    for i, tr in enumerate(trs):
        tds = tr.find_all("td")
        cells = [td.get_text(" ", strip=True) for td in tds]
        links = []
        for a in tds[-1].find_all("a", href=True):
            href = urljoin(FAIS_DET_LIST, a["href"])
            fn = unquote(urlparse(href).path.split("/")[-1])
            links.append({"href": href, "filename": fn, "label": a.get_text(" ", strip=True)})
            by_file[fn].append((i, a.get_text(" ", strip=True)))
        table_rows.append({
            "row_index": i, "restricted": True,
            "fiscal_year": cells[0] or None, "category": cells[1] or None,
            "complainant": cells[2] or None, "respondent": cells[3] or None,
            "date_raw": cells[4] or None,
            "files": [{"filename_sha256": sha256_text(l["filename"]), "label": l["label"],
                       "filename": l["filename"], "href": l["href"]} for l in links],
        })
    os.makedirs(LOCAL, exist_ok=True)
    with open(os.path.join(LOCAL, "fais-determination-rows.jsonl"), "w") as f:
        for r in table_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    rows = []
    href_of = {}
    for r in table_rows:
        for l in r["files"]:
            href_of[l["filename"]] = l["href"]
    for fn, refs in sorted(by_file.items(), key=lambda kv: kv[1][0][0]):
        src_rows = [table_rows[i] for i, _ in refs]
        labels = sorted({lab for _, lab in refs})
        first = src_rows[0]
        d = first["date_raw"] if first["date_raw"] and re.fullmatch(r"\d{8}", first["date_raw"]) else None
        fh = sha256_text(fn)
        rows.append({
            "doc_id": f"fais-det-{fh[:12]}", "office": "FAIS", "division": "FAIS",
            "doc_type": "recommendation" if labels == ["Recommendation"] else "determination",
            "title": None,  # FAIS titles are "<complainant> v <respondent>": restricted
            "period_covered": f"{d[:4]}-{d[4:6]}-{d[6:]}" if d else None,
            "year": int(d[:4]) if d else None,
            "fiscal_year": first["fiscal_year"] or fais_fy_from_date(d),
            "category": first["category"], "language": "en",
            "url": FAIS_DET_LIST, "filename_sha256": fh,
            "fetch_url": href_of[fn],
            "listing_row_indices": [i for i, _ in refs], "link_labels": labels,
            "date_raw_ok": bool(d),
            "snapshot_kind": "file",
            "restricted": {"restricted": True, "filename": fn,
                           "parties": [{"complainant": t["complainant"], "respondent": t["respondent"]}
                                       for t in src_rows]},
            "restricted_fields": ["fetch_url", "restricted"],
        })

    det_sm_locs = sitemap_locs(det_sm)
    labels_ct = Counter(l["label"] for r in table_rows for l in r["files"])
    all_links = [l["filename"] for r in table_rows for l in r["files"]]
    bad_dates = [r["row_index"] for r in table_rows
                 if not (r["date_raw"] and re.fullmatch(r"\d{8}", r["date_raw"]))]
    meta["fais"] = {
        "table_headers": headers, "table_rows": len(table_rows),
        "table_links": len(all_links), "unique_files": len(by_file),
        "link_labels": dict(labels_ct),
        "files_per_row": dict(Counter(len(r["files"]) for r in table_rows)),
        "files_shared_across_rows": sum(1 for v in by_file.values() if len({i for i, _ in v}) > 1),
        "files_repeated_within_row": sum(1 for v in by_file.values()
                                         if len(v) > len({i for i, _ in v})),
        "rows_without_file": sum(1 for r in table_rows if not r["files"]),
        "rows_with_unparseable_date": len(bad_dates),
        "rows_blank_fiscal_year": sum(1 for r in table_rows if not r["fiscal_year"]),
        "determination_sitemap_locs": len(det_sm_locs),
        "category_counts": dict(Counter(r["category"] or "(blank)" for r in table_rows)),
    }

    # --- annual reports + newsletters: links under the section heading; footer links excluded
    def section_links(html, heading):
        s = BeautifulSoup(html.decode("utf-8", "replace"), "html.parser")
        keep, footer = [], []
        for a in s.find_all("a", href=True):
            if ".pdf" not in a["href"].lower():
                continue
            h = a.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
            ht = h.get_text(" ", strip=True) if h else ""
            item = {"href": urljoin(FAIS, a["href"]), "text": a.get_text(" ", strip=True)}
            (keep if ht == heading else footer).append(item)
        return keep, footer

    ar, ar_footer = section_links(ar_html, "Annual Reports")
    nl, nl_footer = section_links(nl_html, "Newsletters")
    footer = {x["href"]: x["text"] for x in ar_footer + nl_footer}
    meta["fais"]["annual_report_links"] = len(ar)
    meta["fais"]["newsletter_links"] = len(nl)
    meta["fais"]["excluded_footer_links"] = [{"url": u, "text": t} for u, t in footer.items()]

    seen = set()
    for x in ar:
        if x["href"] in seen:
            continue
        seen.add(x["href"])
        m = re.search(r"(20\d\d)\s*[/-]\s*(20)?(\d\d)", x["text"])
        start = int(m.group(1)) if m else None
        fy = f"{start}/{m.group(3)}" if m else None
        rows.append({
            "doc_id": f"fais-ar-{start}-{m.group(3)}" if m else f"fais-ar-{slugify(x['text'])}",
            "office": "FAIS", "division": "FAIS", "doc_type": "annual_report",
            "title": x["text"], "period_covered": fy, "year": start, "fiscal_year": fy,
            "language": "en", "url": FAIS + "/publications/annual-reports/", "fetch_url": x["href"],
            "source_filename": unquote(urlparse(x["href"]).path.split("/")[-1]),
            "snapshot_kind": "file", "restricted_fields": [],
        })
    used = Counter()
    for x in nl:
        if x["href"] in seen:
            continue
        seen.add(x["href"])
        base = "fais-nl-" + slugify(x["text"].replace("Newsletter", "").replace("–", " "), 48)
        used[base] += 1
        doc_id = base if used[base] == 1 else f"{base}-{used[base]}"
        ym = re.search(r"(20\d\d)", x["text"]) or re.search(r"(20\d\d)", x["href"])
        rows.append({
            "doc_id": doc_id, "office": "FAIS", "division": "FAIS", "doc_type": "newsletter",
            "title": x["text"], "period_covered": ym.group(1) if re.search(r"20\d\d", x["text"]) else None,
            "year": int(ym.group(1)) if re.search(r"20\d\d", x["text"]) else None,
            "language": fais_language(x["text"]),
            "url": FAIS + "/publications/newsletters/", "fetch_url": x["href"],
            "source_filename": unquote(urlparse(x["href"]).path.split("/")[-1]),
            "snapshot_kind": "file", "restricted_fields": [],
        })

    # --- case studies (HTML pages, `complaints` post type)
    cs_locs = sitemap_locs(cs_sm)
    meta["fais"]["case_study_sitemap_locs"] = len(cs_locs)
    for u in cs_locs:
        s = slug_of(u)
        rows.append({
            "doc_id": f"fais-cs-{slugify(s, 80)}", "office": "FAIS", "division": "FAIS",
            "doc_type": "digest", "title": None, "period_covered": None, "year": None,
            "language": "en", "url": u, "fetch_url": u, "snapshot_kind": "html",
            "restricted_fields": [],
        })
    return rows


def main():
    meta = {}
    print("NFO census…", flush=True)
    rows = census_nfo(meta)
    print(f"  {len(rows)} NFO files planned", flush=True)
    print("FAIS census…", flush=True)
    frows = census_fais(meta)
    print(f"  {len(frows)} FAIS files planned", flush=True)
    rows += frows
    ids = Counter(r["doc_id"] for r in rows)
    dup = [k for k, v in ids.items() if v > 1]
    if dup:
        raise SystemExit(f"duplicate doc_ids: {dup[:10]}")
    meta["census_requests"] = polite.request_count
    with open(os.path.join(LOCAL, "plan.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(LOCAL, "census-meta.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False, default=sorted)
    print(f"plan: {len(rows)} files; requests this run: {polite.request_count}")


if __name__ == "__main__":
    main()
