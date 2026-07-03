"""Post-process pdf2docx output: real Word numbering + TOC layout repair.

Three phases (design reviewed against ECMA-376 numbering semantics):

1. Split paragraphs that pdf2docx merged (line-break separated logical lines).
2. Rebuild Table-of-Contents lines: one paragraph per entry with a
   right-aligned dot-leader tab stop instead of literal "....." filler.
3. Convert literal list markers (1., 1.1, 3.3.1, a., A., bullets — including
   markers garbled into PUA/□ chars by broken font cmaps, recovered via
   pdf_prescan) into live Word auto-numbering with a hard exactness guarantee:
   the rendered number always equals the original literal.

The exactness guarantee comes from *segmenting*: items are simulated against
Word's numbering semantics (a level restarts at its w:start — never at 1;
deeper items never advance parent counters). The moment a literal deviates
from what Word would render, the current segment is closed and a fresh
abstractNum+num is minted whose per-level w:start values equal that literal.
The first item of every segment is exact by construction, so the worst case
is extra numbering definitions — never a wrong number. w:startOverride and
w:lvlRestart are deliberately not used (renderer-compatibility hazards).
"""

import re
import uuid
from copy import deepcopy

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.text.paragraph import Paragraph

from app.features.pdf_prescan import (
    normalize,
    parse_marker,
    prescan_pdf,
)

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

DOT_LEADER_RE = re.compile(r'[.…]{4,}')
TOC_ENTRY_RE = re.compile(
    r'(?P<title>[^\n]+?)[ \t]*[.…]{4,}[ \t]*(?P<page>\d{1,4})(?!\d)')
BARE_PAGENUM_RE = re.compile(r'^\d{1,4}$')

GARBLED_CHARS = set('□▯☐◻')


# ---------------------------------------------------------------------------
# text utilities
# ---------------------------------------------------------------------------

def _is_garbled_char(ch):
    if ch in GARBLED_CHARS:
        return True
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or cp == 0xFFFD


def _leading_garbage_len(text):
    """Length of a garbled marker prefix (garbage chars + trailing blanks)."""
    i = 0
    while i < len(text) and _is_garbled_char(text[i]):
        i += 1
    if i == 0:
        return 0
    while i < len(text) and text[i] in ' \t':
        i += 1
    return i


def _run_text(r_el):
    """Text of one w:r as python-docx renders it (tab -> \\t, br -> \\n)."""
    parts = []
    for child in r_el:
        tag = child.tag
        if tag == qn('w:t'):
            parts.append(child.text or '')
        elif tag == qn('w:tab'):
            parts.append('\t')
        elif tag == qn('w:br'):
            parts.append('\n')
    return ''.join(parts)


def _elements_text(elements):
    return ''.join(_run_text(el) for el in elements if el.tag == qn('w:r'))


# ---------------------------------------------------------------------------
# Phase 1 — split merged paragraphs at line breaks
# ---------------------------------------------------------------------------

_SPLIT_UNSAFE = [qn('w:fldChar'), qn('w:hyperlink'), qn('w:ins'), qn('w:del')]


def _qualifying_br(child):
    if child.tag != qn('w:br'):
        return False
    br_type = child.get(qn('w:type'))
    return br_type in (None, 'textWrapping')


def _segment_starts_line(text):
    t = text.lstrip(' \t')
    if not t:
        return False
    if _leading_garbage_len(t):
        return True
    marker, kind, _ = parse_marker(t)
    return marker is not None


