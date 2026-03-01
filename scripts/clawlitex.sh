#!/usr/bin/env bash
set -euo pipefail

DISTRO="${CLAWLITEX_DISTRO:-ubuntu}"
CLAWLITE_DIR="${CLAWLITEX_DIR:-/root/ClawLite}"
SETUP_SCRIPT="${CLAWLITEX_SETUP_SCRIPT:-$HOME/.clawlite/setup_termux_proot.sh}"
DEFAULT_HOST="${CLAWLITEX_HOST:-127.0.0.1}"
DEFAULT_PORT="${CLAWLITEX_PORT:-8787}"

print_help() {
  cat <<EOF
Uso: clawlitex <comando> [args...]

Comandos:
  setup       Instala/atualiza o proot Ubuntu + ClawLite
  status      Mostra status da instalacao
  start       Inicia gateway no proot (padrao: --host ${DEFAULT_HOST} --port ${DEFAULT_PORT})
  shell       Abre shell Ubuntu no diretorio do ClawLite
  help        Mostra esta ajuda

Qualquer outro comando e repassado para o ClawLite dentro do proot:
  clawlitex onboarding      -> clawlite onboarding
  clawlitex doctor          -> clawlite doctor
  clawlitex skills list     -> clawlite skills list
  clawlitex <qualquer>      -> clawlite <qualquer>

Variaveis opcionais:
  CLAWLITEX_DISTRO (padrao: ubuntu)
  CLAWLITEX_DIR (padrao: /root/ClawLite)
  CLAWLITEX_SETUP_SCRIPT (padrao: ~/.clawlite/setup_termux_proot.sh)
EOF
}

quote_join() {
  local out=""
  local arg
  for arg in "$@"; do
    out+=" $(printf '%q' "$arg")"
  done
  printf '%s' "$out"
}

qdir() {
  printf '%q' "$CLAWLITE_DIR"
}

qhost() {
  printf '%q' "$DEFAULT_HOST"
}

qport() {
  printf '%q' "$DEFAULT_PORT"
}

require_proot() {
  if ! command -v proot-distro >/dev/null 2>&1; then
    echo "proot-distro nao encontrado."
    echo "Execute: pkg install -y proot-distro"
    exit 1
  fi
}

distro_installed() {
  proot-distro list 2>/dev/null | awk '{print $1}' | grep -Fxq "$DISTRO"
}

repo_exists_in_proot() {
  proot-distro login "$DISTRO" -- /bin/bash -lc "[ -d $(qdir) ]" >/dev/null 2>&1
}

clawlite_exists_in_proot() {
  proot-distro login "$DISTRO" -- /bin/bash -lc "command -v clawlite >/dev/null 2>&1" >/dev/null 2>&1
}

run_in_proot() {
  local remote_cmd="$1"
  proot-distro login "$DISTRO" -- /bin/bash -lc "$remote_cmd"
}

ensure_ready_for_clawlite() {
  require_proot
  if ! distro_installed; then
    echo "Distro '$DISTRO' nao encontrada no proot."
    echo "Execute: clawlitex setup"
    exit 1
  fi
  if ! clawlite_exists_in_proot; then
    echo "clawlite nao encontrado dentro do proot '$DISTRO'."
    echo "Execute: clawlitex setup"
    exit 1
  fi
}

cmd_setup() {
  if [[ -f "$SETUP_SCRIPT" ]]; then
    DISTRO="$DISTRO" CLAWLITE_DIR="$CLAWLITE_DIR" bash "$SETUP_SCRIPT"
    return
  fi

  if [[ -f "./scripts/setup_termux_proot.sh" ]]; then
    DISTRO="$DISTRO" CLAWLITE_DIR="$CLAWLITE_DIR" bash "./scripts/setup_termux_proot.sh"
    return
  fi

  echo "Script de setup nao encontrado em:"
  echo "  - $SETUP_SCRIPT"
  echo "  - ./scripts/setup_termux_proot.sh"
  echo
  echo "Execute manualmente:"
  echo "  curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/setup_termux_proot.sh | bash"
  exit 1
}

cmd_status() {
  local ok_proot=0
  local ok_distro=0
  local ok_repo=0
  local ok_clawlite=0
  local ok_setup_script=0

  if command -v proot-distro >/dev/null 2>&1; then
    ok_proot=1
  fi

  if [[ "$ok_proot" -eq 1 ]] && distro_installed; then
    ok_distro=1
  fi

  if [[ "$ok_distro" -eq 1 ]] && repo_exists_in_proot; then
    ok_repo=1
  fi

  if [[ "$ok_distro" -eq 1 ]] && clawlite_exists_in_proot; then
    ok_clawlite=1
  fi

  if [[ -f "$SETUP_SCRIPT" ]]; then
    ok_setup_script=1
  fi

  echo "Status do clawlitex"
  echo
  echo "Termux:"
  echo "  proot-distro:    $([[ $ok_proot -eq 1 ]] && echo 'OK' || echo 'FALTANDO')"
  echo "  setup cacheado:  $([[ $ok_setup_script -eq 1 ]] && echo 'OK' || echo 'FALTANDO')"
  echo
  echo "proot (${DISTRO}):"
  echo "  distro:          $([[ $ok_distro -eq 1 ]] && echo 'OK' || echo 'FALTANDO')"
  echo "  repo dir:        $([[ $ok_repo -eq 1 ]] && echo "OK (${CLAWLITE_DIR})" || echo 'FALTANDO')"
  echo "  clawlite bin:    $([[ $ok_clawlite -eq 1 ]] && echo 'OK' || echo 'FALTANDO')"
  echo

  if [[ "$ok_proot" -eq 1 && "$ok_distro" -eq 1 && "$ok_clawlite" -eq 1 ]]; then
    echo "Pronto para uso."
    echo "  clawlitex onboarding"
    echo "  clawlitex start"
  else
    echo "Setup incompleto. Execute: clawlitex setup"
  fi
}

cmd_start() {
  ensure_ready_for_clawlite

  if [[ $# -eq 0 ]]; then
    run_in_proot "cd $(qdir) && clawlite start --host $(qhost) --port $(qport)"
    return
  fi

  local extra
  extra="$(quote_join "$@")"
  run_in_proot "cd $(qdir) && clawlite start${extra}"
}

cmd_shell() {
  require_proot
  if ! distro_installed; then
    echo "Distro '$DISTRO' nao encontrada. Execute: clawlitex setup"
    exit 1
  fi
  proot-distro login "$DISTRO" -- /bin/bash -lc "cd $(qdir) && exec /bin/bash"
}

cmd_passthrough() {
  ensure_ready_for_clawlite
  local extra
  extra="$(quote_join "$@")"
  run_in_proot "cd $(qdir) && clawlite${extra}"
}

main() {
  local cmd="help"
  if [[ $# -gt 0 ]]; then
    cmd="$1"
    shift
  fi

  case "$cmd" in
    setup|install)
      cmd_setup "$@"
      ;;
    status)
      cmd_status
      ;;
    start|run)
      cmd_start "$@"
      ;;
    shell|ubuntu)
      cmd_shell
      ;;
    help|--help|-h)
      print_help
      ;;
    *)
      cmd_passthrough "$cmd" "$@"
      ;;
  esac
}

main "$@"
