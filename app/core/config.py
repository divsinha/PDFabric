import sys
from pathlib import Path

FROZEN = getattr(sys, 'frozen', False)

if FROZEN:
    # PyInstaller --onefile: exe location for user data, _MEIPASS for bundled code
    BASE_DIR = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parents[2]
    BUNDLE_DIR = BASE_DIR

TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"


def _resolve_libreoffice():
    if FROZEN:
        portable = (
            BASE_DIR / "LibreOfficePortable" / "App"
            / "libreoffice" / "program" / "soffice.exe"
        )
        if portable.exists():
            return str(portable)
    return "soffice"


LIBREOFFICE_PATH = _resolve_libreoffice()

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB

ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_CONVERT_EXTENSIONS = {".docx", ".doc", ".pptx", ".ppt"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
