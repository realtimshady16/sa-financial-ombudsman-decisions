"""Notice when the ombuds change what they publish.

Both offices publish by adding files to a WordPress site, so the only reliable signal is their own
sitemaps — not the human-facing archive page, which we already know omits pages (39 of them at the
2026-11 census, including every NFO-era document).

  python3 scripts/watch_sitemaps.py            # report against sources.jsonl
  python3 scripts/watch_sitemaps.py --changed-exit
        exit 3 when something changed, so a systemd timer's failed state *means* "go and look"

Writes `local/watch/<date>.json` (full lists) and `local/watch/latest.md` (the readable summary).
Nothing is fetched that the census has not already fetched once; this reports, it does not harvest.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "local", "watch")
UA = "ombudsman-data-watch/1.0 (+contact: tim@hellotim.co.za)"

SOURCES = {
    "nfo_docs": "https://nfosa.co.za/docs-sitemap.xml",
    "nfo_files": "https://nfosa.co.za/wpdmpro-sitemap.xml",
    "fais_table": "https://www.faisombud.co.za/determinations/",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def locs(xml):
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def fais_links(html):
    return re.findall(r'href="([^"]*uploads/determinations/[^"]+)"', html)


def basename_hash(url):
    import hashlib
    name = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def main(argv):
    # Three identifiers, because the census records documents in three ways: the page URL, the file
    # URL, and — for FAIS, where the file URL carries a complainant's name — a hash of the filename.
    known, known_hashes = set(), set()
    for line in open(os.path.join(ROOT, "sources.public.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        for k in ("url", "fetch_url", "package_url"):
            if r.get(k):
                known.add(r[k].rstrip("/"))
        if r.get("filename_sha256"):
            known_hashes.add(r["filename_sha256"])
    seen, errors, counts = set(), {}, {}
    for name, url in SOURCES.items():
        try:
            body = fetch(url)
        except Exception as e:  # noqa: BLE001 - a watcher must report, not crash
            errors[name] = f"{type(e).__name__}: {e}"
            continue
        items = fais_links(body) if name == "fais_table" else locs(body)
        if name == "fais_table":
            items = ["https://www.faisombud.co.za" + i if i.startswith("/") else i for i in items]
        counts[name] = len(items)
        for i in items:
            seen.add(i.rstrip("/"))
    # What matters is what changed since the last time *this watcher* looked. Comparing against the
    # census instead reports a permanent ~40-item disagreement (the sitemaps and the census describe
    # the same documents with different slugs) and would cry wolf monthly.
    base_path = os.path.join(OUT, "baseline.json")
    baseline = json.load(open(base_path)) if os.path.exists(base_path) else None
    not_in_census = sorted(u for u in seen if u.rstrip("/") not in known and basename_hash(u) not in known_hashes)
    if baseline is None:
        added, removed, first_run = [], [], True
    else:
        before = set(baseline.get("items", []))
        added = sorted(seen - before)
        removed = sorted(before - seen)
        first_run = False
    changed = bool(added or removed)

    os.makedirs(OUT, exist_ok=True)
    today = dt.date.today().isoformat()
    json.dump({"checked": today, "counts": counts, "added": added, "removed": removed,
               "not_in_census": not_in_census, "errors": errors},
              open(os.path.join(OUT, f"{today}.json"), "w"), indent=1)
    json.dump({"checked": today, "items": sorted(seen)}, open(base_path, "w"), indent=0)
    lines = [f"# Sitemap watch, {today}", ""]
    lines += [f"- {k}: {v} items" for k, v in counts.items()]
    lines += [f"- **{len(added)} added since last check**, {len(removed)} removed"
              + (" (first run: baseline established)" if first_run else "")
              + f", {len(not_in_census)} sitemap items absent from the census"]
    if errors:
        lines += ["", "## Fetch errors"] + [f"- {k}: {v}" for k, v in errors.items()]
    if added:
        lines += ["", "## Added since last check"] + [f"- {u}" for u in added[:40]]
    if removed:
        lines += ["", "## Removed since last check"] + [f"- {u}" for u in removed[:40]]
    summary = "\n".join(lines) + "\n"
    open(os.path.join(OUT, "latest.md"), "w").write(summary)
    print(summary)
    if errors:
        return 1
    if changed and not first_run and "--changed-exit" in argv:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
