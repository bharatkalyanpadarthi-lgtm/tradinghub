#!/usr/bin/env bash
set -euo pipefail

# Standard runtime working directory for the dashboard launchd job.
# We cd into the runtime root first so .env loads from the same place
# as the backend, then drop into dashboard/ to run the Next.js server.
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

# The dashboard proxies API calls server-side so the admin token stays
# out of the browser bundle. Keep the backend URL available at runtime.
export TRADENEST_BACKEND_URL="${TRADENEST_BACKEND_URL:-http://127.0.0.1:8000}"

cd dashboard

printf '[%s] starting tradenest dashboard in %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)"

# exec so launchd tracks the real Node PID rather than this wrapper.
exec npm run start -- --hostname 127.0.0.1 --port 3000
