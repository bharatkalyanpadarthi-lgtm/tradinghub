#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${TRADENEST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
LOG_DIR="${TRADENEST_LOG_DIR:-$ROOT_DIR/logs}"
MAX_SIZE_MB="${TRADENEST_LOG_MAX_SIZE_MB:-25}"
RETENTION_DAYS="${TRADENEST_LOG_RETENTION_DAYS:-14}"

mkdir -p "$LOG_DIR"

find "$LOG_DIR" -type f -name '*.log' -size +"${MAX_SIZE_MB}"M | while read -r log_file; do
  rotated="$log_file.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$log_file" "$rotated"
  gzip -f "$rotated"
  : > "$log_file"
  printf 'rotated: %s\n' "$log_file"
done

find "$LOG_DIR" -type f \( -name '*.log.*.gz' -o -name '*.log.*' \) -mtime +"$RETENTION_DAYS" -delete
