#!/usr/bin/env bash
set -euo pipefail

DISTRO_NAME="${DISTRO_NAME:-ubuntu}"
REPO_URL="${REPO_URL:-https://github.com/eobarretooo/ClawLite.git}"
INSTALL_DIR="${INSTALL_DIR:-/root/ClawLite}"
SYNC_HELPER_URL="${SYNC_HELPER_URL:-https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/update_checkout.sh}"

if [[ -z "${TERMUX_VERSION:-}" && "${PREFIX:-}" != *"/data/data/com.termux/"* ]]; then
  echo "✗ This wrapper is meant to run from Termux on Android."
  echo "  If you are already inside Ubuntu/Linux, use scripts/install.sh instead."
  exit 1
fi

command -v pkg >/dev/null 2>&1 || {
  echo "✗ pkg not found. Open this from a Termux shell."
  exit 1
}

echo "[1/5] Installing Termux-side prerequisites..."
pkg update -y
pkg install -y proot-distro git curl

echo "[2/5] Ensuring ${DISTRO_NAME} rootfs exists..."
if ! proot-distro login "${DISTRO_NAME}" -- true >/dev/null 2>&1; then
  proot-distro install "${DISTRO_NAME}"
fi

echo "[3/5] Preparing Ubuntu packages..."
proot-distro login "${DISTRO_NAME}" --shared-tmp -- env REPO_URL="${REPO_URL}" INSTALL_DIR="${INSTALL_DIR}" /bin/bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  ca-certificates \
  build-essential \
  curl \
  git \
  python3 \
  python3-pip \
  python3-venv

echo "[4/5] Syncing ClawLite repository..."
bash <(curl -fsSL "${SYNC_HELPER_URL}") "${REPO_URL}" "${INSTALL_DIR}" main

echo "[5/5] Running ClawLite installer inside Ubuntu..."
bash "${INSTALL_DIR}/scripts/install.sh"
'

cat <<EOF

ClawLite was installed inside ${DISTRO_NAME} via proot-distro.

Next steps:
  1. Enter Ubuntu:
     proot-distro login ${DISTRO_NAME} --shared-tmp

  2. Run the wizard:
     clawlite configure --flow quickstart

  3. Start the gateway:
     clawlite gateway

If you prefer to keep using the checked-out repo, it lives at:
  ${INSTALL_DIR}
EOF
