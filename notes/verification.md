Output of `scripts/verify.sh --live` at commit time (2026-11-22):

```
$ wc -l sources.jsonl            -> 1004
$ ls pdf/ | wc -l                -> 936
$ ls html/ | wc -l               -> 68   (HTML-only documents; pdf/ + html/ = 1004)
$ sha256sum -c SHA256SUMS        -> 1004 OK
$ python -c json.loads(sources.jsonl) -> parses
$ curl docs-sitemap.xml | grep -c '<loc>'    -> 360
$ curl wpdmpro-sitemap.xml | grep -c '<loc>' -> 332
PASS  sources.jsonl parses — 1004 rows
PASS  rows == files on disk — 1004 rows; pdf/ 936 + html/ 68
PASS  pdf/ rows == ls pdf/ — 936 vs 936
PASS  every row's snapshot exists, names match doc_id
PASS  doc_ids unique
PASS  sha256sum -c SHA256SUMS — 1004 entries
PASS  sources.jsonl validates against schema/document.schema.json — 0 errors []
PASS  sources.public.jsonl validates — 0 errors []
PASS  public rows carry no restricted data
PASS  same rows in public and local
PASS  text/raw/<doc_id>.txt exists for every PDF — 928 PDFs
```
