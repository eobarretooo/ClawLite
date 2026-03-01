---
name: Docker (Essentials + Advanced)
slug: docker
version: 1.0.3
homepage: https://clawic.com/skills/docker
description: Build, secure, and deploy Docker containers with image optimization, networking, and production-ready patterns.
changelog: Added essential commands reference and production patterns
metadata: {"clawdbot":{"emoji":"🐳","requires":{"bins":["docker"]},"os":["linux","darwin","win32"]}}
---

## Setup

On first use, read `setup.md` for user preference guidelines.

## When to Use

User needs Docker expertise. Agent handles containers, images, Compose, networking, volumes, and production deployment.

## Architecture

Memory in `~/docker/`. See `memory-template.md` for structure.

```
~/docker/
└── memory.md    # Preferences and context
```

## Quick Reference

| Topic | File |
|-------|------|
| Essential commands | `commands.md` |
| Dockerfile patterns | `images.md` |
| Compose orchestration | `compose.md` |
| Networking & volumes | `infrastructure.md` |
| Security hardening | `security.md` |
| Setup | `setup.md` |
| Memory | `memory-template.md` |

## Core Rules

### 1. Pin Image Versions
- `python:3.11.5-slim` not `python:latest`
- Today's latest differs from tomorrow's — breaks immutable builds

### 2. Combine RUN Commands
- `apt-get update && apt-get install -y pkg` in ONE layer
- Separate layers = stale package cache weeks later

### 3. Non-Root by Default
- Add `USER nonroot` in Dockerfile
- Running as root fails security scans and platform policies

### 4. Set Resource Limits
- `-m 512m` on every container
- OOM killer strikes without warning otherwise

### 5. Configure Log Rotation
- Default json-file driver has no size limit
- One chatty container fills disk and crashes host

## Image Traps

- Multi-stage builds: forgotten `--from=builder` copies from wrong stage silently
- COPY before RUN invalidates cache on every file change — copy requirements first, install, then copy code
- `ADD` extracts archives automatically — use `COPY` unless you need extraction
- Build args visible in image history — never use for secrets

## Runtime Traps

- `localhost` inside container is container's localhost — bind to `0.0.0.0`
- Port already in use: previous container still stopping — wait or force remove
- Exit code 137 = OOM killed, 139 = segfault — check with `docker inspect --format='{{.State.ExitCode}}'`
- No shell in distroless images — `docker cp` files out or use debug sidecar

## Networking Traps

- Container DNS only works on custom networks — default bridge can't resolve names
- Published ports bind to `0.0.0.0` — use `127.0.0.1:5432:5432` for local-only
- Zombie connections from killed containers — set health checks and restart policies

## Compose Traps

- `depends_on` waits for container start, not service ready — use `condition: service_healthy`
- `.env` file in wrong directory silently ignored — must be next to docker-compose.yml
- Volume mounts overwrite container files — empty host dir = empty container dir
- YAML anchors don't work across files — use multiple compose files instead

## Volume Traps

- Anonymous volumes accumulate silently — use named volumes
- Bind mounts have permission issues — container user must match host user
- `docker system prune` doesn't remove named volumes — add `--volumes` flag
- Stopped container data persists until container removed

## Resource Leaks

- Dangling images grow unbounded — `docker image prune` regularly
- Build cache grows forever — `docker builder prune` reclaims space
- Stopped containers consume disk — `docker container prune` or `--rm` on run
- Networks pile up from compose projects — `docker network prune`

## Secrets and Security

- ENV and COPY bake secrets into layer history permanently — use secrets mount or runtime env
- `--privileged` disables all security — almost never needed, find specific capability instead
- Images from unknown registries may be malicious — verify sources
- Build args visible in image history — don't use for secrets

## Debugging

- Exit code 137 = OOM killed, 139 = segfault — check `docker inspect --format='{{.State.ExitCode}}'`
- Container won't start: check logs even for failed containers — `docker logs <container>`
- No shell in distroless images — `docker cp` files out or use debug sidecar
- Inspect filesystem of dead container — `docker cp deadcontainer:/path ./local`

## Related Skills
Install with `clawhub install <slug>` if user confirms:
- `devops` — deployment pipelines
- `linux` — host system management
- `server` — server administration

## Feedback

- If useful: `clawhub star docker`
- Stay updated: `clawhub sync`
