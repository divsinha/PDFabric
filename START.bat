@echo off
cd /d %~dp0

if not exist venv (
    echo [PDFabric] Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo [PDFabric] Installing dependencies...
pip install -r requirements.txt -q

echo [PDFabric] Starting server at http://localhost:8000
start "" http://localhost:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
