#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "[PDFabric] Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "[PDFabric] Installing dependencies..."
pip install -r requirements.txt -q

# Download PDF.js if not already present
PDFJS_DIR="app/frontend/lib"
if [ ! -f "$PDFJS_DIR/pdf.min.js" ] || [ ! -f "$PDFJS_DIR/pdf.worker.min.js" ]; then
  echo "[PDFabric] Downloading PDF.js..."
  mkdir -p "$PDFJS_DIR"
  TMP=$(mktemp -d)
  # npm registry is reachable without special config
  curl -sSL "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-4.4.168.tgz" -o "$TMP/pdfjs.tgz"
  tar -xzf "$TMP/pdfjs.tgz" -C "$TMP/"
  cp "$TMP/package/legacy/build/pdf.min.mjs"        "$PDFJS_DIR/pdf.min.js"
  cp "$TMP/package/legacy/build/pdf.worker.min.mjs" "$PDFJS_DIR/pdf.worker.min.js"
  rm -rf "$TMP"
  echo "[PDFabric] PDF.js ready."
fi

echo "[PDFabric] Starting server at http://localhost:8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

sleep 2
if command -v open &>/dev/null; then
  open http://localhost:8000
elif command -v xdg-open &>/dev/null; then
  xdg-open http://localhost:8000
fi

wait $SERVER_PID
