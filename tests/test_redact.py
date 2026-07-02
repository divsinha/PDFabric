import os
import fitz
from pathlib import Path

os.environ.setdefault("PYTHONPATH", str(Path(__file__).parents[1]))

from app.core.config import TEMP_DIR, OUTPUT_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from app.features.redact import redact_by_text, redact_by_area

SAMPLE = str(Path(__file__).parent / "fixtures" / "sample.pdf")


def test_redact_text_removes_content():
    out_path, report = redact_by_text(SAMPLE, ["CONFIDENTIAL"], case_sensitive=True)
    doc = fitz.open(out_path)
    for page in doc:
        text = page.get_text()
        assert "CONFIDENTIAL" not in text
    doc.close()
    Path(out_path).unlink(missing_ok=True)


def test_redact_text_report():
    _, report = redact_by_text(SAMPLE, ["CONFIDENTIAL"], case_sensitive=True)
    # Sample PDF has "CONFIDENTIAL" on every page
    assert len(report) > 0


def test_redact_area():
    out_path = redact_by_area(SAMPLE, [{"page": 0, "x": 60, "y": 60, "width": 400, "height": 50}])
    doc = fitz.open(out_path)
    assert doc.page_count == 5
    doc.close()
    Path(out_path).unlink(missing_ok=True)
