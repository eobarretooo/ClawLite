#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-${REPO_URL:-https://github.com/eobarretooo/ClawLite.git}}"
INSTALL_DIR="${2:-${INSTALL_DIR:-/root/ClawLite}}"
BRANCH="${3:-main}"

backup_and_reclone() {
  local reason="$1"
  local backup_dir="${INSTALL_DIR}.backup.$(date +%Y%m%d%H%M%S)"
  echo "${reason}; preserving existing checkout at ${backup_dir}"
  mv "${INSTALL_DIR}" "${backup_dir}"
  git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
}

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  rm -rf "${INSTALL_DIR}"
  git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
  exit 0
fi

git -C "${INSTALL_DIR}" fetch --depth 1 origin "${BRANCH}"
git -C "${INSTALL_DIR}" checkout "${BRANCH}"

current_head="$(git -C "${INSTALL_DIR}" rev-parse HEAD)"
remote_head="$(git -C "${INSTALL_DIR}" rev-parse "origin/${BRANCH}")"

if [[ "${current_head}" == "${remote_head}" ]]; then
  echo "Repository already up to date."
  exit 0
fi

if [[ -n "$(git -C "${INSTALL_DIR}" status --porcelain)" ]]; then
  backup_and_reclone "Existing checkout has local changes"
  exit 0
fi

if git -C "${INSTALL_DIR}" merge-base --is-ancestor "${current_head}" "${remote_head}"; then
  git -C "${INSTALL_DIR}" merge --ff-only "origin/${BRANCH}"
  exit 0
fi

backup_and_reclone "Existing checkout diverged from origin/${BRANCH}"
