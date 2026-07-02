from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

# Override this to the portable soffice binary path if needed
LIBREOFFICE_PATH = "soffice"

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB

ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_CONVERT_EXTENSIONS = {".docx", ".doc", ".pptx", ".ppt"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
