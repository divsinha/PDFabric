import os
import fitz
from pathlib import Path
from PIL import Image

os.environ.setdefault("PYTHONPATH", str(Path(__file__).parents[1]))

from app.core.config import TEMP_DIR, OUTPUT_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from app.features.signature import add_signature

SAMPLE = str(Path(__file__).parent / "fixtures" / "sample.pdf")
SIG_PNG = str(Path(__file__).parent / "fixtures" / "signature.png")


def _make_sig():
    img = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "John Doe", fill=(0, 0, 200, 255))
    img.save(SIG_PNG)


def test_add_signature():
    _make_sig()
    out = add_signature(SAMPLE, SIG_PNG, page_num=0, rect={"x": 400, "y": 700, "width": 150, "height": 50})
    doc = fitz.open(out)
    assert doc.page_count == 5
    doc.close()
    Path(out).unlink(missing_ok=True)
