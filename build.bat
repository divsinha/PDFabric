@echo off
cd /d %~dp0

echo [PDFabric] Installing build dependencies...
pip install pyinstaller -q

if not exist "app\frontend\lib\pdf.min.js" (
    echo [PDFabric] Downloading PDF.js...
    mkdir app\frontend\lib 2>nul
    curl -sSL "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-4.4.168.tgz" -o "%TEMP%\pdfjs.tgz"
    tar -xzf "%TEMP%\pdfjs.tgz" -C "%TEMP%"
    copy "%TEMP%\package\legacy\build\pdf.min.mjs"        "app\frontend\lib\pdf.min.js"
    copy "%TEMP%\package\legacy\build\pdf.worker.min.mjs" "app\frontend\lib\pdf.worker.min.js"
    echo [PDFabric] PDF.js ready.
)

echo [PDFabric] Building executable...
python -m PyInstaller pdfabric.spec --clean --noconfirm

echo.
echo [PDFabric] Build complete!
echo Output: dist\PDFabric.exe
pause
