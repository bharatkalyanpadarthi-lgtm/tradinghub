#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${TRADENEST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

BACKEND_URL="${TRADENEST_BACKEND_URL:-http://127.0.0.1:8000}"
DASHBOARD_URL="${TRADENEST_DASHBOARD_URL:-http://127.0.0.1:3000}"
DB_PATH="${TRADENEST_DB_PATH:-$ROOT_DIR/data/tradenest.sqlite3}"
MIN_FREE_MB="${TRADENEST_MIN_DISK_FREE_MB:-1024}"

failures=0

check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'ok: %s\n' "$label"
  else
    printf 'fail: %s\n' "$label" >&2
    failures=$((failures + 1))
  fi
}

backend_status() {
  if [ -z "${TRADENEST_ADMIN_TOKEN:-}" ]; then
    printf 'TRADENEST_ADMIN_TOKEN is required for /api/status\n' >&2
    return 1
  fi
  curl -fsS \
    -H "X-TradeNest-Admin-Token: $TRADENEST_ADMIN_TOKEN" \
    "$BACKEND_URL/api/status" >/dev/null
}

check "backend /api/status reachable" backend_status

check "sqlite database exists" test -f "$DB_PATH"
check "sqlite database writable" test -w "$DB_PATH"

if curl -fsS "$DASHBOARD_URL" >/dev/null 2>&1; then
  printf 'ok: dashboard reachable\n'
else
  printf 'warn: dashboard not reachable at %s\n' "$DASHBOARD_URL" >&2
fi

free_mb="$(df -Pm "$ROOT_DIR" | awk 'NR==2 {print $4}')"
if [ "${free_mb:-0}" -ge "$MIN_FREE_MB" ]; then
  printf 'ok: disk free %s MB >= %s MB\n' "$free_mb" "$MIN_FREE_MB"
else
  printf 'fail: disk free %s MB < %s MB\n' "$free_mb" "$MIN_FREE_MB" >&2
  failures=$((failures + 1))
fi

exit "$failures"
