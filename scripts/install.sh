#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd 2>/dev/null || true)"
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/eobarretooo/ClawLite.git"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERRO] python3 não encontrado."
  echo "Termux: pkg install python"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "[ERRO] git não encontrado."
  echo "Termux: pkg install git"
  exit 1
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null

# Se executado via curl|bash, não existe pyproject local.
if [ -n "${ROOT_DIR}" ] && [ -f "$ROOT_DIR/pyproject.toml" ]; then
  "$VENV_DIR/bin/python" -m pip install -e "$ROOT_DIR" >/dev/null
else
  "$VENV_DIR/bin/python" -m pip install "git+${REPO_URL}" >/dev/null
fi

mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/clawlite" "$BIN_DIR/clawlite"

# Ajustes automáticos pós-instalação (sem interação)
"$VENV_DIR/bin/python" - <<'PY'
import secrets
from clawlite.config.settings import load_config, save_config
from clawlite.runtime.workspace import init_workspace

cfg = load_config()
init_workspace()
if not cfg.get('gateway', {}).get('token'):
    cfg.setdefault('gateway', {})['token'] = secrets.token_urlsafe(24)
save_config(cfg)
print('[OK] Configuração inicial aplicada (workspace + gateway token).')
PY

echo "[OK] ClawLite instalado em $VENV_DIR"
echo "[INFO] Adicione ao PATH se necessário: export PATH=\"$HOME/.local/bin:$PATH\""

echo "[INFO] Rodando diagnóstico automático..."
"$VENV_DIR/bin/clawlite" doctor || true

echo "[NEXT] Rode: clawlite onboarding"
