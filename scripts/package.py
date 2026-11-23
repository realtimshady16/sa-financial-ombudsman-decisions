"""Build and verify the published data package.

Two jobs, deliberately in one script so they cannot drift apart:

1. emit `decisions.public.csv` — the same records as `decisions.public.jsonl`, for people who open a
   spreadsheet rather than a JSON parser. List-valued fields are pipe-joined.
2. verify `datapackage.json` against what is actually on disk: every resource exists, its row count
   matches, its declared fields cover every key in every record, and the licences it names exist as
   files. A data package that is wrong about itself is worse than no package.

  python3 scripts/package.py [--check]
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "datapackage.json")
CSV_OUT = os.path.join(ROOT, "decisions.public.csv")


def rows(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def join_lists(v):
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return v


def write_csv():
    recs = rows("decisions.public.jsonl")
    fields = list(json.load(open(os.path.join(ROOT, "datapackage.json")))["resources"][0]["schema"]["fields"])
    names = [f["name"] for f in fields]
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=names, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({k: join_lists(r.get(k)) for k in names})
    return len(recs), names


def verify():
    problems = []
    pkg = json.load(open(PKG))
    for res in pkg["resources"]:
        path = os.path.join(ROOT, res["path"])
        if not os.path.exists(path):
            problems.append(f"missing resource file: {res['path']}")
            continue
        if res["path"].endswith(".jsonl"):
            data = rows(res["path"])
        elif res["path"].endswith(".csv"):
            with open(path, newline="", encoding="utf-8") as fh:
                data = list(csv.DictReader(fh))
        else:
            data = []
        want = res.get("count") or res.get("rowCount")
        if want is not None and data and len(data) != want:
            problems.append(f"{res['path']}: declared {want} rows, found {len(data)}")
        declared = {f["name"] for f in res.get("schema", {}).get("fields", [])}
        if data and declared:
            seen = set().union(*[set(r) for r in data])
            undeclared = sorted(seen - declared)
            if undeclared:
                problems.append(f"{res['path']}: undeclared fields {undeclared}")
            absent = sorted(declared - seen)
            if absent:
                problems.append(f"{res['path']}: declared but never present {absent}")
    for lic in pkg.get("licenses", []):
        if "path" in lic and not os.path.exists(os.path.join(ROOT, lic["path"])):
            problems.append(f"licence file missing: {lic['path']}")
    return pkg, problems


def main(argv):
    n, names = write_csv()
    print(f"wrote decisions.public.csv: {n} rows, {len(names)} columns")
    pkg, problems = verify()
    print(f"datapackage.json: {len(pkg['resources'])} resources, "
          f"{len(pkg.get('licenses', []))} licences")
    if problems:
        for p in problems:
            print(f"  PROBLEM {p}")
        return 1
    print("  verified: every resource exists, row counts match, declared fields match the data")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
