#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing dependency: $1"
  fi
}

is_truthy() {
  local raw="${1:-}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

require_cmd docker
if ! docker compose version >/dev/null 2>&1; then
  fail "Docker Compose v2 is required."
fi

export CLAWLITE_UID="${CLAWLITE_UID:-$(id -u)}"
export CLAWLITE_GID="${CLAWLITE_GID:-$(id -g)}"
clawlite_home_dir="${HOME}/.clawlite"
docker_wait_timeout="${CLAWLITE_DOCKER_WAIT_TIMEOUT:-120}"
mkdir -p "$clawlite_home_dir"

if [[ ! -w "$clawlite_home_dir" ]]; then
  fail "Config directory is not writable: $clawlite_home_dir"
fi

if is_truthy "${CLAWLITE_DOCKER_BROWSER:-}"; then
  export CLAWLITE_PIP_EXTRAS="${CLAWLITE_PIP_EXTRAS:-browser,telegram,media,observability,runtime}"
  export CLAWLITE_INSTALL_BROWSER=1
fi

wait_for_gateway_health() {
  local timeout="${1:-120}"
  local deadline=$((SECONDS + timeout))
  local status=""

  while (( SECONDS < deadline )); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' clawlite-gateway 2>/dev/null || true)"
    case "$status" in
      healthy)
        echo "==> Gateway container is healthy"
        return 0
        ;;
      running)
        echo "==> Gateway container is running"
        return 0
        ;;
      starting|created|restarting|"")
        sleep 2
        ;;
      unhealthy|exited|dead)
        break
        ;;
      *)
        sleep 2
        ;;
    esac
  done

  echo "==> Gateway failed to become healthy within ${timeout}s (last status: ${status:-unknown})"
  docker compose "${profile_args[@]}" ps clawlite-gateway || true
  docker compose "${profile_args[@]}" logs --tail 50 clawlite-gateway || true
  return 1
}

profile_args=()
up_services=("clawlite-gateway")
if is_truthy "${CLAWLITE_DOCKER_REDIS:-}" || [[ "${CLAWLITE_BUS_BACKEND:-}" == "redis" ]]; then
  export CLAWLITE_BUS_BACKEND="${CLAWLITE_BUS_BACKEND:-redis}"
  profile_args+=(--profile redis)
  up_services+=("redis")
fi

cd "$ROOT_DIR"

echo "==> Validating Docker Compose configuration"
docker compose "${profile_args[@]}" config >/dev/null

if ! is_truthy "${CLAWLITE_DOCKER_SKIP_BUILD:-}"; then
  echo "==> Building ClawLite image"
  docker compose "${profile_args[@]}" build clawlite-gateway
fi

if ! is_truthy "${CLAWLITE_DOCKER_SKIP_CONFIGURE:-}"; then
  if [[ -f "$clawlite_home_dir/config.json" || -f "$clawlite_home_dir/config.yaml" || -f "$clawlite_home_dir/config.yml" ]]; then
    echo "==> Existing ClawLite config found in $clawlite_home_dir"
  else
    echo "==> Running quickstart configure inside Docker"
    docker compose "${profile_args[@]}" run --rm clawlite-cli configure --flow quickstart
  fi
fi

if ! is_truthy "${CLAWLITE_DOCKER_SKIP_UP:-}"; then
  echo "==> Starting services"
  docker compose "${profile_args[@]}" up -d "${up_services[@]}"
  echo "==> Waiting for gateway health"
  wait_for_gateway_health "$docker_wait_timeout"
fi

echo
echo "ClawLite Docker setup complete."
echo "- Dashboard: http://127.0.0.1:8787"
echo "- CLI status: docker compose run --rm clawlite-cli status"
echo "- Config dir: $clawlite_home_dir"
if is_truthy "${CLAWLITE_DOCKER_REDIS:-}" || [[ "${CLAWLITE_BUS_BACKEND:-}" == "redis" ]]; then
  echo "- Redis profile: enabled"
fi
if is_truthy "${CLAWLITE_DOCKER_BROWSER:-}"; then
  echo "- Browser image: enabled"
fi
echo "- Health wait timeout: ${docker_wait_timeout}s"
