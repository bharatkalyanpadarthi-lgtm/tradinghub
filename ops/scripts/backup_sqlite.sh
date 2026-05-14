#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${TRADENEST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DB_PATH="${TRADENEST_DB_PATH:-$ROOT_DIR/data/tradenest.sqlite3}"
BACKUP_DIR="${TRADENEST_BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${TRADENEST_BACKUP_RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
  printf 'database not found: %s\n' "$DB_PATH" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$BACKUP_DIR/tradenest-$timestamp.sqlite3"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$backup_path'"
else
  cp "$DB_PATH" "$backup_path"
  [ -f "$DB_PATH-wal" ] && cp "$DB_PATH-wal" "$backup_path-wal"
  [ -f "$DB_PATH-shm" ] && cp "$DB_PATH-shm" "$backup_path-shm"
fi

find "$BACKUP_DIR" -name 'tradenest-*.sqlite3*' -type f -mtime +"$RETENTION_DAYS" -delete

printf 'backup written: %s\n' "$backup_path"
