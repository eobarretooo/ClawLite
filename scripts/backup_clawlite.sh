#!/usr/bin/env bash
set -euo pipefail
SRC="${HOME}/.clawlite"
OUT_DIR="${1:-${HOME}/.clawlite/backups}"
TS="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/clawlite-backup-$TS.tar.gz"

tar -czf "$ARCHIVE" \
  -C "$HOME" \
  .clawlite/config.json \
  .clawlite/multiagent.db \
  .clawlite/learning.db \
  .clawlite/workspace 2>/dev/null || true

echo "backup: $ARCHIVE"
