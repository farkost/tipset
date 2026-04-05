#!/usr/bin/env bash
# Serves this project on localhost (Flask + SQLite) and opens an ngrok HTTP tunnel (foreground).
# Requires: Python 3, pip install -r requirements.txt, ngrok CLI — https://ngrok.com/download
# One-time: ngrok config add-authtoken <token>
#
# Usage: ./scripts/start-tunnel.sh
#        PORT=9000 ./scripts/start-tunnel.sh

set -euo pipefail

PORT="${PORT:-8080}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! python3 -c "import flask" 2>/dev/null; then
  echo "Install dependencies: pip3 install -r requirements.txt"
  exit 1
fi

python3 "$ROOT/server.py" --port "$PORT" --host 127.0.0.1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Local: http://127.0.0.1:${PORT}/  (SQLite under data/)"
echo ""

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok not found in PATH. Install: https://ngrok.com/download"
  echo "Server PID ${SERVER_PID}; Ctrl+C to stop."
  wait "$SERVER_PID"
  exit 0
fi

ngrok http "$PORT"
