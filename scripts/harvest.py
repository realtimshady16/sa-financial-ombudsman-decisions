"""Stage 1, step 2 — fetch every planned file once, hash it, snapshot it, analyse it.

Reads local/plan.jsonl. For each row:
  - skip the fetch if pdf/<doc_id>.<ext> (or html/<doc_id>.html) exists and its sha256 matches
    the last recorded fetch (resumable: a re-run never refetches a good file);
  - otherwise GET (1 req/s, <=2 retries), write atomically, append to local/fetch-log.jsonl;
  - analyse PDFs: pdfinfo, pdffonts, ToUnicode holes (qpdf), pdftotext -layout -> text/raw/.
Failures go to local/failures.jsonl (latest attempt per doc_id wins).

Logs print doc_ids only. FAIS determination URLs carry party names and are never printed.
Run: python3 -I scripts/harvest.py   (from the repo root)
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import polite  # noqa: E402
import pdfcheck  # noqa: E402

LOCAL = os.path.join(ROOT, "local")
FETCH_LOG = os.path.join(LOCAL, "fetch-log.jsonl")
FAILURES = os.path.join(LOCAL, "failures.jsonl")
ANALYSIS = os.path.join(LOCAL, "analysis")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl_last(path):
    out = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out[r["doc_id"]] = r
    return out


def append_jsonl(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def sanitize(reason):
    """Strip URLs/paths out of exception text: FAIS paths contain party names."""
    reason = re.sub(r"https?://\S+", "<url>", reason or "")
    reason = re.sub(r"url: \S+", "url: <path>", reason)
    reason = re.sub(r"/wp-content/\S+", "<path>", reason)
    return reason[:300]


def sniff_ext(body, content_type):
    if body[:5] == b"%PDF-":
        return "pdf"
    head = body[:2048].lower()
    if b"<html" in head or b"<!doctype html" in head:
        return "html"
    if body[:4] == b"\xd0\xcf\x11\xe0":  # OLE2: legacy MS Office binary
        ct = (content_type or "").lower()
        return "doc" if "msword" in ct else "ppt" if "powerpoint" in ct else "xls" if "excel" in ct else "ole"
    if body[:4] == b"PK\x03\x04":
        ct = (content_type or "").lower()
        if "wordprocessingml" in ct:
            return "docx"
        if "spreadsheetml" in ct:
            return "xlsx"
        return "zip"
    return "bin"


def served_filename(headers):
    cd = headers.get("content-disposition") or ""
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    return m.group(1) if m else None


def main():
    with open(os.path.join(LOCAL, "plan.jsonl")) as f:
        plan = [json.loads(l) for l in f if l.strip()]
    log = load_jsonl_last(FETCH_LOG)
    os.makedirs(os.path.join(ROOT, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "html"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "text", "raw"), exist_ok=True)
    os.makedirs(ANALYSIS, exist_ok=True)

    failures = {}
    fetched = skipped = 0
    for n, row in enumerate(plan, 1):
        doc_id = row["doc_id"]
        prev = log.get(doc_id)
        if prev and os.path.exists(os.path.join(ROOT, prev["path"])) \
                and sha256_file(os.path.join(ROOT, prev["path"])) == prev["sha256"]:
            skipped += 1
            rec = prev
        else:
            try:
                r = polite.get(row["fetch_url"])
            except polite.FetchError as e:
                failures[doc_id] = {"doc_id": doc_id, "reason": sanitize(e.reason),
                                    "attempts": e.attempts,
                                    "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
                print(f"[{n}/{len(plan)}] FAIL {doc_id}: {sanitize(e.reason)}", flush=True)
                continue
            body = r.content
            ext = sniff_ext(body, r.headers.get("content-type"))
            if row["snapshot_kind"] == "file" and ext == "html":
                failures[doc_id] = {"doc_id": doc_id, "attempts": 1,
                                    "reason": "served HTML, not a file "
                                              f"(content-type {r.headers.get('content-type')})",
                                    "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
                print(f"[{n}/{len(plan)}] FAIL {doc_id}: served HTML", flush=True)
                continue
            sub = "html" if row["snapshot_kind"] == "html" else "pdf"
            rel = f"{sub}/{doc_id}.{ext}"
            path = os.path.join(ROOT, rel)
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, path)
            rec = {
                "doc_id": doc_id, "path": rel, "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "http_status": r.status_code, "content_type": r.headers.get("content-type"),
                "last_modified": r.headers.get("last-modified"),
                "served_filename": served_filename(r.headers) if not row.get("restricted") else None,
                "redirected": r.url != row["fetch_url"],
            }
            # a stale file under another extension would break `ls pdf/ | wc -l`
            if prev and prev["path"] != rel and os.path.exists(os.path.join(ROOT, prev["path"])):
                os.remove(os.path.join(ROOT, prev["path"]))
            append_jsonl(FETCH_LOG, rec)
            log[doc_id] = rec
            fetched += 1
            print(f"[{n}/{len(plan)}] ok {doc_id} {ext} {len(body)}B", flush=True)

        # analysis, cached by sha256
        apath = os.path.join(ANALYSIS, f"{doc_id}.json")
        if os.path.exists(apath):
            with open(apath) as f:
                a = json.load(f)
            if a.get("sha256") == rec["sha256"]:
                continue
        src = os.path.join(ROOT, rec["path"])
        if rec["path"].endswith(".pdf"):
            a = pdfcheck.analyse(src, os.path.join(ROOT, "text", "raw", f"{doc_id}.txt"),
                                 language=row.get("language") or "en")
        elif rec["path"].endswith(".html"):
            with open(src, "rb") as f:
                soup = BeautifulSoup(f.read().decode("utf-8", "replace"), "html.parser")
            og = soup.find("meta", property="og:title")
            mod = soup.find("meta", property="article:modified_time")
            a = {"html_title": (og.get("content") if og else None),
                 "html_modified": (mod.get("content") if mod else None)}
        else:
            a = {"note": f"non-PDF file ({rec['path'].rsplit('.', 1)[-1]}); not analysed"}
        a["sha256"] = rec["sha256"]
        with open(apath, "w") as f:
            json.dump(a, f, ensure_ascii=False)

    # failures file reflects this run's view: drop entries that now have a good file
    old = load_jsonl_last(FAILURES)
    old.update(failures)
    with open(FAILURES, "w") as f:
        for k, v in old.items():
            if k in log and os.path.exists(os.path.join(ROOT, log[k]["path"])):
                continue
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    print(f"done: fetched {fetched}, skipped (already valid) {skipped}, failed {len(failures)}, "
          f"requests {polite.request_count}")


if __name__ == "__main__":
    main()
