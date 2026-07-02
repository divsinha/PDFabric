import re
from pathlib import Path

import fitz
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.exceptions import InvalidPDFError, InvalidPageRangeError, PageOutOfRangeError
from app.core.file_manager import cleanup_file, get_output_path, make_zip, save_upload

router = APIRouter(prefix="/api/split", tags=["split"])


def _parse_ranges(range_str: str, total_pages: int) -> list[list[int]]:
    """Parse '1-3,5,7-10' into list of page index lists (0-based)."""
    groups = []
    for part in re.split(r"[,;]", range_str):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise InvalidPageRangeError(f"Invalid range segment: '{part}'")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start < 1 or end > total_pages or start > end:
            raise PageOutOfRangeError(
                f"Range {start}-{end} out of bounds (1-{total_pages})"
            )
        groups.append(list(range(start - 1, end)))  # convert to 0-based
    if not groups:
        raise InvalidPageRangeError("No valid ranges provided")
    return groups


def split_pdf(input_path: str, mode: str, params: dict) -> list[str]:
    """
    mode: "ranges" | "every_n" | "individual"
    params for "ranges": {"ranges": "1-3,5"}
    params for "every_n": {"n": 2}
    Returns list of output file paths.
    """
    try:
        src = fitz.open(input_path)
    except Exception as e:
        raise InvalidPDFError(f"Cannot open PDF: {e}")

    total = src.page_count
    output_paths = []

    if mode == "individual":
        page_groups = [[i] for i in range(total)]
    elif mode == "every_n":
        n = int(params.get("n", 1))
        if n < 1:
            raise InvalidPageRangeError("n must be >= 1")
        page_groups = [list(range(i, min(i + n, total))) for i in range(0, total, n)]
    elif mode == "ranges":
        page_groups = _parse_ranges(params.get("ranges", ""), total)
    else:
        raise InvalidPageRangeError(f"Unknown mode: {mode}")

    for pages in page_groups:
        out_doc = fitz.open()
        out_doc.insert_pdf(src, from_page=pages[0], to_page=pages[-1])
        out_path = get_output_path(".pdf")
        out_doc.save(str(out_path))
        out_doc.close()
        output_paths.append(str(out_path))

    src.close()
    return output_paths


@router.post("/")
async def split_endpoint(
    file: UploadFile = File(...),
    mode: str = Form(...),
    ranges: str = Form(default=""),
    n: int = Form(default=1),
):
    temp_path = save_upload(file)
    try:
        params = {"ranges": ranges, "n": n}
        output_paths = split_pdf(str(temp_path), mode, params)
        paths = [Path(p) for p in output_paths]

        if len(paths) == 1:
            return FileResponse(
                path=str(paths[0]),
                media_type="application/pdf",
                filename="split.pdf",
            )
        zip_path = make_zip(paths)
        for p in paths:
            cleanup_file(p)
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename="split_pages.zip",
        )
    finally:
        cleanup_file(temp_path)