def _split_paragraph(para):
    """Split one paragraph at soft line breaks where a new list line starts."""
    p = para._p
    for tag in _SPLIT_UNSAFE:
        if p.find('.//' + tag) is not None:
            return

    has_br = any(
        _qualifying_br(child)
        for r in p.findall(qn('w:r'))
        for child in r
    )
    if not has_br:
        return

    # Build segments: lists of (run or other) elements, split at soft breaks.
    segments = [[]]
    for child in list(p):
        if child.tag == qn('w:pPr'):
            continue
        if child.tag != qn('w:r'):
            segments[-1].append(child)
            continue
        rpr = child.find(qn('w:rPr'))
        chunk = []
        chunks = [chunk]
        for sub in list(child):
            if sub.tag == qn('w:rPr'):
                continue
            if _qualifying_br(sub):
                chunk = []
                chunks.append(chunk)
            else:
                chunk.append(sub)
        if len(chunks) == 1:
            segments[-1].append(child)
            continue
        for idx, ch in enumerate(chunks):
            if idx > 0:
                segments.append([])
            if not ch:
                continue
            new_r = OxmlElement('w:r')
            if rpr is not None:
                new_r.append(deepcopy(rpr))
            for sub in ch:
                new_r.append(deepcopy(sub))
            segments[-1].append(new_r)

    if len(segments) <= 1:
        return

    # Group segments: a segment starting with a list marker begins a new
    # paragraph; anything else is a wrapped continuation joined by a space.
    groups = [segments[0]]
    for seg in segments[1:]:
        if _segment_starts_line(_elements_text(seg)):
            groups.append(seg)
        else:
            space_r = OxmlElement('w:r')
            prev_runs = [e for e in groups[-1] if e.tag == qn('w:r')]
            if prev_runs:
                prev_rpr = prev_runs[-1].find(qn('w:rPr'))
                if prev_rpr is not None:
                    space_r.append(deepcopy(prev_rpr))
            t_el = OxmlElement('w:t')
            t_el.set(qn('xml:space'), 'preserve')
            t_el.text = ' '
            space_r.append(t_el)
            groups[-1].append(space_r)
            groups[-1].extend(seg)

    if len(groups) == 1:
        # Pure reflow: still rebuild so soft breaks become spaces.
        pass

    ppr = p.find(qn('w:pPr'))
    sect_pr = ppr.find(qn('w:sectPr')) if ppr is not None else None
    if sect_pr is not None:
        ppr.remove(sect_pr)

    # Rebuild the original paragraph with the first group.
    for child in list(p):
        if child.tag != qn('w:pPr'):
            p.remove(child)
    for el in groups[0]:
        p.append(el)

    anchor = p
    for group in groups[1:]:
        new_p = OxmlElement('w:p')
        if ppr is not None:
            new_p.append(deepcopy(ppr))
        for el in group:
            new_p.append(el)
        anchor.addnext(new_p)
        anchor = new_p

    # A section break stays on the physically last paragraph of the split.
    if sect_pr is not None:
        last_ppr = anchor.find(qn('w:pPr'))
        if last_ppr is None:
            last_ppr = OxmlElement('w:pPr')
            anchor.insert(0, last_ppr)
        last_ppr.append(sect_pr)


def _split_merged_paragraphs(doc):
    for para in list(doc.paragraphs):
        _split_paragraph(para)


def _rtrim_paragraph(p_el):
    """Remove trailing spaces/tabs from a paragraph's last runs."""
    for r_el in reversed(p_el.findall(qn('w:r'))):
        changed = True
        while changed:
            changed = False
            subs = [c for c in r_el if c.tag != qn('w:rPr')]
            if not subs:
                break
            last = subs[-1]
            if last.tag == qn('w:tab'):
                r_el.remove(last)
                changed = True
            elif last.tag == qn('w:t'):
                text = (last.text or '').rstrip(' \t')
                if text != (last.text or ''):
                    last.text = text
                if not text:
                    r_el.remove(last)
                    changed = True
        if not [c for c in r_el if c.tag != qn('w:rPr')]:
            r_el.getparent().remove(r_el)
        else:
            return


