import os
import pytest
import fitz
from pathlib import Path

os.environ.setdefault("PYTHONPATH", str(Path(__file__).parents[1]))

from app.core.config import TEMP_DIR, OUTPUT_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from app.features.merge import merge_pdfs

SAMPLE = str(Path(__file__).parent / "fixtures" / "sample.pdf")


def test_merge_two_copies():
    out = merge_pdfs([SAMPLE, SAMPLE])
    doc = fitz.open(out)
    assert doc.page_count == 10
    doc.close()
    Path(out).unlink(missing_ok=True)


def test_merge_with_page_selections():
    out = merge_pdfs([SAMPLE, SAMPLE], page_selections={"0": [1, 2], "1": [3]})
    doc = fitz.open(out)
    assert doc.page_count == 3
    doc.close()
    Path(out).unlink(missing_ok=True)
