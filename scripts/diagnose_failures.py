"""Explain each 'served HTML' failure: what did the site send instead of the file?

For every NFO failure in local/failures.jsonl whose reason is "served HTML", fetch (1 req/s):
  1. the fetch_url again, keeping the HTML (local/raw/nfo/failed/<doc_id>.served.html);
  2. the package's /download/<slug>/ page, if not already cached.
Prints doc_id + the page's visible message + what the package page lists. FAIS rows are never
printed with URLs. Writes local/failure-diagnosis.json for build.py.
Run: python3 -I scripts/diagnose_failures.py
"""
import json
import os
import re
import sys

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import polite  # noqa: E402
from census import cached_get, parse_download_page, slug_of  # noqa: E402

LOCAL = os.path.join(ROOT, "local")


KNOWN = ["No file is attached with this package!", "Login is required to access this page"]


def visible_message(html):
    for k in KNOWN:
        if k in html:
            return k
    s = BeautifulSoup(html, "html.parser")
    for sel in [".alert", ".wpdm-alert", ".card-body", "h1", "title"]:
        el = s.select_one(sel)
        if el and el.get_text(strip=True):
            return re.sub(r"\s+", " ", el.get_text(" ", strip=True))[:200]
    return None


def main():
    plan = {json.loads(l)["doc_id"]: json.loads(l) for l in open(os.path.join(LOCAL, "plan.jsonl"))}
    fails = [json.loads(l) for l in open(os.path.join(LOCAL, "failures.jsonl")) if l.strip()]
    out = {}
    for f in fails:
        row = plan.get(f["doc_id"])
        if not row or row["office"] != "NFO" or not f["reason"].startswith("served HTML"):
            continue
        status, body = cached_get(row["fetch_url"], f"nfo/failed/{row['doc_id']}.served.html",
                                  accept_status=(200, 403, 404))
        served = visible_message(body.decode("utf-8", "replace"))
        ps = slug_of(row["package_url"])
        _, pk = cached_get(row["package_url"], f"nfo/download/{ps}.html", accept_status=(200, 404))
        info = parse_download_page(pk.decode("utf-8", "replace"))
        out[row["doc_id"]] = {"served_message": served, "package_files": info["files"],
                              "package_wpdm_id": info["wpdm_id"], "login_required": info["login_required"],
                              "package_message": visible_message(pk.decode("utf-8", "replace"))}
        print(row["doc_id"], "|", served, "| package files:", len(info["files"]),
              "| login:", info["login_required"])
    with open(os.path.join(LOCAL, "failure-diagnosis.json"), "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