def _split_para_at_offset(para, offset):
    """Split a paragraph at a character offset (python-docx text coords)."""
    p = para._p
    ppr = p.find(qn('w:pPr'))
    new_p = OxmlElement('w:p')
    if ppr is not None:
        npr = deepcopy(ppr)
        sect = npr.find(qn('w:sectPr'))
        if sect is not None:
            npr.remove(sect)
        new_p.append(npr)

    pos = 0
    moving = False
    for child in list(p):
        if child.tag == qn('w:pPr'):
            continue
        if moving:
            new_p.append(child)
            continue
        if child.tag != qn('w:r'):
            continue
        rlen = len(_run_text(child))
        if pos + rlen <= offset:
            pos += rlen
            continue
        # Split inside this run.
        split_at = offset - pos
        rpr = child.find(qn('w:rPr'))
        tail_r = OxmlElement('w:r')
        if rpr is not None:
            tail_r.append(deepcopy(rpr))
        consumed = 0
        for sub in list(child):
            if sub.tag == qn('w:rPr'):
                continue
            if consumed >= split_at:
                tail_r.append(sub)
                continue
            if sub.tag == qn('w:t'):
                tlen = len(sub.text or '')
                if consumed + tlen > split_at:
                    cut = split_at - consumed
                    full = sub.text or ''
                    sub.text = full[:cut]
                    sub.set(qn('xml:space'), 'preserve')
                    t2 = OxmlElement('w:t')
                    t2.text = full[cut:]
                    t2.set(qn('xml:space'), 'preserve')
                    tail_r.append(t2)
                    consumed = split_at
                else:
                    consumed += tlen
            else:
                consumed += 1
        if len(tail_r) > (1 if rpr is not None else 0):
            new_p.append(tail_r)
        pos = offset
        moving = True

    p.addnext(new_p)
    _rtrim_paragraph(p)


def _split_at_prescan_lines(doc, scan):
    """Split paragraphs where pdf2docx merged several PDF lines with only a
    space/tab separator. The prescan tells us exactly where each real line
    began (marker + leading body text), so splitting is evidence-based and
    cannot cut ordinary prose."""
    if not scan.lines:
        return
    needles = []
    for info in scan.lines:
        if info.marker and not info.is_toc and info.body:
            frag = info.body[:12].rstrip()
            if frag:
                needles.append(f"{info.marker} {frag}")
    if not needles:
        return

    for para in list(doc.paragraphs):
        p = para._p
        if any(p.find('.//' + tag) is not None for tag in _SPLIT_UNSAFE):
            continue
        text = para.text
        if DOT_LEADER_RE.search(text):
            continue  # TOC content is handled by the TOC rebuild
        offsets = set()
        for needle in needles:
            start = text.find(needle)
            while start != -1:
                if start > 0 and text[start - 1] in ' \t\n':
                    offsets.add(start)
                start = text.find(needle, start + 1)
        for off in sorted(offsets, reverse=True):
            _split_para_at_offset(para, off)


# ---------------------------------------------------------------------------
# Phase 2 — TOC rebuild
# ---------------------------------------------------------------------------

def _content_width_emu(doc):
    try:
        sec = doc.sections[0]
        return int(sec.page_width) - int(sec.left_margin) - int(sec.right_margin)
    except Exception:
        return int(Inches(6.5))


def _set_tab_stops(p_el, stops):
    """stops: list of (pos_twips, alignment, leader). Replaces existing."""
    ppr = p_el.find(qn('w:pPr'))
    if ppr is None:
        ppr = OxmlElement('w:pPr')
        p_el.insert(0, ppr)
    existing = ppr.find(qn('w:tabs'))
    if existing is not None:
        ppr.remove(existing)
    tabs = OxmlElement('w:tabs')
    for pos, val, leader in stops:
        tab = OxmlElement('w:tab')
        tab.set(qn('w:val'), val)
        if leader and leader != 'none':
            tab.set(qn('w:leader'), leader)
        tab.set(qn('w:pos'), str(int(pos)))
        tabs.append(tab)
    ppr.append(tabs)


def _template_rpr(para):
    for r in para._p.findall(qn('w:r')):
        text = _run_text(r)
        if text.strip() and not all(_is_garbled_char(c) or c in ' \t' for c in text.strip()):
            rpr = r.find(qn('w:rPr'))
            return deepcopy(rpr) if rpr is not None else None
    return None


def _clean_toc_title(title, scan):
    """Strip garbage, restore true marker from the prescan when missing."""
    title = title.strip()
    glen = _leading_garbage_len(title)
    if glen:
        title = title[glen:].strip()
    marker, kind, _ = parse_marker(title)
    if marker is None and scan is not None:
        info = scan.toc_by_key.get(normalize(title)[:40])
        if info is not None and info.marker:
            title = f"{info.marker} {title}"
    return title


