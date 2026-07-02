@echo off
cd /d %~dp0

if not exist venv (
    echo [PDFabric] Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo [PDFabric] Installing dependencies...
pip install -r requirements.txt -q

if not exist "app\frontend\lib\pdf.min.js" (
    echo [PDFabric] Downloading PDF.js...
    mkdir app\frontend\lib 2>nul
    curl -sSL "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-4.4.168.tgz" -o "%TEMP%\pdfjs.tgz"
    tar -xzf "%TEMP%\pdfjs.tgz" -C "%TEMP%"
    copy "%TEMP%\package\legacy\build\pdf.min.mjs"        "app\frontend\lib\pdf.min.js"
    copy "%TEMP%\package\legacy\build\pdf.worker.min.mjs" "app\frontend\lib\pdf.worker.min.js"
    echo [PDFabric] PDF.js ready.
)

echo [PDFabric] Starting server at http://localhost:8000
start "" http://localhost:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
