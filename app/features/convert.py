import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.core.config import ALLOWED_CONVERT_EXTENSIONS, LIBREOFFICE_PATH, TEMP_DIR
from app.core.exceptions import ConversionError, LibreOfficeNotFoundError, UnsupportedFileTypeError
from app.core.file_manager import cleanup_file, get_output_path, save_upload

router = APIRouter(prefix="/api/convert", tags=["convert"])


def verify_libreoffice(soffice_path: str = LIBREOFFICE_PATH) -> bool:
    """Returns True if soffice is found and executable."""
    resolved = shutil.which(soffice_path) or soffice_path
    return os.path.isfile(resolved) and os.access(resolved, os.X_OK)


def convert_to_pdf(input_path: str, soffice_path: str = LIBREOFFICE_PATH) -> str:
    """Convert DOCX/PPTX to PDF using LibreOffice headless. Returns output PDF path."""
    suffix = Path(input_path).suffix.lower()
    if suffix not in ALLOWED_CONVERT_EXTENSIONS:
        raise UnsupportedFileTypeError(f"Unsupported file type: {suffix}")

    resolved = shutil.which(soffice_path) or soffice_path
    if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        raise LibreOfficeNotFoundError(
            f"LibreOffice not found at '{soffice_path}'. "
            "Install LibreOffice or set LIBREOFFICE_PATH in config.py."
        )

    out_dir = str(TEMP_DIR)
    try:
        result = subprocess.run(
            [resolved, "--headless", "--convert-to", "pdf", "--outdir", out_dir, input_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("LibreOffice conversion timed out after 30 seconds")

    if result.returncode != 0:
        raise ConversionError(f"LibreOffice failed: {result.stderr.strip()}")

    # LibreOffice writes <original_stem>.pdf in out_dir
    stem = Path(input_path).stem
    converted = Path(out_dir) / f"{stem}.pdf"
    if not converted.exists():
        raise ConversionError("Conversion produced no output file")

    # Move to a uuid-named output path
    out_path = get_output_path(".pdf")
    shutil.move(str(converted), str(out_path))
    return str(out_path)


@router.post("/")
async def convert_endpoint(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_CONVERT_EXTENSIONS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    temp_path = save_upload(file)
    try:
        out_path = convert_to_pdf(str(temp_path))
        stem = Path(file.filename).stem
        return FileResponse(
            path=out_path,
            media_type="application/pdf",
            filename=f"{stem}.pdf",
        )
    finally:
        cleanup_file(temp_path)