def _rebuild_toc_paragraph(para, doc, scan, extra_text=''):
    """Replace a TOC paragraph with one clean paragraph per entry."""
    full_text = para.text + extra_text
    entries = [
        (_clean_toc_title(m.group('title'), scan), m.group('page'))
        for m in TOC_ENTRY_RE.finditer(full_text)
    ]
    entries = [(t, pg) for t, pg in entries if t]
    if not entries:
        return False

    rpr = _template_rpr(para)
    right_twips = int(_content_width_emu(doc) / 635)
    parent = para._parent

    anchor = para._p
    for title, page in entries:
        new_p = OxmlElement('w:p')
        anchor.addprevious(new_p)
        wrapper = Paragraph(new_p, parent)
        run = wrapper.add_run(f"{title}\t{page}")
        if rpr is not None:
            run._element.insert(0, deepcopy(rpr))
        ppr = new_p.find(qn('w:pPr'))
        if ppr is None:
            ppr = OxmlElement('w:pPr')
            new_p.insert(0, ppr)
        jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), 'left')
        ppr.append(jc)
        _set_tab_stops(new_p, [(right_twips, 'right', 'dot')])

    anchor.getparent().remove(anchor)
    return True


def _fix_toc(doc, scan):
    paragraphs = list(doc.paragraphs)
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        text = para.text
        if not DOT_LEADER_RE.search(text):
            i += 1
            continue

        # Orphaned page number on the following paragraph?
        extra = ''
        skip = 1
        stripped = text.rstrip()
        if stripped and DOT_LEADER_RE.search(stripped[-8:]) and i + 1 < len(paragraphs):
            nxt = paragraphs[i + 1].text.strip()
            if BARE_PAGENUM_RE.match(nxt):
                extra = ' ' + nxt
                skip = 2

        if _rebuild_toc_paragraph(para, doc, scan, extra_text=extra):
            if skip == 2:
                orphan = paragraphs[i + 1]._p
                orphan.getparent().remove(orphan)
        i += skip


def _is_rebuilt_toc(para):
    """Structural check for paragraphs produced by the TOC rebuild.

    (lxml element proxies have unstable Python ids, so identity sets cannot
    be used to track paragraphs across accesses.)
    """
    if not re.search(r'\t\d{1,4}\s*$', para.text):
        return False
    ppr = para._p.find(qn('w:pPr'))
    if ppr is None:
        return False
    tabs = ppr.find(qn('w:tabs'))
    if tabs is None:
        return False
    return any(
        tab.get(qn('w:val')) == 'right' and tab.get(qn('w:leader')) == 'dot'
        for tab in tabs
    )


# ---------------------------------------------------------------------------
# Phase 3 — numbering engine
# ---------------------------------------------------------------------------

_ROMAN_VALUES = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}


def _roman_to_int(s):
    s = s.lower()
    total, prev = 0, 0
    for ch in reversed(s):
        val = _ROMAN_VALUES.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total if total > 0 else None


def _decimal_tuple(marker):
    body = marker.rstrip('.)')
    try:
        parts = tuple(int(p) for p in body.split('.'))
    except ValueError:
        return None
    if not parts or len(parts) > 4 or any(p < 1 or p > 99 for p in parts):
        return None
    return parts


def _marker_style(marker, kind):
    """Suffix style of a marker: '.', ')' or '' (no trailing punctuation)."""
    if marker.endswith(')'):
        return ')'
    if marker.endswith('.'):
        if kind == 'multilevel':
            return '.'  # trailing dot on multilevel: "1.1."
        return '.'
    return ''


class _Item:
    __slots__ = ('para', 'family', 'kind', 'marker', 'value', 'level',
                 'style', 'garbled_len', 'confirmed', 'index')

    def __init__(self, para, family, kind, marker, value, level, style,
                 garbled_len, confirmed, index):
        self.para = para
        self.family = family
        self.kind = kind
        self.marker = marker
        self.value = value          # tuple for decimal; int ordinal otherwise
        self.level = level          # display indent level
        self.style = style
        self.garbled_len = garbled_len
        self.confirmed = confirmed
        self.index = index


