import re
from copy import deepcopy

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

BULLET_CHARS = set('•◦▪‣·►●○■◆◇▸–—')
BULLET_PUA = {'', '', '', '', '', ''}

NUM_PATTERN = re.compile(r'^(\d+[.)]\s*)')
ALPHA_LOWER_PATTERN = re.compile(r'^([a-z][.)]\s*)')
ALPHA_UPPER_PATTERN = re.compile(r'^([A-Z][.)]\s*)')
ROMAN_PATTERN = re.compile(r'^([ivxlcdm]+[.)]\s*)', re.IGNORECASE)

TEXT_BULLET_PATTERN = re.compile(r'^[-*]\s+')


def _is_bullet_char(ch):
    return ch in BULLET_CHARS or ch in BULLET_PUA


def _get_para_indent_emu(para):
    pf = para.paragraph_format
    if pf.left_indent is not None:
        return int(pf.left_indent)
    return 0


def detect_marker(para):
    """Detect if a paragraph starts with a bullet or number marker.

    Returns (marker_type, prefix_info, indent_emu) or None.
    marker_type: 'bullet' or 'number'
    prefix_info: dict with 'run_idx', 'char_count', 'delete_run' flag,
                 and 'has_tab' if a tab follows the marker.
    """
    runs = para.runs
    if not runs:
        return None

    text = para.text.strip()
    if not text:
        return None

    indent = _get_para_indent_emu(para)

    first_run_text = runs[0].text

    # Case 1: bullet character is the entire first run (its own span)
    if len(first_run_text.strip()) == 1 and _is_bullet_char(first_run_text.strip()):
        return ('bullet', {'run_idx': 0, 'char_count': 0, 'delete_run': True, 'has_tab': _has_tab_after(runs, 0)}, indent)

    # Case 2: bullet character at start of first run text
    if first_run_text and _is_bullet_char(first_run_text[0]):
        return ('bullet', {'run_idx': 0, 'char_count': 1, 'delete_run': False, 'has_tab': '\t' in first_run_text[:3]}, indent)

    # Case 3: text bullet (- or *)
    m = TEXT_BULLET_PATTERN.match(first_run_text)
    if m:
        return ('bullet', {'run_idx': 0, 'char_count': m.end(), 'delete_run': False, 'has_tab': False}, indent)

    # Case 4: numbered list patterns
    for pattern in [NUM_PATTERN, ALPHA_LOWER_PATTERN, ALPHA_UPPER_PATTERN, ROMAN_PATTERN]:
        m = pattern.match(first_run_text)
        if m:
            return ('number', {'run_idx': 0, 'char_count': m.end(), 'delete_run': False,
                               'has_tab': '\t' in first_run_text[:m.end() + 2],
                               'marker_text': m.group(1).strip()}, indent)

    # Case 5: number marker might be in its own run (e.g., bold "1." in separate run)
    if len(runs) >= 2:
        r0 = first_run_text.strip()
        for pattern in [NUM_PATTERN, ALPHA_LOWER_PATTERN, ALPHA_UPPER_PATTERN, ROMAN_PATTERN]:
            m = pattern.match(r0 + ' ')
            if m and m.end() >= len(r0):
                return ('number', {'run_idx': 0, 'char_count': 0, 'delete_run': True,
                                   'has_tab': _has_tab_after(runs, 0),
                                   'marker_text': r0}, indent)

    return None


def _has_tab_after(runs, marker_run_idx):
    """Check if there's a tab character or <w:tab/> after the marker run."""
    if marker_run_idx + 1 < len(runs):
        next_text = runs[marker_run_idx + 1].text
        if next_text and next_text[0] == '\t':
            return True
    # Check for w:tab element
    marker_el = runs[marker_run_idx]._element
    for sibling in marker_el.itersiblings():
        if sibling.tag == qn('w:r'):
            for child in sibling:
                if child.tag == qn('w:tab'):
                    return True
            break
    return False


