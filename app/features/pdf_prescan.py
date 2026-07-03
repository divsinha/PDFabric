"""Pre-scan a PDF with PyMuPDF to recover true list markers and TOC structure.

pdf2docx sometimes fails to decode marker glyphs (broken font cmaps) and emits
replacement/PUA characters. PyMuPDF's own text extraction usually decodes the
same glyphs correctly, so this pre-scan acts as the source of truth for what
each line's leading marker really was.
"""

import re

import fitz

# Multilevel first (1.1., 2.10.3) so it wins over plain decimal
MULTILEVEL_RE = re.compile(r'^(\d+(?:\.\d+)+\.?)(?=[\s ]|$)')
DECIMAL_RE = re.compile(r'^(\d+[.)])(?=[\s ]|$)')
ALPHA_RE = re.compile(r'^([a-zA-Z][.)])(?=[\s ]|$)')
ROMAN_RE = re.compile(r'^([ivxlcdmIVXLCDM]{1,6}[.)])(?=[\s ]|$)')

BULLET_CHARS = set('•◦▪‣·►●○■◆◇▸□☐▫★☆✦✧➤➢–—')

# TOC line: some text, then a run of ≥5 dots (or … chars), then a page number
TOC_RE = re.compile(r'^(?P<title>.*?)\s*(?P<leader>\.{5,}|…{2,})\s*(?P<page>\d{1,4})\s*$')

_WS_RE = re.compile(r'[\W_]+', re.UNICODE)


def normalize(text):
    """Normalize text for fuzzy paragraph matching: lowercase alphanumerics only."""
    return _WS_RE.sub('', text).lower()


def _parse_marker(text):
    """Return (marker, level, rest) for a line's leading marker, or (None, 0, text)."""
    stripped = text.lstrip()
    if not stripped:
        return None, 0, text

    m = MULTILEVEL_RE.match(stripped)
    if m:
        marker = m.group(1)
        # depth = number of numeric parts: "1.1." -> 2 -> level 1
        level = max(0, len([p for p in marker.strip('.').split('.') if p]) - 1)
        return marker, level, stripped[m.end():].lstrip()

    m = DECIMAL_RE.match(stripped)
    if m:
        return m.group(1), 0, stripped[m.end():].lstrip()

    m = ALPHA_RE.match(stripped)
    if m:
        return m.group(1), 1, stripped[m.end():].lstrip()

    m = ROMAN_RE.match(stripped)
    if m:
        return m.group(1), 2, stripped[m.end():].lstrip()

    ch = stripped[0]
    if ch in BULLET_CHARS or 0xF000 <= ord(ch) <= 0xF0FF:
        return ch, 0, stripped[1:].lstrip()

    return None, 0, stripped


class LineInfo:
    __slots__ = ('marker', 'level', 'body', 'body_key', 'is_toc', 'toc_page', 'toc_title')

    def __init__(self, marker, level, body, is_toc=False, toc_page=None, toc_title=None):
        self.marker = marker
        self.level = level
        self.body = body
        self.body_key = normalize(body)[:40]
        self.is_toc = is_toc
        self.toc_page = toc_page
        self.toc_title = toc_title


def prescan_pdf(pdf_path):
    """Extract per-line marker/TOC info from a PDF.

    Returns a dict mapping normalized body-text prefix -> LineInfo.
    Lines without a marker and without TOC structure are skipped.
    """
    index = {}
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return index

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

                    marker, level, rest = _parse_marker(text)

                    toc_m = TOC_RE.match(rest if marker else text.strip())
                    if toc_m and toc_m.group('title').strip():
                        title = toc_m.group('title').strip()
                        info = LineInfo(
                            marker, level, title,
                            is_toc=True,
                            toc_page=toc_m.group('page'),
                            toc_title=title,
                        )
                        if info.body_key and info.body_key not in index:
                            index[info.body_key] = info
                        continue

                    if marker is None:
                        continue

                    info = LineInfo(marker, level, rest)
                    if info.body_key and info.body_key not in index:
                        index[info.body_key] = info
    finally:
        doc.close()

    return index