def _classify(marker, kind):
    """Map a parsed marker to (family, value, ilvl_for_decimal)."""
    if kind in ('decimal', 'multilevel'):
        value = _decimal_tuple(marker)
        if value is None:
            return None
        return ('decimal', value, len(value) - 1)
    if kind == 'alpha':
        ch = marker.rstrip('.)')
        if len(ch) != 1 or not ch.isalpha():
            return None
        family = 'lowerLetter' if ch.islower() else 'upperLetter'
        return (family, ord(ch.lower()) - 96, 0)
    if kind == 'roman':
        body = marker.rstrip('.)')
        val = _roman_to_int(body)
        if val is None:
            return None
        family = 'lowerRoman' if body.islower() else 'upperRoman'
        return (family, val, 0)
    if kind == 'bullet':
        return ('bullet', 0, 0)
    return None  # hybrid & anything else -> literal fallback


def _detect_items(doc, scan):
    items = []
    hybrids = []
    paragraphs = [p for p in doc.paragraphs if not _is_rebuilt_toc(p)]
    for idx, para in enumerate(paragraphs):
        text = para.text
        t = text.lstrip(' \t')
        if not t:
            continue

        glen = _leading_garbage_len(t)
        confirmed = False
        if glen:
            rest = t[glen:]
            info = scan.by_key.get(normalize(rest)[:40]) if scan else None
            if info is not None and info.marker and info.kind:
                marker, kind = info.marker, info.kind
                level_hint = info.level
                confirmed = True
            else:
                marker, kind, level_hint = t[:1], 'bullet', 0
        else:
            marker, kind, rest = parse_marker(t)
            if marker is None:
                continue
            level_hint = None
            # Marker must be followed by whitespace in the DOCX text, OR the
            # remainder must be confirmed by the prescan ("3.Conflict" case
            # where pdf2docx dropped the space).
            after = t[len(marker):]
            if after and after[0] not in ' \t':
                info = scan.by_key.get(normalize(after)[:40]) if scan else None
                if info is not None and info.marker == marker:
                    confirmed = True
                else:
                    continue
            else:
                info = scan.by_key.get(normalize(after.strip())[:40]) if scan else None
                if info is not None and info.marker == marker:
                    confirmed = True

        if kind == 'hybrid':
            hybrids.append((para, marker))
            continue

        cls = _classify(marker, kind)
        if cls is None:
            hybrids.append((para, marker))
            continue
        family, value, dec_level = cls

        if family == 'decimal':
            level = dec_level
        elif level_hint is not None:
            level = level_hint
        elif family == 'bullet':
            level = 0
        else:
            level = 1

        items.append(_Item(
            para, family, kind, marker, value, level,
            _marker_style(marker, kind), glen, confirmed, idx,
        ))

    # Guard: an isolated single-level "N." with no prescan confirmation and no
    # neighbouring list item within 3 paragraphs is prose, not a list.
    kept = []
    positions = [it.index for it in items]
    for n, it in enumerate(items):
        if (it.family == 'decimal' and len(it.value) == 1
                and not it.confirmed and it.garbled_len == 0):
            has_neighbor = any(
                abs(positions[m] - it.index) <= 3
                for m in range(len(items)) if m != n
            )
            if not has_neighbor:
                continue
        kept.append(it)
    return kept, hybrids


# --- segmenting simulation --------------------------------------------------

class _Segment:
    """A maximal run of items renderable by a single w:num."""

    def __init__(self, item):
        self.family = item.family
        self.items = [item]
        if item.family == 'decimal':
            self.base_level = len(item.value) - 1
            self.hard_prefix = item.value[:-1] if self.base_level > 0 else ()
            # w:start per relative level (0 = base_level)
            self.wstart = {0: item.value[-1]}
            self.counters = {0: item.value[-1]}
            self.styles = {0: item.style}
        else:
            self.base_level = 0
            self.hard_prefix = ()
            self.wstart = {0: item.value}
            self.counters = {0: item.value}
            self.styles = {0: item.style}
        self.display_level = item.level  # indent depth for the first level

    def try_add(self, item):
        """Simulate Word rendering item next; True if the literal matches."""
        if item.family != self.family:
            return False
        if self.family != 'decimal':
            expected = self.counters[0] + 1
            if item.value != expected or item.style != self.styles[0]:
                return False
            self.counters[0] = expected
            self.items.append(item)
            return True

        L_abs = len(item.value) - 1
        if L_abs < self.base_level:
            return False  # shallower than the (possibly hardcoded) base
        if item.value[:self.base_level] != self.hard_prefix:
            return False
        L = L_abs - self.base_level

        # Style compatibility at this relative level.
        if L in self.styles and self.styles[L] != item.style:
            return False

        # Parent display values (relative levels 0..L-1): current counter if
        # the level has an active count, else its w:start (never start-1).
        for l in range(L):
            shown = self.counters.get(l, self.wstart.get(l, 1))
            if item.value[self.base_level + l] != shown:
                return False

        # Own level: +1 if active, else restart/first-use at w:start (never 1).
        own = self.counters.get(L)
        expected = (own + 1) if own is not None else self.wstart.get(L, 1)
        if item.value[-1] != expected:
            return False

        # Commit.
        self.counters[L] = expected
        if L not in self.styles:
            self.styles[L] = item.style
        if L not in self.wstart:
            self.wstart[L] = 1
        for l in list(self.counters):
            if l > L:
                del self.counters[l]
        self.items.append(item)
        return True