def strip_marker(para, prefix_info):
    """Remove the marker characters from the paragraph, preserving all run formatting."""
    runs = para.runs
    if not runs:
        return

    run_idx = prefix_info['run_idx']

    if prefix_info['delete_run']:
        # Delete the entire marker run
        run_el = runs[run_idx]._element
        run_el.getparent().remove(run_el)
        # Remove following tab run/element if present
        _remove_leading_tab(para)
    else:
        char_count = prefix_info['char_count']
        if char_count > 0:
            run = runs[run_idx]
            run.text = run.text[char_count:]
        # Strip leading tabs/spaces from the modified run
        if runs[run_idx].text:
            runs[run_idx].text = runs[run_idx].text.lstrip('\t ')

    # Final cleanup: remove any leading tab runs that remain
    _remove_leading_tab(para)


def _remove_leading_tab(para):
    """Remove a leading tab character or <w:tab/> element from the paragraph."""
    # Check for w:tab elements in the first run
    for r_el in para._p.findall(qn('w:r')):
        has_content = False
        for child in list(r_el):
            if child.tag == qn('w:tab'):
                r_el.remove(child)
                return
            if child.tag == qn('w:t'):
                t_text = child.text or ''
                if t_text.startswith('\t'):
                    child.text = t_text.lstrip('\t')
                    if not child.text:
                        child.text = ''
                return
            if child.tag != qn('w:rPr'):
                has_content = True
        if has_content:
            break

    # Also strip tab from first run text
    runs = para.runs
    if runs and runs[0].text and runs[0].text[0] == '\t':
        runs[0].text = runs[0].text[1:]


