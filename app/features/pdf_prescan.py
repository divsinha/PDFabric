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

# Characters that are ordinary prose despite being non-ASCII non-alnum
_NOT_BULLETS = set('“”‘’«»‹›„‚…€£¥§¶©®™°±×÷¡¿')

# TOC line: text, a run of ≥4 dots (dense or spaced) or ellipses, page number
TOC_RE = re.compile(
    r'^(?P<title>.*?)\s*(?P<leader>(?:[.…][  ]?){4,})\s*(?P<page>\d{1,4})\s*$')

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

    # Broad glyph coverage: any unusual non-ASCII symbol at line start
    # followed by whitespace is treated as a bullet (Wingdings-style glyphs
    # come in endless variety). Common prose punctuation is excluded.
    if (len(stripped) > 1 and stripped[1] in ' \t'
            and ord(ch) > 127 and not ch.isalnum()
            and ch not in _NOT_BULLETS):
        return ch, 'bullet', stripped[1:].lstrip()

    return None, None, stripped


_PART_RE = re.compile(r'^(?:(\d{1,2})|([a-z])|([A-Z]))$')


def marker_parts(marker, kind):
    """Parse a sequence marker into per-part (format, ordinal) tuples.

    "3.3.1" -> [('decimal',3),('decimal',3),('decimal',1)]
    "10.a"  -> [('decimal',10),('lowerLetter',1)]
    Returns None if any part is unparseable or out of bounds.
    """
    if kind not in ('decimal', 'multilevel', 'hybrid'):
        return None
    body = marker.rstrip('.)')
    parts = []
    for raw in body.split('.'):
        m = _PART_RE.match(raw)
        if not m:
            return None
        if m.group(1) is not None:
            val = int(m.group(1))
            if val < 1 or val > 99:
                return None
            parts.append(('decimal', val))
        elif m.group(2) is not None:
            parts.append(('lowerLetter', ord(m.group(2)) - 96))
        else:
            parts.append(('upperLetter', ord(m.group(3)) - 64))
    if not parts or len(parts) > 4:
        return None
    return parts


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
            page_lines = []  # (bbox, text) for vector-bullet matching
            for block in data.get('blocks', []):
                if block.get('type') != 0:
                    continue
                for line in block.get('lines', []):
                    text = ''.join(span.get('text', '') for span in line.get('spans', []))
                    if not text.strip():
                        continue

                    marker, kind, rest = parse_marker(text)
                    page_lines.append((line.get('bbox'), text, marker))

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

            _detect_vector_bullets(page, page_lines, scan)
    finally:
        doc.close()

    return scan


def _detect_vector_bullets(page, page_lines, scan):
    """Mark lines whose bullet is a small filled shape drawn as graphics
    (no character in the text layer)."""
    if not page_lines:
        return
    try:
        drawings = page.get_drawings()
    except Exception:
        return
    dots = []
    for d in drawings:
        rect = d.get('rect')
        if rect is None:
            continue
        w, h = rect.width, rect.height
        if w <= 0 or h <= 0 or w > 7 or h > 7:
            continue
        if not (0.4 <= (w / h if h else 0) <= 2.5):
            continue
        if d.get('fill') is None and 'f' not in (d.get('type') or ''):
            continue
        dots.append(rect)
    if not dots:
        return

    for bbox, text, marker in page_lines:
        if marker is not None or bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        line_h = max(1.0, y1 - y0)
        cy = (y0 + y1) / 2
        for rect in dots:
            dcy = (rect.y0 + rect.y1) / 2
            if abs(dcy - cy) <= line_h * 0.6 and rect.x1 <= x0 + 1 and x0 - rect.x0 <= 40:
                scan.add(LineInfo('•', 'vector-bullet', 0, text.strip()))
                break