def _build_segments(items):
    segments = []
    open_segments = {}  # family -> segment
    for item in items:
        if item.family == 'bullet':
            seg = open_segments.get('bullet')
            if seg is None:
                seg = _Segment(item)
                open_segments['bullet'] = seg
                segments.append(seg)
            else:
                seg.items.append(item)
            continue
        seg = open_segments.get(item.family)
        if seg is not None and seg.try_add(item):
            continue
        seg = _Segment(item)
        open_segments[item.family] = seg
        segments.append(seg)
    return segments


# --- numbering.xml construction ----------------------------------------------

_LVL_CHILD_ORDER = ('w:start', 'w:numFmt', 'w:suff', 'w:lvlText', 'w:lvlJc', 'w:pPr')

BULLET_GLYPHS = ['•', '○', '▪', '•', '○', '▪', '•', '○', '▪']


class _NumberingXML:
    def __init__(self, doc):
        self._doc = doc
        self._numbering_el = self._ensure_part()
        self._next_abstract = 1
        self._next_num = 1
        for el in self._numbering_el.findall(qn('w:abstractNum')):
            aid = int(el.get(qn('w:abstractNumId'), 0))
            self._next_abstract = max(self._next_abstract, aid + 1)
        for el in self._numbering_el.findall(qn('w:num')):
            nid = int(el.get(qn('w:numId'), 0))
            self._next_num = max(self._next_num, nid + 1)
        self._pending_abstracts = []
        self._pending_nums = []

    def _ensure_part(self):
        try:
            part = self._doc.part.numbering_part
            return part.numbering_definitions._numbering
        except Exception:
            pass
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.opc.packuri import PackURI
        from docx.opc.part import XmlPart
        from docx.oxml import parse_xml

        xml = (
            '<w:numbering xmlns:w="%s"></w:numbering>' % W
        )
        part = XmlPart(
            PackURI('/word/numbering.xml'),
            'application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.numbering+xml',
            parse_xml(xml),
            self._doc.part.package,
        )
        self._doc.part.relate_to(part, RT.NUMBERING)
        return part.element

    @staticmethod
    def _lvl(ilvl, start, num_fmt, lvl_text, indent_left, hanging=460):
        lvl = OxmlElement('w:lvl')
        lvl.set(qn('w:ilvl'), str(ilvl))

        el = OxmlElement('w:start')
        el.set(qn('w:val'), str(start))
        lvl.append(el)

        el = OxmlElement('w:numFmt')
        el.set(qn('w:val'), num_fmt)
        lvl.append(el)

        el = OxmlElement('w:suff')
        el.set(qn('w:val'), 'tab')
        lvl.append(el)

        el = OxmlElement('w:lvlText')
        el.set(qn('w:val'), lvl_text)
        lvl.append(el)

        el = OxmlElement('w:lvlJc')
        el.set(qn('w:val'), 'left')
        lvl.append(el)

        ppr = OxmlElement('w:pPr')
        tabs = OxmlElement('w:tabs')
        tab = OxmlElement('w:tab')
        tab.set(qn('w:val'), 'num')
        tab.set(qn('w:pos'), str(indent_left))
        tabs.append(tab)
        ppr.append(tabs)
        ind = OxmlElement('w:ind')
        ind.set(qn('w:left'), str(indent_left))
        ind.set(qn('w:hanging'), str(hanging))
        ppr.append(ind)
        lvl.append(ppr)

        if num_fmt == 'bullet':
            rpr = OxmlElement('w:rPr')
            fonts = OxmlElement('w:rFonts')
            fonts.set(qn('w:ascii'), 'Symbol')
            fonts.set(qn('w:hAnsi'), 'Symbol')
            fonts.set(qn('w:hint'), 'default')
            rpr.append(fonts)
            lvl.append(rpr)
        return lvl

    def _new_abstract(self):
        aid = self._next_abstract
        self._next_abstract += 1
        abstract = OxmlElement('w:abstractNum')
        abstract.set(qn('w:abstractNumId'), str(aid))
        nsid = OxmlElement('w:nsid')
        nsid.set(qn('w:val'), uuid.uuid4().hex[:8].upper())
        abstract.append(nsid)
        mlt = OxmlElement('w:multiLevelType')
        mlt.set(qn('w:val'), 'multilevel')
        abstract.append(mlt)
        return aid, abstract

    def abstract_for_segment(self, seg):
        aid, abstract = self._new_abstract()

        if seg.family == 'bullet':
            for i in range(9):
                abstract.append(self._lvl(
                    i, 1, 'bullet', BULLET_GLYPHS[i], 720 * (i + 1), 360))
        elif seg.family == 'decimal':
            prefix = ''.join(f'{n}.' for n in seg.hard_prefix)
            base = seg.base_level
            base_indent = 720 * (seg.display_level + 1)
            for i in range(9):
                rel = i - base
                if rel < 0:
                    # Levels shallower than the segment base are never used
                    # (using one closes the segment); keep them valid.
                    text = '.'.join(f'%{k + 1}' for k in range(i + 1)) + '.'
                    abstract.append(self._lvl(
                        i, 1, 'decimal', text, 720 * (i + 1)))
                    continue
                start = seg.wstart.get(rel, 1)
                style = seg.styles.get(rel, '.')
                placeholders = [f'%{base + k + 1}' for k in range(rel + 1)]
                core = prefix + '.'.join(placeholders)
                if style == ')':
                    text = core + ')'
                elif style == '.':
                    text = core + '.'
                else:
                    text = core
                indent = base_indent + 720 * rel
                abstract.append(self._lvl(i, start, 'decimal', text, indent))
        else:
            fmt = seg.family  # lowerLetter/upperLetter/lowerRoman/upperRoman
            style = seg.styles.get(0, '.')
            text = '%1' + (style if style else '')
            indent = 720 * (seg.display_level + 1)
            abstract.append(self._lvl(0, seg.wstart[0], fmt, text, indent))
            for i in range(1, 9):
                abstract.append(self._lvl(
                    i, 1, 'decimal', f'%{i + 1}.', indent + 720 * i))

        self._pending_abstracts.append(abstract)
        return aid

    def num_for_abstract(self, aid):
        nid = self._next_num
        self._next_num += 1
        num = OxmlElement('w:num')
        num.set(qn('w:numId'), str(nid))
        ref = OxmlElement('w:abstractNumId')
        ref.set(qn('w:val'), str(aid))
        num.append(ref)
        self._pending_nums.append(num)
        return nid

    def flush(self):
        """Insert abstractNums before all nums (schema ordering)."""
        first_num = self._numbering_el.find(qn('w:num'))
        for abstract in self._pending_abstracts:
            if first_num is not None:
                first_num.addprevious(abstract)
            else:
                self._numbering_el.append(abstract)
        for num in self._pending_nums:
            self._numbering_el.append(num)
        self._pending_abstracts = []
        self._pending_nums = []


