import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.core.config import TEMP_DIR, OUTPUT_DIR


def save_upload(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename).suffix.lower()
    dest = TEMP_DIR / f"{uuid.uuid4()}{suffix}"
    with dest.open("wb") as f:
        content = upload_file.file.read()
        f.write(content)
    return dest


def get_output_path(suffix: str) -> Path:
    return OUTPUT_DIR / f"{uuid.uuid4()}{suffix}"


def get_temp_path(suffix: str) -> Path:
    return TEMP_DIR / f"{uuid.uuid4()}{suffix}"


def cleanup_file(path: Path) -> None:
    try:
        if path and path.exists():
            path.unlink()
    except OSError:
        pass


def make_zip(file_paths: list[Path]) -> Path:
    zip_path = get_output_path(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, fp in enumerate(file_paths):
            zf.write(fp, arcname=f"part_{i + 1}.pdf")
    return zip_path
