#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=""
GATEWAY_URL=""
TOKEN=""
DOCKER_PREFLIGHT=0

usage() {
  cat <<'EOF'
Usage: bash scripts/release_preflight.sh [--config <path>] [--gateway-url <url>] [--token <token>] [--docker]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      CONFIG_PATH="$2"
      shift 2
      ;;
    --gateway-url)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      GATEWAY_URL="$2"
      shift 2
      ;;
    --token)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      TOKEN="$2"
      shift 2
      ;;
    --docker)
      DOCKER_PREFLIGHT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

echo "[1/3] pytest suite"
python -m pytest tests -q --tb=short

echo "[2/3] config validation"
if [ -n "$CONFIG_PATH" ]; then
  python -m clawlite.cli --config "$CONFIG_PATH" validate config
else
  python -m clawlite.cli validate config
fi

echo "[3/3] release preflight"
if [ -n "$CONFIG_PATH" ]; then
  set -- --config "$CONFIG_PATH" validate preflight
else
  set -- validate preflight
fi

if [ -n "$GATEWAY_URL" ]; then
  set -- "$@" --gateway-url "$GATEWAY_URL"
fi

if [ -n "$TOKEN" ]; then
  set -- "$@" --token "$TOKEN"
fi

if [ "$DOCKER_PREFLIGHT" -eq 1 ]; then
  set -- "$@" --docker
fi

python -m clawlite.cli "$@"

echo "[ok] release preflight completed"
