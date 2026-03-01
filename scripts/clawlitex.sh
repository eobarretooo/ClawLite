#!/usr/bin/env bash
set -euo pipefail

DISTRO="${CLAWLITEX_DISTRO:-ubuntu}"
CLAWLITE_DIR="${CLAWLITEX_DIR:-/root/ClawLite}"
SETUP_SCRIPT="${CLAWLITEX_SETUP_SCRIPT:-$HOME/.clawlite/setup_termux_proot.sh}"
DEFAULT_HOST="${CLAWLITEX_HOST:-127.0.0.1}"
DEFAULT_PORT="${CLAWLITEX_PORT:-8787}"
TERMUX_HOME="${CLAWLITEX_TERMUX_HOME:-$HOME}"
if [[ -d "/data/data/com.termux/files/home" ]]; then
  TERMUX_HOME="/data/data/com.termux/files/home"
fi
TERMUX_BOOT_DIR="${TERMUX_HOME}/.termux/boot"
TERMUX_BOOT_SCRIPT="${TERMUX_BOOT_DIR}/clawlite-supervisord.sh"
PROOT_SUPERVISOR_CONF="${CLAWLITEX_SUPERVISOR_CONF:-/root/.clawlite/supervisord.conf}"
PROOT_SUPERVISOR_START_SCRIPT="${CLAWLITEX_SUPERVISOR_START_SCRIPT:-/root/.clawlite/bin/clawlite-supervised-start.sh}"
PROOT_SUPERVISORCTL_CONF="${CLAWLITEX_SUPERVISORCTL_CONF:-/root/.clawlite/supervisorctl.conf}"
PROOT_SUPERVISOR_SERVER="${CLAWLITEX_SUPERVISOR_SERVER:-http://127.0.0.1:9001}"
ROOTFS_BASE="${PREFIX:-/data/data/com.termux/files/usr}/var/lib/proot-distro/installed-rootfs"

in_proot_runtime() {
  uname -a 2>/dev/null | grep -qi "PRoot-Distro"
}

