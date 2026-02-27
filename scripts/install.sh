#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERRO] python3 não encontrado."
  echo "Termux: pkg install python"
  exit 1
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"$VENV_DIR/bin/python" -m pip install -e "$ROOT_DIR" >/dev/null

mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/clawlite" "$BIN_DIR/clawlite"

echo "[OK] ClawLite instalado em $VENV_DIR"
echo "[INFO] Adicione ao PATH se necessário: export PATH=\"$HOME/.local/bin:$PATH\""
echo "Teste: clawlite doctor"
