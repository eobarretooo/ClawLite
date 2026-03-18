# Docker

Docker is now a first-class deployment path for ClawLite. This flow is intentionally closer to `ref/nanobot` today: one image, one compose file, one persisted home directory. The target for later phases is `ref/openclaw` depth: richer setup helpers, optional browser/runtime variants, and heavier container smoke coverage.

## Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2
- Enough disk for the image plus `~/.clawlite`

## Quick Start

From the repository root:

```bash
docker compose build
docker compose run --rm clawlite-cli configure --flow quickstart
docker compose up -d clawlite-gateway
```

Open `http://127.0.0.1:8787`.

ClawLite keeps config and runtime state in a bind mount:

- Host: `~/.clawlite`
- Container: `/root/.clawlite`

That means the normal config path still works inside the container:

```bash
docker compose run --rm clawlite-cli status
docker compose run --rm clawlite-cli run "summarize the latest session state"
docker compose run --rm clawlite-cli provider status
```

## Build Options

The image installs `telegram`, `media`, and `observability` extras by default. Override them with build args if you want a different surface:

```bash
CLAWLITE_PIP_EXTRAS=telegram,media,observability docker compose build
```

To bake Playwright + Chromium into the image:

```bash
CLAWLITE_PIP_EXTRAS=browser,telegram,media,observability \
CLAWLITE_INSTALL_BROWSER=1 \
docker compose build
```

## Local Providers from the Container

The compose file adds `host.docker.internal:host-gateway` so the container can reach providers running on the host machine.

Examples:

- Ollama on host: `http://host.docker.internal:11434/v1`
- vLLM on host: `http://host.docker.internal:8000/v1`

Use those URLs in ClawLite config instead of `127.0.0.1`, because inside the container `127.0.0.1` refers to the container itself.

## Security Notes

- The gateway binds `0.0.0.0` inside the container so Docker port publishing works.
- The compose services drop `NET_ADMIN` and `NET_RAW` and enable `no-new-privileges`.
- If you expose port `8787` beyond local development, configure gateway auth before doing so.
- `clawlite-cli` shares the gateway network namespace, similar to the convenience pattern used by `ref/openclaw`. Treat that as the same trust boundary.

## Current Scope

What this Docker path covers now:

- local build + compose startup
- persisted config/state under `~/.clawlite`
- gateway healthcheck via `/health`
- optional CLI sidecar container
- host access to local Ollama/vLLM

What remains for later parity work:

- setup helper script similar to `openclaw/docker-setup.sh`
- CI container build smoke
- rootless image variant
- sandbox/browser-optimized runtime images

