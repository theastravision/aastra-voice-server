#!/usr/bin/env bash
# Build React interview-ui for Salad /production (/interview route).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="$ROOT/interview-ui"
DIST="$UI_DIR/dist"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. On Salad run:"
  echo "  sudo apt-get update && sudo apt-get install -y nodejs npm"
  echo "Or: bash scripts/salad-run.sh --install   (installs Node + builds UI)"
  exit 1
fi

if [[ ! -d "$UI_DIR" ]]; then
  echo "Missing $UI_DIR"
  exit 1
fi

echo "==> Building interview-ui (React) for /interview"
cd "$UI_DIR"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build

if [[ ! -f "$DIST/index.html" ]]; then
  echo "Build failed: $DIST/index.html not found"
  exit 1
fi

echo "==> OK: $DIST"
echo "    Open: http://127.0.0.1:\${PORT:-8000}/interview"
