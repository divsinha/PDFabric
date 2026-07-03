from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import LIBREOFFICE_PATH, OUTPUT_DIR, TEMP_DIR
from app.core.exceptions import PDFabricError
from app.features import convert, merge, pdf_to_office, redact, signature, split
from app.features.convert import verify_libreoffice

app = FastAPI(title="PDFabric")

# Feature routers
app.include_router(split.router)
app.include_router(merge.router)
app.include_router(redact.router)
app.include_router(convert.router)
app.include_router(signature.router)
app.include_router(pdf_to_office.router)


@app.get("/api/health")
def health():
    lo_ok = verify_libreoffice(LIBREOFFICE_PATH)
    return {
        "status": "ok",
        "libreoffice": lo_ok,
        "libreoffice_path": LIBREOFFICE_PATH,
    }


@app.exception_handler(PDFabricError)
async def pdfabric_error_handler(request: Request, exc: PDFabricError):
    return JSONResponse(
        status_code=400,
        content={"error": exc.message, "code": exc.code},
    )


@app.on_event("startup")
async def startup():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not verify_libreoffice(LIBREOFFICE_PATH):
        print(
            f"[PDFabric] WARNING: LibreOffice not found at '{LIBREOFFICE_PATH}'. "
            "DOCX/PPTX conversion will not work. "
            "Install LibreOffice or set LIBREOFFICE_PATH in app/core/config.py."
        )


# Serve frontend — must be last so API routes take priority
from app.core.config import BUNDLE_DIR
FRONTEND_DIR = BUNDLE_DIR / "app" / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
