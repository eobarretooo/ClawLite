#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: find-sessions.sh (-S <socket> | --all)

List tmux sessions and print one "socket:session" row per line.

Options:
  -S <socket>   Inspect a single tmux socket path.
  --all         Scan every socket under CLAWLITE_TMUX_SOCKET_DIR.
  -h, --help    Show this help.
USAGE
}

socket_path=""
scan_all=false
socket_dir="${CLAWLITE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/clawlite-tmux-sockets}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -S)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      socket_path="$2"
      shift 2
      ;;
    --all)
      scan_all=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "$socket_path" && "$scan_all" == true ]]; then
  echo "Use -S or --all, not both." >&2
  usage >&2
  exit 2
fi

if [[ -z "$socket_path" && "$scan_all" == false ]]; then
  echo "One of -S or --all is required." >&2
  usage >&2
  exit 2
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH." >&2
  exit 1
fi

list_sessions() {
  local socket="$1"
  local sessions=""

  if [[ ! -S "$socket" ]]; then
    return 0
  fi

  if ! sessions="$(tmux -S "$socket" list-sessions -F '#{session_name}' 2>/dev/null)"; then
    return 0
  fi

  while IFS= read -r session; do
    [[ -n "$session" ]] || continue
    printf '%s:%s\n' "$socket" "$session"
  done <<< "$sessions"
}

if [[ -n "$socket_path" ]]; then
  list_sessions "$socket_path"
  exit 0
fi

if [[ ! -d "$socket_dir" ]]; then
  exit 0
fi

shopt -s nullglob
sockets=("$socket_dir"/*)
shopt -u nullglob

for socket in "${sockets[@]}"; do
  list_sessions "$socket"
done
