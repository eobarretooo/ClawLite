#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd 2>/dev/null || true)"
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/eobarretooo/ClawLite.git"

C_RESET='\033[0m'
C_ORANGE='\033[38;5;208m'
C_CYAN='\033[36m'
C_GREEN='\033[32m'
C_RED='\033[31m'
C_DIM='\033[2m'

ok()   { echo -e "${C_GREEN}✓${C_RESET} $*"; }
info() { echo -e "${C_CYAN}ℹ${C_RESET} $*"; }
err()  { echo -e "${C_RED}✗${C_RESET} $*"; }

print_banner() {
  echo -e "${C_ORANGE}"
  cat <<'EOF'
   =^.^=  ClawLite Installer v0.4.1
      /\_/\
     ( o.o )   Linux + Termux First
      > ^ <
EOF
  echo -e "${C_RESET}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

progress_bar() {
  local pct="$1"
  local filled=$((pct/10))
  local empty=$((10-filled))
  local bar=""
  for _ in $(seq 1 "$filled"); do bar+="█"; done
  for _ in $(seq 1 "$empty"); do bar+="░"; done
  echo -e "${bar} ${pct}%"
}

run_step() {
  local title="$1"
  shift
  echo -e "${C_CYAN}${title}${C_RESET}"
  "$@"
}

run_with_spinner() {
  local msg="$1"
  shift
  local logfile
  logfile="$(mktemp)"
  ("$@") >"$logfile" 2>&1 &
  local pid=$!
  local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$(( (i + 1) % 10 ))
    printf "\r${C_DIM}%s %s${C_RESET}" "${spin:$i:1}" "$msg"
    sleep 0.12
  done
  wait "$pid" || {
    printf "\r"
    cat "$logfile" >&2
    rm -f "$logfile"
    return 1
  }
  rm -f "$logfile"
  printf "\r"
}

is_termux() {
  [[ "${PREFIX:-}" == *"com.termux"* ]] && command -v pkg >/dev/null 2>&1
}

ensure_path() {
  mkdir -p "$BIN_DIR"
  ln -sf "$VENV_DIR/bin/clawlite" "$BIN_DIR/clawlite"

  local export_line='export PATH="$HOME/.local/bin:$PATH"'
  local rc_file
  if [[ "${SHELL:-}" == *"zsh" ]]; then
    rc_file="$HOME/.zshrc"
  else
    rc_file="$HOME/.bashrc"
  fi
  touch "$rc_file"
  if ! grep -Fq "$export_line" "$rc_file"; then
    echo "$export_line" >> "$rc_file"
  fi

  touch "$HOME/.profile"
  if ! grep -Fq "$export_line" "$HOME/.profile"; then
    echo "$export_line" >> "$HOME/.profile"
  fi
}

install_termux_deps() {
  run_with_spinner "Atualizando pacotes do Termux..." pkg update -y
  run_with_spinner "Instalando dependências base (rust/clang/python/git/curl)..." pkg install -y rust clang python git curl
}

install_clawlite() {
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null

  if [ -n "${ROOT_DIR}" ] && [ -f "$ROOT_DIR/pyproject.toml" ]; then
    "$VENV_DIR/bin/python" -m pip install --upgrade --force-reinstall --no-deps -e "$ROOT_DIR" >/dev/null
  else
    "$VENV_DIR/bin/python" -m pip install --upgrade --force-reinstall --no-deps "git+${REPO_URL}" >/dev/null
  fi

  "$VENV_DIR/bin/python" -m pip install --upgrade rich questionary fastapi uvicorn >/dev/null
}

bootstrap_workspace() {
  "$VENV_DIR/bin/python" - <<'PY'
import secrets
from clawlite.config.settings import load_config, save_config
from clawlite.runtime.workspace import init_workspace

cfg = load_config()
init_workspace()
if not cfg.get('gateway', {}).get('token'):
    cfg.setdefault('gateway', {})['token'] = secrets.token_urlsafe(24)
save_config(cfg)
PY
}

verify_install() {
  "$VENV_DIR/bin/clawlite" doctor >/tmp/clawlite-doctor.out 2>&1 || return 1
}

main() {
  print_banner

  echo -e "${C_CYAN}[1/5] Detectando ambiente...${C_RESET}"
  if is_termux; then
    ok "Termux detectado"
  else
    ok "Linux detectado"
  fi

  echo -e "${C_CYAN}[2/5] Instalando dependências...${C_RESET}"
  echo -n "  "
  progress_bar 20
  if is_termux; then
    install_termux_deps || { err "Falha ao instalar dependências no Termux"; exit 1; }
  else
    command -v python3 >/dev/null 2>&1 || { err "python3 não encontrado"; exit 1; }
    command -v git >/dev/null 2>&1 || { err "git não encontrado"; exit 1; }
    command -v curl >/dev/null 2>&1 || { err "curl não encontrado"; exit 1; }
  fi
  echo -n "  "
  progress_bar 80
  ok "Dependências prontas"

  echo -e "${C_CYAN}[3/5] Instalando ClawLite...${C_RESET}"
  run_with_spinner "Instalando pacote e dependências Python..." install_clawlite || { err "Falha na instalação do ClawLite"; exit 1; }
  ok "v0.4.1"

  echo -e "${C_CYAN}[4/5] Configurando workspace...${C_RESET}"
  run_with_spinner "Aplicando configuração inicial..." bootstrap_workspace || { err "Falha ao configurar workspace"; exit 1; }
  ensure_path
  ok "Pronto"

  echo -e "${C_CYAN}[5/5] Verificando instalação...${C_RESET}"
  run_with_spinner "Rodando clawlite doctor..." verify_install || { err "Verificação final falhou"; cat /tmp/clawlite-doctor.out; exit 1; }
  ok "Tudo ok"

  echo
  echo -e "${C_GREEN}🎉 ClawLite instalado com sucesso!${C_RESET}"
  echo -e "${C_CYAN}👉 Próximo passo:${C_RESET} clawlite onboarding"
  echo
  echo -e "${C_DIM}Resumo:${C_RESET}"
  echo "- Ambiente: $(is_termux && echo Termux || echo Linux)"
  echo "- Venv: $VENV_DIR"
  echo "- Binário: $BIN_DIR/clawlite"
  echo "- PATH: configurado em ~/.bashrc|~/.zshrc e ~/.profile"
}

main "$@"