# --- paragraph surgery --------------------------------------------------------

def _consume_prefix(para, nchars):
    """Remove the first nchars of the paragraph text, plus trailing blanks,
    working across runs and w:tab elements. Run formatting is untouched."""
    remaining = nchars
    eating_ws = False
    for r_el in list(para._p.findall(qn('w:r'))):
        for child in list(r_el):
            if remaining <= 0 and not eating_ws:
                break
            tag = child.tag
            if tag == qn('w:t'):
                text = child.text or ''
                if remaining > 0:
                    cut = min(remaining, len(text))
                    text = text[cut:]
                    remaining -= cut
                    if remaining == 0:
                        eating_ws = True
                if eating_ws:
                    stripped = text.lstrip(' \t')
                    if stripped != text:
                        text = stripped
                    if text:
                        eating_ws = False
                child.text = text
                if text:
                    child.set(qn('xml:space'), 'preserve')
            elif tag == qn('w:tab'):
                if remaining > 0:
                    r_el.remove(child)
                    remaining -= 1
                    if remaining == 0:
                        eating_ws = True
                elif eating_ws:
                    r_el.remove(child)
            elif tag == qn('w:br'):
                eating_ws = False
                if remaining > 0:
                    remaining -= 1
        # Drop runs left with no content (only rPr).
        has_content = any(c.tag not in (qn('w:rPr'),) for c in r_el)
        if not has_content:
            r_el.getparent().remove(r_el)
        if remaining <= 0 and not eating_ws:
            break


