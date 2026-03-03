#!/usr/bin/env bash
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "usage: scripts/restore_clawlite.sh <backup-file.tar.gz>"
  exit 1
fi
ARCHIVE="$1"
if [ ! -f "$ARCHIVE" ]; then
  echo "file not found: $ARCHIVE"
  exit 1
fi

tar -xzf "$ARCHIVE" -C "$HOME"
echo "restore completed from: $ARCHIVE"
