import os
from pathlib import Path

os.environ.setdefault("PYTHONPATH", str(Path(__file__).parents[1]))

from app.core.config import TEMP_DIR, OUTPUT_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from app.features.convert import verify_libreoffice


def test_verify_libreoffice_default():
    # Just checks the function returns a bool; may be False if LO not installed
    result = verify_libreoffice()
    assert isinstance(result, bool)
