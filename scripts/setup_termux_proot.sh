#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# ClawLite setup recomendado para Termux: instala e roda dentro de proot Ubuntu.
# Uso:
#   bash scripts/setup_termux_proot.sh
# Variáveis opcionais:
#   DISTRO=ubuntu
#   CLAWLITE_REPO=https://github.com/eobarretooo/ClawLite.git
#   CLAWLITE_DIR=/root/ClawLite

DISTRO="${DISTRO:-ubuntu}"
CLAWLITE_REPO="${CLAWLITE_REPO:-https://github.com/eobarretooo/ClawLite.git}"
CLAWLITE_DIR="${CLAWLITE_DIR:-/root/ClawLite}"
PREFIX_BIN="${PREFIX:-/data/data/com.termux/files/usr}/bin"
ROOTFS_BASE="${PREFIX:-/data/data/com.termux/files/usr}/var/lib/proot-distro/installed-rootfs"

if ! command -v pkg >/dev/null 2>&1; then
  echo "Este script deve ser executado no Termux."
  exit 1
fi

echo "[1/6] Instalando dependências base do Termux..."
pkg update -y >/dev/null
pkg install -y proot-distro git curl >/dev/null

if ! proot-distro list | grep -q "^${DISTRO}\$"; then
  echo "[2/6] Instalando distro '${DISTRO}'..."
  proot-distro install "$DISTRO"
else
  echo "[2/6] Distro '${DISTRO}' já instalada."
fi

echo "[3/6] Preparando Ubuntu/proot..."
proot-distro login "$DISTRO" -- /bin/bash -lc "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl build-essential
"

echo "[4/6] Instalando/atualizando ClawLite no proot..."
proot-distro login "$DISTRO" -- /bin/bash -lc "
set -euo pipefail
if [ -d '${CLAWLITE_DIR}/.git' ]; then
  git -C '${CLAWLITE_DIR}' pull --rebase
else
  git clone '${CLAWLITE_REPO}' '${CLAWLITE_DIR}'
fi
cd '${CLAWLITE_DIR}'
bash scripts/install.sh
"

echo "[5/6] Instalando launcher 'clawlitex' no Termux..."
CACHE_DIR="${HOME}/.clawlite"
mkdir -p "$CACHE_DIR" "$PREFIX_BIN"

PROOT_REPO_PATH="${ROOTFS_BASE}/${DISTRO}${CLAWLITE_DIR}"
SRC_WRAPPER="${PROOT_REPO_PATH}/scripts/clawlitex.sh"
SRC_SETUP="${PROOT_REPO_PATH}/scripts/setup_termux_proot.sh"

if [ -f "$SRC_WRAPPER" ]; then
  install -m 0755 "$SRC_WRAPPER" "${PREFIX_BIN}/clawlitex"
  ln -sf "${PREFIX_BIN}/clawlitex" "${PREFIX_BIN}/clawlitex-setup"
  echo "  Launcher instalado em: ${PREFIX_BIN}/clawlitex"
else
  echo "  Aviso: wrapper clawlitex não encontrado em ${SRC_WRAPPER}"
fi

if [ -f "$SRC_SETUP" ]; then
  install -m 0755 "$SRC_SETUP" "${CACHE_DIR}/setup_termux_proot.sh"
fi

echo "[6/6] Finalizado."
echo
echo "Próximos comandos (no Termux):"
echo "  clawlitex status"
echo "  clawlitex onboarding"
echo "  clawlitex start"
echo
echo "Se necessário, fallback direto:"
echo "  proot-distro login ${DISTRO} -- /bin/bash -lc 'cd ${CLAWLITE_DIR} && clawlite onboarding'"
echo "  proot-distro login ${DISTRO} -- /bin/bash -lc 'cd ${CLAWLITE_DIR} && clawlite start --host 127.0.0.1 --port 8787'"
