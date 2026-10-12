#!/usr/bin/env bash
# Start the backend (port 8000) and the Angular dev server (port 4200, proxies /api).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"; }
.venv/bin/uvicorn app.main:app --reload --port 8000 &
BACK=$!
trap 'kill $BACK' EXIT
cd "$ROOT/frontend"
[ -d node_modules ] || npm ci
npx ng serve --open
