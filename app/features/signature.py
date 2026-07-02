import json
from pathlib import Path

import fitz
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from app.core.exceptions import InvalidPDFError, PageOutOfRangeError
from app.core.file_manager import cleanup_file, get_output_path, get_temp_path, save_upload

router = APIRouter(prefix="/api/signature", tags=["signature"])


def _prepare_signature_image(image_path: str) -> str:
    """Convert signature image to PNG, preserving transparency where possible."""
    img = Image.open(image_path)
    out_path = get_temp_path(".png")
    if img.mode in ("RGBA", "LA"):
        img.save(str(out_path), format="PNG")
    else:
        img = img.convert("RGBA")
        img.save(str(out_path), format="PNG")
    return str(out_path)


def add_signature(
    input_path: str,
    sig_image_path: str,
    page_num: int,
    rect: dict,
) -> str:
    """
    Place signature image on page_num (0-based) at rect coordinates (PDF points).
    rect: {"x": float, "y": float, "width": float, "height": float}
    """
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        raise InvalidPDFError(f"Cannot open PDF: {e}")

    if page_num < 0 or page_num >= doc.page_count:
        raise PageOutOfRangeError(f"Page {page_num} out of range (0-{doc.page_count - 1})")

    prepared = _prepare_signature_image(sig_image_path)

    page = doc[page_num]
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    placement = fitz.Rect(x, y, x + w, y + h)
    page.insert_image(placement, filename=prepared, keep_proportion=False)

    out_path = get_output_path(".pdf")
    doc.save(str(out_path))
    doc.close()

    cleanup_file(Path(prepared))
    return str(out_path)


@router.post("/")
async def signature_endpoint(
    file: UploadFile = File(...),
    signature: UploadFile = File(...),
    page_num: int = Form(...),
    rect: str = Form(...),
):
    temp_pdf = save_upload(file)
    temp_sig = save_upload(signature)
    try:
        rect_dict: dict = json.loads(rect)
        out_path = add_signature(str(temp_pdf), str(temp_sig), page_num, rect_dict)
        return FileResponse(
            path=out_path,
            media_type="application/pdf",
            filename="signed.pdf",
        )
    finally:
        cleanup_file(temp_pdf)
        cleanup_file(temp_sig)
