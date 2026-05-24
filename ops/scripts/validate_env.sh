#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${TRADENEST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

failures=0

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    printf 'missing required env: %s\n' "$name" >&2
    failures=$((failures + 1))
  else
    printf 'ok: %s is set\n' "$name"
  fi
}

require_env TRADINGVIEW_PATH_TOKEN
require_env TRADINGVIEW_AUTH_TOKEN
require_env TRADENEST_ADMIN_TOKEN

DB_PATH="${TRADENEST_DB_PATH:-$ROOT_DIR/data/tradenest.sqlite3}"
DB_DIR="$(dirname "$DB_PATH")"
if mkdir -p "$DB_DIR" && touch "$DB_DIR/.tradenest-write-test"; then
  rm -f "$DB_DIR/.tradenest-write-test"
  printf 'ok: TRADENEST_DB_PATH directory writable: %s\n' "$DB_DIR"
else
  printf 'database directory is not writable: %s\n' "$DB_DIR" >&2
  failures=$((failures + 1))
fi

if [ "${TRADENEST_TELEGRAM_ENABLED:-true}" = "true" ]; then
  require_env TELEGRAM_BOT_TOKEN
  require_env TELEGRAM_ALLOWED_CHAT_ID
  require_env TRADENEST_TELEGRAM_WEBHOOK_SECRET_TOKEN
fi

exit "$failures"
