import os
import pytest
import fitz
from pathlib import Path

os.environ.setdefault("PYTHONPATH", str(Path(__file__).parents[1]))

from app.core.config import TEMP_DIR, OUTPUT_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from app.features.split import split_pdf
from app.core.exceptions import InvalidPageRangeError, PageOutOfRangeError

SAMPLE = str(Path(__file__).parent / "fixtures" / "sample.pdf")


def test_split_individual():
    paths = split_pdf(SAMPLE, "individual", {})
    assert len(paths) == 5
    for p in paths:
        doc = fitz.open(p)
        assert doc.page_count == 1
        doc.close()
        Path(p).unlink(missing_ok=True)


def test_split_ranges():
    paths = split_pdf(SAMPLE, "ranges", {"ranges": "1-2,4-5"})
    assert len(paths) == 2
    doc1 = fitz.open(paths[0]); assert doc1.page_count == 2; doc1.close()
    doc2 = fitz.open(paths[1]); assert doc2.page_count == 2; doc2.close()
    for p in paths:
        Path(p).unlink(missing_ok=True)


def test_split_every_n():
    paths = split_pdf(SAMPLE, "every_n", {"n": 2})
    assert len(paths) == 3  # pages: 1-2, 3-4, 5
    for p in paths:
        Path(p).unlink(missing_ok=True)


def test_split_invalid_range():
    with pytest.raises(PageOutOfRangeError):
        split_pdf(SAMPLE, "ranges", {"ranges": "1-10"})


def test_split_bad_range_str():
    with pytest.raises(InvalidPageRangeError):
        split_pdf(SAMPLE, "ranges", {"ranges": "abc"})
