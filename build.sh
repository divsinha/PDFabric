#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "[PDFabric] Installing build dependencies..."
pip install pyinstaller -q

PDFJS_DIR="app/frontend/lib"
if [ ! -f "$PDFJS_DIR/pdf.min.js" ]; then
    echo "[PDFabric] Downloading PDF.js..."
    mkdir -p "$PDFJS_DIR"
    TMP=$(mktemp -d)
    curl -sSL "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-4.4.168.tgz" -o "$TMP/pdfjs.tgz"
    tar -xzf "$TMP/pdfjs.tgz" -C "$TMP/"
    cp "$TMP/package/legacy/build/pdf.min.mjs"        "$PDFJS_DIR/pdf.min.js"
    cp "$TMP/package/legacy/build/pdf.worker.min.mjs" "$PDFJS_DIR/pdf.worker.min.js"
    rm -rf "$TMP"
    echo "[PDFabric] PDF.js ready."
fi

echo "[PDFabric] Building executable..."
python -m PyInstaller pdfabric.spec --clean --noconfirm

echo ""
echo "[PDFabric] Build complete! Output: dist/PDFabric"
