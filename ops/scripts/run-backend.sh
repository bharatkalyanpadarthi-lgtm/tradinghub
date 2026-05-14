#!/usr/bin/env bash
set -euo pipefail

# Standard runtime working directory for the backend launchd job.
# Repo files are the source of truth and live elsewhere; this directory
# is the deployed runtime copy that macOS launchd is allowed to read.
cd "$HOME/tradenest-runtime"

if [ ! -f ".env" ]; then
  echo "FATAL: .env missing in $(pwd)" >&2
  exit 1
fi

# Export every variable defined in .env so child processes inherit them.
set -a
# shellcheck disable=SC1091
source ".env"
set +a

printf '[%s] starting tradenest backend in %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)"

# exec so launchd tracks the real Python PID rather than this wrapper.
exec .venv/bin/python -m uvicorn tradenest.main:app \
  --host 127.0.0.1 --port 8000
