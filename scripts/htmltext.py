"""Extract readable text from an archived HTML page (stdlib only, no dependencies).

The ombuds sites publish some documents only as web pages — 24 FAIS case studies and 44 NFO
documents that exist as nothing else. Their text has to come from HTML rather than a PDF.

Not a general-purpose reader: it prefers <article>, then <main>, then <body>; drops script,
style, nav, header, footer, form and aside; and collapses whitespace. That is enough for these
pages, which are WordPress content pages, and it avoids pulling in a parser dependency for one
stage.
"""
from html.parser import HTMLParser

SKIP = {"script", "style", "nav", "header", "footer", "form", "aside", "noscript"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
         "blockquote", "table", "td", "th", "dt", "dd"}
PREFER = ("article", "main", "body")


class _Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth_skip = 0
        self.stack = []
        self.capture_from = None   # tag name we are capturing inside, once decided
        self.buf = []
        self.fallback = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SKIP:
            self.depth_skip += 1
            return
        if self.depth_skip:
            return
        self.stack.append(tag)
        if self.capture_from is None and tag in PREFER:
            self.capture_from = tag
        if tag in BLOCK:
            self.buf.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in BLOCK and not self.depth_skip:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP:
            if self.depth_skip:
                self.depth_skip -= 1
            return
        if self.depth_skip:
            return
        if self.stack and tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        if tag in BLOCK:
            self.buf.append("\n")
        if self.capture_from == tag:
            # finished the preferred container; remember it and close capture
            self.fallback = list(self.buf)
            self.capture_from = "__done__"

    def handle_data(self, data):
        if self.depth_skip:
            return
        self.buf.append(data)


def html_to_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    p = _Extract()
    p.feed(raw)
    p.close()
    text = "".join(p.buf if not p.fallback else p.fallback)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
