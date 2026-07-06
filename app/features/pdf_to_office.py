import io
import shutil
from pathlib import Path

import fitz
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import TEMP_DIR
from app.core.exceptions import ConversionError
from app.core.file_manager import cleanup_file, get_output_path, save_upload

router = APIRouter(prefix="/api/pdf-to-office", tags=["pdf-to-office"])

ALLOWED_FORMATS = {"docx", "pptx"}

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def convert_pdf_to_docx(input_path: str) -> str:
    from pdf2docx import Converter

    out_path = str(get_output_path(".docx"))
    try:
        cv = Converter(input_path)
        cv.convert(out_path)
        cv.close()
    except Exception as e:
        raise ConversionError(f"PDF to DOCX conversion failed: {e}")

    if not Path(out_path).exists():
        raise ConversionError("Conversion produced no output file")

    try:
        from app.features.docx_list_fixer import fix_lists
        fix_lists(out_path, pdf_path=input_path)
    except Exception:
        # Never break the conversion, but make failures visible in the console
        # instead of silently shipping the unfixed document.
        import traceback
        traceback.print_exc()

    return out_path


def convert_pdf_to_pptx(input_path: str) -> str:
    out_path = str(get_output_path(".pptx"))
    try:
        from app.features.pdf_to_pptx import convert
        convert(input_path, out_path)
    except Exception as e:
        raise ConversionError(f"PDF to PPTX conversion failed: {e}")
    if not Path(out_path).exists():
        raise ConversionError("Conversion produced no output file")
    return out_path


@router.post("/")
async def pdf_to_office_endpoint(
    file: UploadFile = File(...),
    format: str = Form("docx"),
):
    fmt = format.lower().strip()
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}. Use 'docx' or 'pptx'.")

    suffix = Path(file.filename).suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    temp_path = save_upload(file)
    try:
        if fmt == "docx":
            out_path = convert_pdf_to_docx(str(temp_path))
        else:
            out_path = convert_pdf_to_pptx(str(temp_path))

        stem = Path(file.filename).stem
        return FileResponse(
            path=out_path,
            media_type=MEDIA_TYPES[fmt],
            filename=f"{stem}.{fmt}",
        )
    finally:
        cleanup_file(temp_path)
