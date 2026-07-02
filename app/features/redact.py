import json

import fitz
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.exceptions import InvalidPDFError
from app.core.file_manager import cleanup_file, get_output_path, save_upload

router = APIRouter(prefix="/api/redact", tags=["redact"])


def redact_by_text(
    input_path: str, terms: list[str], case_sensitive: bool = False
) -> tuple[str, dict]:
    """
    Search for terms and permanently redact all occurrences.
    Returns (output_path, report) where report maps page number to hit count.
    """
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        raise InvalidPDFError(f"Cannot open PDF: {e}")

    report = {}
    flags = fitz.TEXT_PRESERVE_WHITESPACE
    if not case_sensitive:
        flags |= fitz.TEXT_DEHYPHENATE

    for page in doc:
        count = 0
        for term in terms:
            hits = page.search_for(term, quads=False)
            if not case_sensitive:
                hits += page.search_for(term.lower(), quads=False)
                hits += page.search_for(term.upper(), quads=False)
                hits += page.search_for(term.title(), quads=False)
                # deduplicate by converting to tuples
                seen = set()
                unique = []
                for r in hits:
                    key = (round(r.x0), round(r.y0), round(r.x1), round(r.y1))
                    if key not in seen:
                        seen.add(key)
                        unique.append(r)
                hits = unique

            for rect in hits:
                page.add_redact_annot(rect, fill=(0, 0, 0))
                count += 1

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        if count:
            report[str(page.number + 1)] = count

    out_path = get_output_path(".pdf")
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()
    return str(out_path), report


def redact_by_area(input_path: str, areas: list[dict]) -> str:
    """
    areas: [{"page": 0, "x": float, "y": float, "width": float, "height": float}]
    Coordinates are in PDF points (72 dpi space), 0-based page index.
    """
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        raise InvalidPDFError(f"Cannot open PDF: {e}")

    pages_touched: set[int] = set()

    for area in areas:
        page_idx = int(area["page"])
        if page_idx < 0 or page_idx >= doc.page_count:
            continue
        page = doc[page_idx]
        x, y, w, h = area["x"], area["y"], area["width"], area["height"]
        rect = fitz.Rect(x, y, x + w, y + h)
        page.add_redact_annot(rect, fill=(0, 0, 0))
        pages_touched.add(page_idx)

    for idx in pages_touched:
        doc[idx].apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)

    out_path = get_output_path(".pdf")
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()
    return str(out_path)


@router.post("/text")
async def redact_text_endpoint(
    file: UploadFile = File(...),
    terms: str = Form(...),
    case_sensitive: bool = Form(default=False),
):
    temp_path = save_upload(file)
    try:
        term_list = [t.strip() for t in json.loads(terms) if t.strip()]
        out_path, report = redact_by_text(str(temp_path), term_list, case_sensitive)
        from fastapi.responses import JSONResponse
        # Return the file path and report; client downloads via /api/download
        return JSONResponse({"output": out_path, "report": report})
    finally:
        cleanup_file(temp_path)


@router.post("/text/download")
async def redact_text_download(
    file: UploadFile = File(...),
    terms: str = Form(...),
    case_sensitive: bool = Form(default=False),
):
    temp_path = save_upload(file)
    try:
        term_list = [t.strip() for t in json.loads(terms) if t.strip()]
        out_path, report = redact_by_text(str(temp_path), term_list, case_sensitive)
        return FileResponse(
            path=out_path,
            media_type="application/pdf",
            filename="redacted.pdf",
            headers={"X-Redaction-Report": json.dumps(report)},
        )
    finally:
        cleanup_file(temp_path)


@router.post("/area")
async def redact_area_endpoint(
    file: UploadFile = File(...),
    areas: str = Form(...),
):
    temp_path = save_upload(file)
    try:
        area_list: list[dict] = json.loads(areas)
        out_path = redact_by_area(str(temp_path), area_list)
        return FileResponse(
            path=out_path,
            media_type="application/pdf",
            filename="redacted.pdf",
        )
    finally:
        cleanup_file(temp_path)
