"""Pre-scan a PDF with PyMuPDF to recover true list markers and TOC structure.

pdf2docx sometimes fails to decode marker glyphs (broken font cmaps) and emits
replacement/PUA characters. PyMuPDF's own text extraction usually decodes the
same glyphs correctly, so this pre-scan acts as the source of truth for what
each line's leading marker really was.
"""

import re

import fitz

# Order matters: hybrid and multilevel must win over plain decimal.
HYBRID_RE = re.compile(r'^(\d{1,2}\.[a-zA-Z][.)]?)(?=[ \t]|$)')
MULTILEVEL_RE = re.compile(r'^(\d{1,2}(?:\.\d{1,2}){1,3}\.?)(?=[ \t]|$)')
DECIMAL_RE = re.compile(r'^(\d{1,2}[.)])(?=[ \t]|$)')
ALPHA_RE = re.compile(r'^([a-zA-Z][.)])(?=[ \t]|$)')
ROMAN_RE = re.compile(r'^([ivxlcdmIVXLCDM]{2,6}[.)])(?=[ \t]|$)')

BULLET_CHARS = set('•◦▪‣·►●○■◆◇▸□☐▫★☆✦✧➤➢–—')

# TOC line: some text, then a run of ≥4 dots (or … chars), then a page number
TOC_RE = re.compile(r'^(?P<title>.*?)\s*(?P<leader>\.{4,}|…{2,})\s*(?P<page>\d{1,4})\s*$')

_WS_RE = re.compile(r'[\W_]+', re.UNICODE)


def normalize(text):
    """Normalize text for fuzzy paragraph matching: lowercase alphanumerics only."""
    return _WS_RE.sub('', text).lower()


def parse_marker(text):
    """Parse a leading list marker from text.

    Returns (marker, kind, rest) where kind is one of
    'hybrid', 'multilevel', 'decimal', 'alpha', 'roman', 'bullet', or
    (None, None, text) when no marker is found.
    """
    stripped = text.lstrip()
    if not stripped:
        return None, None, text

    m = HYBRID_RE.match(stripped)
    if m:
        return m.group(1), 'hybrid', stripped[m.end():].lstrip()

    m = MULTILEVEL_RE.match(stripped)
    if m:
        return m.group(1), 'multilevel', stripped[m.end():].lstrip()

    m = DECIMAL_RE.match(stripped)
    if m:
        return m.group(1), 'decimal', stripped[m.end():].lstrip()

    m = ROMAN_RE.match(stripped)
    if m:
        return m.group(1), 'roman', stripped[m.end():].lstrip()

    m = ALPHA_RE.match(stripped)
    if m:
        return m.group(1), 'alpha', stripped[m.end():].lstrip()

    ch = stripped[0]
    if ch in BULLET_CHARS or 0xE000 <= ord(ch) <= 0xF8FF:
        return ch, 'bullet', stripped[1:].lstrip()

    return None, None, stripped


def marker_level(marker, kind):
    """Nesting level implied by the marker itself (multilevel depth)."""
    if kind == 'multilevel':
        return max(0, len([p for p in marker.strip('.').split('.') if p]) - 1)
    if kind in ('alpha', 'roman'):
        return 1
    return 0


class LineInfo:
    __slots__ = ('marker', 'kind', 'level', 'body', 'body_key',
                 'is_toc', 'toc_page', 'toc_title')

    def __init__(self, marker, kind, level, body,
                 is_toc=False, toc_page=None, toc_title=None):
        self.marker = marker
        self.kind = kind
        self.level = level
        self.body = body
        self.body_key = normalize(body)[:40]
        self.is_toc = is_toc
        self.toc_page = toc_page
        self.toc_title = toc_title


class PreScan:
    """Result of scanning a PDF: ordered lines plus lookup structures."""

    def __init__(self):
        self.lines = []            # all LineInfo in document order
        self.by_key = {}           # normalized body prefix -> LineInfo (first wins)
        self.toc_entries = []      # LineInfo with is_toc, in document order
        self.toc_by_key = {}       # normalized title -> LineInfo

    def add(self, info):
        self.lines.append(info)
        if info.body_key and info.body_key not in self.by_key:
            self.by_key[info.body_key] = info
        if info.is_toc:
            self.toc_entries.append(info)
            if info.body_key and info.body_key not in self.toc_by_key:
                self.toc_by_key[info.body_key] = info

    def get(self, key):
        return self.by_key.get(key)


def prescan_pdf(pdf_path):
    """Extract per-line marker/TOC info from a PDF. Returns a PreScan."""
    scan = PreScan()
    if not pdf_path:
        return scan
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return scan

    try:
        for page in doc:
            data = page.get_text('dict')
            for block in data.get('blocks', []):
                if block.get('type') != 0:
                    continue
                for line in block.get('lines', []):
                    text = ''.join(span.get('text', '') for span in line.get('spans', []))
                    if not text.strip():
                        continue

                    marker, kind, rest = parse_marker(text)

                    toc_m = TOC_RE.match(rest if marker else text.strip())
                    if toc_m and toc_m.group('title').strip():
                        title = toc_m.group('title').strip()
                        scan.add(LineInfo(
                            marker, kind, marker_level(marker, kind), title,
                            is_toc=True,
                            toc_page=toc_m.group('page'),
                            toc_title=title,
                        ))
                        continue

                    if marker is None:
                        continue

                    scan.add(LineInfo(marker, kind, marker_level(marker, kind), rest))
    finally:
        doc.close()

    return scan