print_help() {
  cat <<EOF
Uso: clawlitex <comando> [args...]

Comandos:
  setup       Instala/atualiza o proot Ubuntu + ClawLite
  status      Mostra status da instalacao
  start       Inicia gateway no proot (padrao: --host ${DEFAULT_HOST} --port ${DEFAULT_PORT})
  autostart   Configura supervisord 24/7 no proot + boot script no Termux
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
  CLAWLITEX_SUPERVISOR_CONF (padrao: /root/.clawlite/supervisord.conf)
  CLAWLITEX_SUPERVISORCTL_CONF (padrao: /root/.clawlite/supervisorctl.conf)
  CLAWLITEX_SUPERVISOR_SERVER (padrao: http://127.0.0.1:9001)
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
  if in_proot_runtime; then
    return 0
  fi

  if proot-distro list-installed >/dev/null 2>&1; then
    if proot-distro list-installed 2>/dev/null | awk '{print $1}' | grep -Fxq "$DISTRO"; then
      return 0
    fi
  fi

  if [[ -d "${ROOTFS_BASE}/${DISTRO}" ]]; then
    return 0
  fi

  if proot-distro login "$DISTRO" -- /bin/true >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

repo_exists_in_proot() {
  proot-distro login "$DISTRO" -- /bin/bash -lc "[ -d $(qdir) ]" >/dev/null 2>&1
}

clawlite_exists_in_proot() {
  proot-distro login "$DISTRO" -- /bin/bash -lc "command -v clawlite >/dev/null 2>&1" >/dev/null 2>&1
}

run_in_proot() {
  local remote_cmd="$1"
  if in_proot_runtime; then
    /bin/bash -lc "$remote_cmd"
    return
  fi
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

cmd_autostart_install() {
  ensure_ready_for_clawlite

  echo "[1/4] Configurando supervisor dentro do proot..."
  run_in_proot "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v supervisord >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y supervisor
fi
mkdir -p /root/.clawlite/bin /root/.clawlite/logs /root/.clawlite/run
cat > ${PROOT_SUPERVISOR_START_SCRIPT} <<'EOS'
#!/bin/bash
set -euo pipefail
cd ${CLAWLITE_DIR}
exec clawlite start --host ${DEFAULT_HOST} --port ${DEFAULT_PORT}
EOS
chmod +x ${PROOT_SUPERVISOR_START_SCRIPT}
cat > ${PROOT_SUPERVISOR_CONF} <<'EOS'
[inet_http_server]
port=127.0.0.1:9001

[supervisord]
logfile=/root/.clawlite/logs/supervisord.log
pidfile=/root/.clawlite/run/supervisord.pid
childlogdir=/root/.clawlite/logs
daemonize=true
minfds=1024
minprocs=200

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=http://127.0.0.1:9001

[program:clawlite]
command=${PROOT_SUPERVISOR_START_SCRIPT}
directory=${CLAWLITE_DIR}
autostart=true
autorestart=true
# backoff de bootstrap via startsecs/startretries
startsecs=5
startretries=20
exitcodes=0
stopsignal=TERM
stopwaitsecs=45
stopasgroup=true
killasgroup=true
stdout_logfile=/root/.clawlite/logs/clawlite.out.log
stderr_logfile=/root/.clawlite/logs/clawlite.err.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED=\"1\"
EOS
cat > ${PROOT_SUPERVISORCTL_CONF} <<'EOS'
[supervisorctl]
serverurl=http://127.0.0.1:9001
EOS
if [ -f /root/.clawlite/run/supervisord.pid ] && kill -0 \$(cat /root/.clawlite/run/supervisord.pid) 2>/dev/null; then
  supervisorctl -c ${PROOT_SUPERVISORCTL_CONF} reread >/dev/null 2>&1 || true
  supervisorctl -c ${PROOT_SUPERVISORCTL_CONF} update >/dev/null 2>&1 || true
  supervisorctl -c ${PROOT_SUPERVISORCTL_CONF} restart clawlite >/dev/null 2>&1 || true
else
  supervisord -c ${PROOT_SUPERVISOR_CONF}
fi
"

  echo "[2/4] Criando script de boot no Termux..."
  mkdir -p "${TERMUX_BOOT_DIR}"
  cat > "${TERMUX_BOOT_SCRIPT}" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
if ! command -v proot-distro >/dev/null 2>&1; then
  exit 0
fi
proot-distro login ${DISTRO} -- /bin/bash -lc '
set -euo pipefail
if [ ! -f ${PROOT_SUPERVISOR_CONF} ]; then
  exit 0
fi
if [ -f /root/.clawlite/run/supervisord.pid ] && kill -0 \$(cat /root/.clawlite/run/supervisord.pid) 2>/dev/null; then
  supervisorctl -s ${PROOT_SUPERVISOR_SERVER} start clawlite >/dev/null 2>&1 || true
else
  supervisord -c ${PROOT_SUPERVISOR_CONF}
fi
'
EOF
  chmod +x "${TERMUX_BOOT_SCRIPT}"

  echo "[3/4] Validando status do supervisor..."
  run_in_proot "
set -euo pipefail
timeout_s=45
elapsed=0
while [ \$elapsed -lt \$timeout_s ]; do
  line=\$(supervisorctl -s ${PROOT_SUPERVISOR_SERVER} status clawlite 2>/dev/null || true)
  if echo \"\$line\" | grep -Eq 'clawlite\\s+RUNNING'; then
    echo \"  \$line\"
    exit 0
  fi
  sleep 1
  elapsed=\$((elapsed + 1))
done
echo 'ERRO: clawlite nao entrou em RUNNING no supervisord.'
supervisorctl -s ${PROOT_SUPERVISOR_SERVER} status || true
tail -n 80 /root/.clawlite/logs/clawlite.err.log || true
exit 1
"

  echo "[4/4] Pronto."
  echo "Autostart configurado com supervisord."
  echo "Boot script: ${TERMUX_BOOT_SCRIPT}"
  echo
  echo "Importante:"
  echo "  1) Instale o app Termux:Boot no Android."
  echo "  2) Desative otimizações agressivas de bateria para o Termux."
  echo "  3) Reinicie o aparelho e rode: clawlitex autostart status"
}

cmd_autostart_status() {
  require_proot
  echo "Autostart (Termux):"
  if [[ -f "${TERMUX_BOOT_SCRIPT}" ]]; then
    echo "  boot script: OK (${TERMUX_BOOT_SCRIPT})"
  else
    echo "  boot script: FALTANDO (${TERMUX_BOOT_SCRIPT})"
  fi

  if ! distro_installed; then
    echo
    echo "proot (${DISTRO}): distro nao instalada"
    return
  fi

  echo
  echo "Autostart (proot ${DISTRO}):"
  run_in_proot "
set -euo pipefail
if command -v supervisord >/dev/null 2>&1; then
  echo '  supervisord bin: OK'
else
  echo '  supervisord bin: FALTANDO'
fi
if [ -f ${PROOT_SUPERVISOR_CONF} ]; then
  echo '  supervisor conf: OK (${PROOT_SUPERVISOR_CONF})'
else
  echo '  supervisor conf: FALTANDO (${PROOT_SUPERVISOR_CONF})'
fi
if [ -f /root/.clawlite/run/supervisord.pid ] && kill -0 \$(cat /root/.clawlite/run/supervisord.pid) 2>/dev/null; then
  echo '  supervisord pid: RUNNING'
else
  echo '  supervisord pid: STOPPED'
fi
if command -v supervisorctl >/dev/null 2>&1 && [ -f ${PROOT_SUPERVISOR_CONF} ]; then
  status_out=\$(supervisorctl -s ${PROOT_SUPERVISOR_SERVER} status 2>/dev/null || true)
  if echo \"\$status_out\" | grep -Eq 'no such file|refused connection'; then
    status_out=''
  fi
  if [ -n \"\$status_out\" ]; then
    echo \"\$status_out\"
  else
    if pgrep -f 'clawlite start --host' >/dev/null 2>&1; then
      echo '  clawlite program: RUNNING (fallback pid check)'
    else
      echo '  clawlite program: STOPPED (fallback pid check)'
    fi
  fi
fi
"
}

cmd_autostart_remove() {
  require_proot
if distro_installed; then
  run_in_proot "
set -euo pipefail
if command -v supervisorctl >/dev/null 2>&1 && [ -f ${PROOT_SUPERVISOR_CONF} ]; then
  supervisorctl -s ${PROOT_SUPERVISOR_SERVER} stop clawlite >/dev/null 2>&1 || true
  supervisorctl -s ${PROOT_SUPERVISOR_SERVER} shutdown >/dev/null 2>&1 || true
fi
"
  fi

  rm -f "${TERMUX_BOOT_SCRIPT}"
  echo "Autostart removido."
  echo "Boot script apagado: ${TERMUX_BOOT_SCRIPT}"
}

cmd_autostart() {
  local subcmd="${1:-status}"
  shift || true
  case "${subcmd}" in
    install|enable)
      cmd_autostart_install "$@"
      ;;
    status)
      cmd_autostart_status "$@"
      ;;
    remove|disable)
      cmd_autostart_remove "$@"
      ;;
    *)
      echo "Uso: clawlitex autostart <install|status|remove>"
      exit 1
      ;;
  esac
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
    autostart)
      cmd_autostart "$@"
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
