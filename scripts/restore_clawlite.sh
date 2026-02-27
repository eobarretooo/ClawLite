#!/usr/bin/env bash
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "uso: scripts/restore_clawlite.sh <arquivo-backup.tar.gz>"
  exit 1
fi
ARCHIVE="$1"
if [ ! -f "$ARCHIVE" ]; then
  echo "arquivo não encontrado: $ARCHIVE"
  exit 1
fi

tar -xzf "$ARCHIVE" -C "$HOME"
echo "restore concluído de: $ARCHIVE"
