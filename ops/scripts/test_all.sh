#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${TRADENEST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

cd "$ROOT_DIR"
"$PYTHON_BIN" -m pytest -q

cd "$ROOT_DIR/dashboard"
npm run typecheck
npm run build
