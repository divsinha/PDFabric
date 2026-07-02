import json
from pathlib import Path

import fitz
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.exceptions import InvalidPDFError
from app.core.file_manager import cleanup_file, get_output_path, save_upload

router = APIRouter(prefix="/api/merge", tags=["merge"])


def merge_pdfs(input_paths: list[str], page_selections: dict | None = None) -> str:
    """
    Merge PDFs in order. page_selections maps index str to list of 1-based page numbers
    (or None to include all pages).
    Returns output file path.
    """
    out_doc = fitz.open()

    for i, path in enumerate(input_paths):
        try:
            src = fitz.open(path)
        except Exception as e:
            raise InvalidPDFError(f"Cannot open PDF {path}: {e}")

        sel = page_selections.get(str(i)) if page_selections else None

        if sel is None:
            out_doc.insert_pdf(src)
        else:
            for page_num in sel:
                idx = int(page_num) - 1  # convert 1-based to 0-based
                if 0 <= idx < src.page_count:
                    out_doc.insert_pdf(src, from_page=idx, to_page=idx)
        src.close()

    out_path = get_output_path(".pdf")
    out_doc.save(str(out_path))
    out_doc.close()
    return str(out_path)


@router.post("/")
async def merge_endpoint(
    files: list[UploadFile] = File(...),
    order: str = Form(default="[]"),
    page_selections: str = Form(default="{}"),
):
    temp_paths: list[Path] = []
    try:
        temp_paths = [save_upload(f) for f in files]

        order_indices: list[int] = json.loads(order)
        if order_indices:
            ordered = [temp_paths[i] for i in order_indices if i < len(temp_paths)]
        else:
            ordered = temp_paths

        selections: dict = json.loads(page_selections)

        out_path = merge_pdfs([str(p) for p in ordered], selections or None)
        return FileResponse(
            path=out_path,
            media_type="application/pdf",
            filename="merged.pdf",
        )
    finally:
        for p in temp_paths:
            cleanup_file(p)