class NumberingBuilder:
    """Manages Word numbering XML (word/numbering.xml) for list formatting."""

    def __init__(self, doc):
        self._doc = doc
        self._numbering_part = None
        self._numbering_el = None
        self._next_abstract_id = 1
        self._next_num_id = 1
        self._bullet_abstract_id = None
        self._number_abstract_id = None
        self._current_num_ids = {}
        self._ensure_numbering_part()

    def _ensure_numbering_part(self):
        """Create word/numbering.xml if it doesn't exist."""
        try:
            self._numbering_part = self._doc.part.numbering_part
            self._numbering_el = self._numbering_part.numbering_definitions._numbering
        except Exception:
            self._create_numbering_part()

        # Find existing max IDs to avoid conflicts
        if self._numbering_el is not None:
            for el in self._numbering_el.findall(qn('w:abstractNum')):
                aid = int(el.get(qn('w:abstractNumId'), 0))
                self._next_abstract_id = max(self._next_abstract_id, aid + 1)
            for el in self._numbering_el.findall(qn('w:num')):
                nid = int(el.get(qn('w:numId'), 0))
                self._next_num_id = max(self._next_num_id, nid + 1)

    def _create_numbering_part(self):
        """Create a minimal numbering.xml part."""
        from docx.opc.part import Part
        from docx.opc.packuri import PackURI

        numbering_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '</w:numbering>'
        )
        partname = PackURI('/word/numbering.xml')
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'

        part = Part(
            partname, content_type, numbering_xml.encode('utf-8'),
            self._doc.part.package
        )
        self._doc.part.relate_to(part, RT.NUMBERING)
        self._numbering_el = part.element

    def _get_or_create_abstract(self, list_type):
        """Get or create an abstractNum for bullet or number lists."""
        if list_type == 'bullet':
            if self._bullet_abstract_id is None:
                self._bullet_abstract_id = self._create_bullet_abstract()
            return self._bullet_abstract_id
        else:
            if self._number_abstract_id is None:
                self._number_abstract_id = self._create_number_abstract()
            return self._number_abstract_id

    def _create_bullet_abstract(self):
        aid = self._next_abstract_id
        self._next_abstract_id += 1

        abstract = OxmlElement('w:abstractNum')
        abstract.set(qn('w:abstractNumId'), str(aid))

        bullets = ['•', '○', '▪']  # •, ○, ▪
        indents = [720, 1440, 2160]  # in twips (1/20 pt)

        for i in range(3):
            lvl = OxmlElement('w:lvl')
            lvl.set(qn('w:ilvl'), str(i))

            start = OxmlElement('w:start')
            start.set(qn('w:val'), '1')
            lvl.append(start)

            numFmt = OxmlElement('w:numFmt')
            numFmt.set(qn('w:val'), 'bullet')
            lvl.append(numFmt)

            lvlText = OxmlElement('w:lvlText')
            lvlText.set(qn('w:val'), bullets[i])
            lvl.append(lvlText)

            lvlJc = OxmlElement('w:lvlJc')
            lvlJc.set(qn('w:val'), 'left')
            lvl.append(lvlJc)

            pPr = OxmlElement('w:pPr')
            ind = OxmlElement('w:ind')
            ind.set(qn('w:left'), str(indents[i]))
            ind.set(qn('w:hanging'), '360')
            pPr.append(ind)
            lvl.append(pPr)

            rPr = OxmlElement('w:rPr')
            rFonts = OxmlElement('w:rFonts')
            rFonts.set(qn('w:ascii'), 'Symbol')
            rFonts.set(qn('w:hAnsi'), 'Symbol')
            rFonts.set(qn('w:hint'), 'default')
            rPr.append(rFonts)
            lvl.append(rPr)

            abstract.append(lvl)

        self._numbering_el.append(abstract)
        return aid

    def _create_number_abstract(self):
        aid = self._next_abstract_id
        self._next_abstract_id += 1

        abstract = OxmlElement('w:abstractNum')
        abstract.set(qn('w:abstractNumId'), str(aid))

        formats = ['decimal', 'lowerLetter', 'lowerRoman']
        texts = ['%1.', '%2.', '%3.']
        indents = [720, 1440, 2160]

        for i in range(3):
            lvl = OxmlElement('w:lvl')
            lvl.set(qn('w:ilvl'), str(i))

            start = OxmlElement('w:start')
            start.set(qn('w:val'), '1')
            lvl.append(start)

            numFmt = OxmlElement('w:numFmt')
            numFmt.set(qn('w:val'), formats[i])
            lvl.append(numFmt)

            lvlText = OxmlElement('w:lvlText')
            lvlText.set(qn('w:val'), texts[i])
            lvl.append(lvlText)

            lvlJc = OxmlElement('w:lvlJc')
            lvlJc.set(qn('w:val'), 'left')
            lvl.append(lvlJc)

            pPr = OxmlElement('w:pPr')
            ind = OxmlElement('w:ind')
            ind.set(qn('w:left'), str(indents[i]))
            ind.set(qn('w:hanging'), '360')
            pPr.append(ind)
            lvl.append(pPr)

            abstract.append(lvl)

        self._numbering_el.append(abstract)
        return aid

    def get_num_id(self, list_type, restart=False):
        """Get a num ID for the given list type. Creates a new one on restart."""
        key = list_type
        if restart or key not in self._current_num_ids:
            abstract_id = self._get_or_create_abstract(list_type)
            num_id = self._next_num_id
            self._next_num_id += 1

            num_el = OxmlElement('w:num')
            num_el.set(qn('w:numId'), str(num_id))
            abstractNumId = OxmlElement('w:abstractNumId')
            abstractNumId.set(qn('w:val'), str(abstract_id))
            num_el.append(abstractNumId)

            if restart:
                override = OxmlElement('w:lvlOverride')
                override.set(qn('w:ilvl'), '0')
                startOverride = OxmlElement('w:startOverride')
                startOverride.set(qn('w:val'), '1')
                override.append(startOverride)
                num_el.append(override)

            self._numbering_el.append(num_el)
            self._current_num_ids[key] = num_id

        return self._current_num_ids[key]

    def apply_numbering(self, para, list_type, ilvl, num_id):
        """Inject w:numPr into paragraph properties."""
        pPr = para._p.get_or_add_pPr()

        # Remove any existing numPr
        existing = pPr.find(qn('w:numPr'))
        if existing is not None:
            pPr.remove(existing)

        numPr = OxmlElement('w:numPr')
        ilvl_el = OxmlElement('w:ilvl')
        ilvl_el.set(qn('w:val'), str(ilvl))
        numId_el = OxmlElement('w:numId')
        numId_el.set(qn('w:val'), str(num_id))
        numPr.append(ilvl_el)
        numPr.append(numId_el)
        pPr.insert(0, numPr)

        # Let numbering definition own the indents
        para.paragraph_format.left_indent = None
        para.paragraph_format.first_line_indent = None


