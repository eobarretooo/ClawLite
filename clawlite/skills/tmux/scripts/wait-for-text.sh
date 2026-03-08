#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: wait-for-text.sh -t <target> (-p <pattern> | -F <text>) [options]

Poll a tmux pane until a pattern appears in the recent pane history.

Options:
  -t <target>   tmux target pane (session:window.pane), required.
  -p <pattern>  Regex pattern to search for.
  -F <text>     Fixed string to search for.
  -T <seconds>  Timeout in seconds. Default: 15.
  -i <seconds>  Poll interval in seconds. Default: 0.5.
  -l <lines>    Number of recent lines to inspect. Default: 200.
  -S <socket>   tmux socket path.
  -h, --help    Show this help.

Exit codes:
  0  pattern found
  1  timeout
  2  invalid usage
USAGE
}

target=""
pattern=""
fixed_text=""
timeout_s=15
interval_s=0.5
history_lines=200
socket_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    -p)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      pattern="$2"
      shift 2
      ;;
    -F)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      fixed_text="$2"
      shift 2
      ;;
    -T)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      timeout_s="$2"
      shift 2
      ;;
    -i)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      interval_s="$2"
      shift 2
      ;;
    -l)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      history_lines="$2"
      shift 2
      ;;
    -S)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      socket_path="$2"
      shift 2
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

if [[ -z "$target" ]]; then
  echo "Target pane is required." >&2
  usage >&2
  exit 2
fi

if [[ -n "$pattern" && -n "$fixed_text" ]]; then
  echo "Use -p or -F, not both." >&2
  usage >&2
  exit 2
fi

if [[ -z "$pattern" && -z "$fixed_text" ]]; then
  echo "One of -p or -F is required." >&2
  usage >&2
  exit 2
fi

if ! [[ "$timeout_s" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "Timeout must be an integer number of seconds." >&2
  exit 2
fi

if ! [[ "$history_lines" =~ ^[0-9]+$ ]]; then
  echo "History line count must be an integer." >&2
  exit 2
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found in PATH." >&2
  exit 1
fi

tmux_cmd=(tmux)
if [[ -n "$socket_path" ]]; then
  tmux_cmd+=(-S "$socket_path")
fi

start_epoch="$(date +%s)"
timeout_ceiling="${timeout_s%.*}"
[[ -n "$timeout_ceiling" ]] || timeout_ceiling=0
deadline=$((start_epoch + timeout_ceiling))

while true; do
  pane_text="$("${tmux_cmd[@]}" capture-pane -p -J -t "$target" -S "-${history_lines}" 2>/dev/null || true)"

  if [[ -n "$fixed_text" ]]; then
    if printf '%s\n' "$pane_text" | grep -F -- "$fixed_text" >/dev/null 2>&1; then
      exit 0
    fi
  else
    if printf '%s\n' "$pane_text" | grep -E -- "$pattern" >/dev/null 2>&1; then
      exit 0
    fi
  fi

  now_epoch="$(date +%s)"
  if (( now_epoch >= deadline )); then
    exit 1
  fi

  sleep "$interval_s"
done
