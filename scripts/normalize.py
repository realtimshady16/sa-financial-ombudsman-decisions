"""The only normalisation Stage 2 applies to extracted text. Deliberately narrow.

- Unicode ligature characters U+FB00–FB06 (ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ) are expanded to their letters, so that
  `ﬁrst` is findable as `first`. These are real characters in the text layer of 29 PDFs.
- Soft hyphens U+00AD are removed (invisible in print, they split words for search).

Not done, on purpose: full NFKC. NFKC also folds superscripts into plain digits, and the corpus has
footnote markers set directly after amounts (`R800 000⁴`); folding them would turn an amount into
a different number. Hyphenation and column order are left alone too; both are layout decisions for
the stage that reads the text.
"""

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "ﬅ": "st", "ﬆ": "st"}


def normalize(text):
    """-> (text, {"ligatures_expanded": n, "soft_hyphens_removed": n})"""
    lig = sum(text.count(k) for k in LIGATURES)
    soft = text.count("­")
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = text.replace("­", "")
    return text, {"ligatures_expanded": lig, "soft_hyphens_removed": soft}