def _infer_ilvl(indent_emu, indent_levels):
    """Map an indent value to a nesting level (0, 1, 2)."""
    if not indent_levels:
        return 0
    closest = min(indent_levels, key=lambda x: abs(x - indent_emu))
    return indent_levels.index(closest)


def _cluster_indents(indents, tolerance=10800):
    """Cluster indent values with tolerance (~0.15 inch = 10800 EMU)."""
    if not indents:
        return [0]
    sorted_indents = sorted(set(indents))
    clusters = [sorted_indents[0]]
    for v in sorted_indents[1:]:
        if v - clusters[-1] > tolerance:
            clusters.append(v)
    return clusters


def _should_restart_numbering(marker_info):
    """Check if this numbered item starts a new sequence (e.g., "1." after a gap)."""
    if marker_info[0] != 'number':
        return False
    prefix_info = marker_info[1]
    marker_text = prefix_info.get('marker_text', '')
    return marker_text.rstrip('.)') in ('1', 'a', 'A', 'i', 'I')


def fix_lists(docx_path):
    """Post-process a DOCX file to convert detected list patterns to proper Word lists."""
    doc = Document(docx_path)
    paragraphs = list(doc.paragraphs)

    if not paragraphs:
        return

    # Phase 1: detect markers on all paragraphs
    detections = []
    for i, para in enumerate(paragraphs):
        result = detect_marker(para)
        detections.append(result)

    # Phase 2: filter false positives — require ≥2 consecutive or tab after marker
    for i, det in enumerate(detections):
        if det is None:
            continue
        has_tab = det[1].get('has_tab', False)
        if has_tab:
            continue
        # Check for consecutive match
        has_neighbor = False
        if i > 0 and detections[i - 1] is not None:
            has_neighbor = True
        if i < len(detections) - 1 and detections[i + 1] is not None:
            has_neighbor = True
        if not has_neighbor:
            detections[i] = None

    # Phase 3: group consecutive detections into list runs
    list_runs = []
    current_run = []
    for i, det in enumerate(detections):
        if det is not None:
            current_run.append((i, det))
        else:
            if current_run:
                list_runs.append(current_run)
                current_run = []
    if current_run:
        list_runs.append(current_run)

    if not list_runs:
        return

    # Phase 4: process each list run
    builder = NumberingBuilder(doc)

    for run in list_runs:
        indents = [item[1][2] for item in run]
        indent_levels = _cluster_indents(indents)

        prev_type = None
        num_id = None

        for para_idx, marker_info in run:
            para = paragraphs[para_idx]
            list_type = marker_info[0]
            prefix_info = marker_info[1]
            indent_emu = marker_info[2]

            ilvl = _infer_ilvl(indent_emu, indent_levels)
            ilvl = min(ilvl, 2)  # max 3 levels

            # Determine if we need a new numbering sequence
            restart = False
            if list_type != prev_type:
                restart = True
            elif list_type == 'number' and _should_restart_numbering(marker_info):
                restart = True

            if restart or num_id is None:
                num_id = builder.get_num_id(list_type, restart=(list_type == 'number' and restart))

            prev_type = list_type

            # Strip the marker characters (preserving run formatting)
            strip_marker(para, prefix_info)

            # Apply Word numbering
            builder.apply_numbering(para, list_type, ilvl, num_id)

    doc.save(docx_path)
