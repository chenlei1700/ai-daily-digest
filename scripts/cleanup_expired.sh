#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
LOG="$HOME/Library/Logs/ai-daily-digest/cleanup.log"

mkdir -p "$(dirname "$LOG")"

# Remove expired generated artifacts. `-mtime +0` means older than 24 hours.
find "$ROOT/output" -mindepth 1 -type f -mtime +0 -delete 2>/dev/null || true
find "$ROOT/output" -mindepth 1 -type d -empty -delete 2>/dev/null || true
find "$ROOT/data/wiki" -type f -name '*.md' -mtime +0 -delete 2>/dev/null || true
find "$ROOT/data/wiki" -mindepth 1 -type d -empty -delete 2>/dev/null || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] cleanup ran" >> "$LOG"
