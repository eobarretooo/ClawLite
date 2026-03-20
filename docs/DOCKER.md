# Docker

Docker is now a first-class deployment path for ClawLite. This flow is intentionally closer to `ref/nanobot` today: one image, one compose file, one persisted home directory. The target for later phases is `ref/openclaw` depth: richer setup helpers, optional browser/runtime variants, and heavier container smoke coverage.

## Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2
- Enough disk for the image plus `~/.clawlite`

## Quick Start

Recommended:

```bash
bash scripts/docker_setup.sh
```

The helper validates Compose, builds the image, runs `configure --flow quickstart` if no local config exists yet, and starts the gateway. It also exports `CLAWLITE_UID` / `CLAWLITE_GID` from your host user so the container runs rootless without leaving root-owned files behind in `~/.clawlite`.

Optional helper toggles:

- `CLAWLITE_DOCKER_REDIS=1` — enable the Redis profile during setup
- `CLAWLITE_DOCKER_BROWSER=1` — build the browser-enabled image variant
- `CLAWLITE_DOCKER_SKIP_BUILD=1` — skip image build
- `CLAWLITE_DOCKER_SKIP_CONFIGURE=1` — skip `configure --flow quickstart`
- `CLAWLITE_DOCKER_SKIP_UP=1` — stop after build/config validation

Manual flow still works:

From the repository root:

```bash
docker compose build
docker compose run --rm clawlite-cli configure --flow quickstart
docker compose up -d clawlite-gateway
```

Open `http://127.0.0.1:8787`.

ClawLite keeps config and runtime state in a bind mount:

- Host: `~/.clawlite`
- Container: `/home/clawlite/.clawlite`

That means the normal config path still works inside the container:

```bash
docker compose run --rm clawlite-cli status
docker compose run --rm clawlite-cli run "summarize the latest session state"
docker compose run --rm clawlite-cli provider status
```

## Build Options

The image installs `telegram`, `media`, `observability`, and `runtime` extras by default. Override them with build args if you want a different surface:

```bash
CLAWLITE_PIP_EXTRAS=telegram,media,observability,runtime docker compose build
```

To bake Playwright + Chromium into the image:

```bash
CLAWLITE_PIP_EXTRAS=browser,telegram,media,observability \
CLAWLITE_INSTALL_BROWSER=1 \
docker compose build
```

The `runtime` extra installs the Redis Python client used by the optional Redis bus backend.

The image now runs as a rootless `clawlite` user. Override the build-time UID/GID when your host user is not `1000`:

```bash
CLAWLITE_UID="$(id -u)" \
CLAWLITE_GID="$(id -g)" \
docker compose build
```

## Local Providers from the Container

The compose file adds `host.docker.internal:host-gateway` so the container can reach providers running on the host machine.

Examples:

- Ollama on host: `http://host.docker.internal:11434/v1`
- vLLM on host: `http://host.docker.internal:8000/v1`

Use those URLs in ClawLite config instead of `127.0.0.1`, because inside the container `127.0.0.1` refers to the container itself.

## Optional Redis Bus

ClawLite's runtime can scale the internal bus through Redis. The compose file now includes an optional `redis` profile:

```bash
CLAWLITE_BUS_BACKEND=redis docker compose --profile redis up -d
```

Default env wiring in the compose file:

- `CLAWLITE_BUS_BACKEND=inprocess`
- `CLAWLITE_BUS_REDIS_URL=redis://redis:6379/0`
- `CLAWLITE_BUS_REDIS_PREFIX=clawlite:bus`

If you want Redis enabled all the time, set those env vars before running `docker compose up` or place them in your shell environment.

## Security Notes

- The gateway binds `0.0.0.0` inside the container so Docker port publishing works.
- The compose services drop `NET_ADMIN` and `NET_RAW` and enable `no-new-privileges`.
- If you expose port `8787` beyond local development, configure gateway auth before doing so.
- `clawlite-cli` shares the gateway network namespace, similar to the convenience pattern used by `ref/openclaw`. Treat that as the same trust boundary.

## CI Coverage

CI now validates:

- `docker compose config`
- default image build for `clawlite-gateway`
- browser-enabled image build with `browser` extras plus `CLAWLITE_INSTALL_BROWSER=1`
- a one-off runtime smoke that confirms the image contains Playwright plus a baked Chromium runtime under `PLAYWRIGHT_BROWSERS_PATH`

## Current Scope

What this Docker path covers now:

- local build + compose startup
- rootless runtime under `/home/clawlite`
- persisted config/state under `~/.clawlite`
- gateway healthcheck via `/health`
- optional CLI sidecar container
- host access to local Ollama/vLLM
- optional Redis bus profile with persisted Redis data
- browser-enabled image variant with CI build/runtime smoke coverage

What remains for later parity work:

- sandbox/browser-optimized runtime images
