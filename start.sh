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
