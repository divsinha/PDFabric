"""Post-process pdf2docx output: repair garbled list markers and TOC layout.

Strategy: preserve literal marker text, fix layout. Word auto-numbering is
deliberately NOT used — auto-numbers recalculate and silently renumber items
whenever detection is imperfect (1.10 becomes 1.5), while literal markers can
never be wrong. This mirrors what mature converters do.

Repairs performed:
- Garbled markers (□ / PUA chars from undecodable fonts) are replaced with the
  true marker text recovered from the source PDF via pdf_prescan.
- List paragraphs get hanging indents scaled by their nesting level so marker
  and body columns align.
- TOC lines get a right-aligned dot-leader tab stop instead of literal "....."
  filler, and page numbers orphaned onto their own paragraph are merged back.

All text surgery happens on individual runs (run.text / run._element) — never
para.text, which would destroy run-level formatting.
"""

import re

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Inches

from app.features.pdf_prescan import normalize, prescan_pdf

DOT_LEADER_RE = re.compile(r'[.…]{5,}')
BARE_PAGENUM_RE = re.compile(r'^\d{1,4}$')

GARBLED_CHARS = set('□▯☐◻＿')


def _is_garbled_char(ch):
    if ch in GARBLED_CHARS:
        return True
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or cp == 0xFFFD  # PUA or replacement char


def _leading_garbage_len(text):
    """Length of a garbled marker prefix (garbage chars + trailing whitespace)."""
    i = 0
    while i < len(text) and _is_garbled_char(text[i]):
        i += 1
    if i == 0:
        return 0
    while i < len(text) and text[i] in ' \t':
        i += 1
    return i


def _para_key(para):
    """Normalized matching key for a paragraph, ignoring any garbled prefix."""
    text = para.text.strip()
    text = text[_leading_garbage_len(text):]
    # Drop trailing dot leader + page number so TOC lines match their title
    m = DOT_LEADER_RE.search(text)
    if m:
        text = text[:m.start()]
    return normalize(text)[:40]


def _first_text_run(para):
    for run in para.runs:
        if run.text:
            return run
    return None


def _replace_garbled_marker(para, true_marker):
    """Swap a garbled leading marker for the true text, keeping run formatting."""
    run = _first_text_run(para)
    if run is None:
        return False
    glen = _leading_garbage_len(run.text)
    if glen == 0:
        # Garbage might be a whole run of only garbage chars
        if all(_is_garbled_char(c) or c in ' \t' for c in run.text) and run.text.strip():
            run.text = true_marker + '\t'
            return True
        return False
    run.text = true_marker + '\t' + run.text[glen:]
    return True


def _strip_garbled_marker(para):
    """No prescan info: just remove the garbage so it doesn't render as □."""
    run = _first_text_run(para)
    if run is None:
        return
    glen = _leading_garbage_len(run.text)
    if glen:
        run.text = run.text[glen:]
    elif all(_is_garbled_char(c) or c in ' \t' for c in run.text) and run.text.strip():
        run._element.getparent().remove(run._element)


def _apply_hanging_indent(para, level, marker_width_in=0.35):
    pf = para.paragraph_format
    left = Inches(0.25 + 0.3 * level + marker_width_in)
    pf.left_indent = left
    pf.first_line_indent = -Inches(marker_width_in)
    _set_tab_stops(para, [(int(left), 'left', 'none')])


def _set_tab_stops(para, stops):
    """stops: list of (pos_emu, alignment, leader). Replaces existing tabs."""
    pPr = para._p.get_or_add_pPr()
    existing = pPr.find(qn('w:tabs'))
    if existing is not None:
        pPr.remove(existing)
    tabs = OxmlElement('w:tabs')
    for pos_emu, val, leader in stops:
        tab = OxmlElement('w:tab')
        tab.set(qn('w:val'), val)
        if leader and leader != 'none':
            tab.set(qn('w:leader'), leader)
        tab.set(qn('w:pos'), str(int(pos_emu / 635)))  # EMU -> twips
        tabs.append(tab)
    pPr.append(tabs)


def _content_width_emu(doc):
    try:
        sec = doc.sections[0]
        return int(sec.page_width) - int(sec.left_margin) - int(sec.right_margin)
    except Exception:
        return int(Inches(6.5))


def _fix_toc_paragraph(para, doc, page_num_text=None):
    """Turn literal '.....' filler into a right-aligned dot-leader tab stop."""
    # Replace every dot-leader sequence with a tab: pdf2docx may merge several
    # TOC lines into one paragraph (separated by line breaks), and each line
    # needs its own tab to reach the shared right tab stop.
    replaced = False
    for run in para.runs:
        if run.text and DOT_LEADER_RE.search(run.text):
            run.text = DOT_LEADER_RE.sub('\t', run.text)
            replaced = True
    if page_num_text is not None:
        # Append merged page number after a tab
        target = None
        for run in reversed(para.runs):
            if run.text:
                target = run
                break
        if target is not None:
            base = target.text.rstrip(' ')
            if not base.endswith('\t'):
                base += '\t'
            target.text = base + page_num_text
    # Kill wrapping-induced indents and set the right tab stop
    pf = para.paragraph_format
    pf.first_line_indent = None
    _set_tab_stops(para, [(_content_width_emu(doc), 'right', 'dot')])


def _delete_paragraph(para):
    el = para._p
    el.getparent().remove(el)


def fix_lists(docx_path, pdf_path=None):
    """Repair list markers and TOC layout in a pdf2docx-generated DOCX."""
    doc = Document(docx_path)
    prescan = prescan_pdf(pdf_path) if pdf_path else {}

    paragraphs = list(doc.paragraphs)
    to_delete = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        text = para.text.strip()
        if not text:
            i += 1
            continue

        key = _para_key(para)
        info = prescan.get(key) if key else None

        has_garbage = _leading_garbage_len(text) > 0

        # --- TOC lines ---------------------------------------------------
        # Only treat as TOC when the DOCX paragraph itself shows a dot leader;
        # a body heading can share its text with a TOC entry (same match key).
        is_toc_like = bool(DOT_LEADER_RE.search(text))
        orphan_page = None
        if is_toc_like:
            # Detect orphaned page number in the next paragraph
            if not re.search(r'\d\s*$', text) and i + 1 < len(paragraphs):
                nxt = paragraphs[i + 1].text.strip()
                if BARE_PAGENUM_RE.match(nxt):
                    orphan_page = nxt
                    to_delete.append(paragraphs[i + 1])

            if has_garbage:
                if info is not None and info.marker:
                    _replace_garbled_marker(para, info.marker)
                else:
                    _strip_garbled_marker(para)

            _fix_toc_paragraph(para, doc, page_num_text=orphan_page)
            i += 2 if orphan_page else 1
            continue

        # --- Garbled list markers -----------------------------------------
        if has_garbage:
            if info is not None and info.marker:
                _replace_garbled_marker(para, info.marker)
                _apply_hanging_indent(para, info.level)
            else:
                _strip_garbled_marker(para)
            i += 1
            continue

        # --- Intact list markers: align only, never rewrite ---------------
        # (TOC-flagged info is fine here: real TOC lines were handled above.)
        if info is not None and info.marker and text.startswith(info.marker):
            _apply_hanging_indent(para, info.level)

        i += 1

    for para in to_delete:
        _delete_paragraph(para)

    doc.save(docx_path)