def _leading_blank_len(text):
    return len(text) - len(text.lstrip(' \t'))


def _apply_numpr(para, num_id, ilvl):
    p = para._p
    ppr = p.find(qn('w:pPr'))
    if ppr is None:
        ppr = OxmlElement('w:pPr')
        p.insert(0, ppr)
    for tag in ('w:numPr', 'w:ind', 'w:tabs'):
        el = ppr.find(qn(tag))
        if el is not None:
            ppr.remove(el)
    numpr = OxmlElement('w:numPr')
    ilvl_el = OxmlElement('w:ilvl')
    ilvl_el.set(qn('w:val'), str(ilvl))
    numpr.append(ilvl_el)
    numid_el = OxmlElement('w:numId')
    numid_el.set(qn('w:val'), str(num_id))
    numpr.append(numid_el)
    pstyle = ppr.find(qn('w:pStyle'))
    if pstyle is not None:
        pstyle.addnext(numpr)
    else:
        ppr.insert(0, numpr)


def _fix_hybrid(para, marker):
    """Literal fallback: ensure a space after the marker + hanging indent."""
    text = para.text.lstrip(' \t')
    after = text[len(marker):]
    if after and after[0] not in ' \t':
        # Insert a space right after the marker inside the owning run.
        consumed = 0
        target = len(para.text) - len(text) + len(marker)
        for r_el in para._p.findall(qn('w:r')):
            for child in r_el:
                if child.tag == qn('w:t'):
                    t = child.text or ''
                    if consumed + len(t) >= target:
                        pos = target - consumed
                        child.text = t[:pos] + ' ' + t[pos:]
                        child.set(qn('xml:space'), 'preserve')
                        consumed = target
                        break
                    consumed += len(t)
                elif child.tag in (qn('w:tab'), qn('w:br')):
                    consumed += 1
            if consumed >= target:
                break
    pf = para.paragraph_format
    pf.left_indent = Inches(0.6)
    pf.first_line_indent = -Inches(0.35)


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def fix_lists(docx_path, pdf_path=None):
    doc = Document(docx_path)
    scan = prescan_pdf(pdf_path)

    _split_merged_paragraphs(doc)
    _split_at_prescan_lines(doc, scan)
    _fix_toc(doc, scan)
    items, hybrids = _detect_items(doc, scan)

    if items:
        segments = _build_segments(items)
        numbering = _NumberingXML(doc)
        for seg in segments:
            aid = numbering.abstract_for_segment(seg)
            nid = numbering.num_for_abstract(aid)
            for item in seg.items:
                blanks = _leading_blank_len(item.para.text)
                if item.garbled_len:
                    _consume_prefix(item.para, blanks + item.garbled_len)
                else:
                    _consume_prefix(item.para, blanks + len(item.marker))
                if seg.family == 'decimal':
                    # abstractNum levels are indexed by absolute depth
                    ilvl = min(8, len(item.value) - 1)
                elif seg.family == 'bullet':
                    ilvl = min(8, item.level)
                else:
                    ilvl = 0
                _apply_numpr(item.para, nid, ilvl)
        numbering.flush()

    for para, marker in hybrids:
        _fix_hybrid(para, marker)

    doc.save(docx_path)
