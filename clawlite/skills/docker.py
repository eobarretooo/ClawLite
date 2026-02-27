from __future__ import annotations
import shutil
import subprocess

SKILL_NAME = "docker"
SKILL_DESCRIPTION = 'Build, secure, and deploy Docker containers with image optimization, networking, and production-ready patterns.'

def run(command: str = "") -> str:
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    proc = subprocess.run(command, shell=True, text=True, capture_output=True)
    if proc.returncode != 0:
        return proc.stderr.strip() or "erro"
    return proc.stdout.strip()

def info() -> str:
    return '---\nname: Docker (Essentials + Advanced)\nslug: docker\nversion: 1.0.3\nhomepage: https://clawic.com/skills/docker\ndescription: Build, secure, and deploy Docker containers with image optimization, networking, and production-ready patterns.\nchangelog: Added essential commands reference and production patterns\nmetadata: {"clawdbot":{"emoji":"🐳","requires":{"bins":["docker"]},"os":["linux","darwin","win32"]}}\n---\n## Setup\nOn first use, read `setup.md` for user preference guidelines.\n## When to Use\nUser needs Docker expertise. Agent handles containers, images, Compose, networking, volumes, and production deployment.\n## Architecture\nMemory in `~/docker/`. See `memory-template.md` for structure.\n```\n~/docker/\n└── memory.md    # Preferences and context\n```\n## Quick Reference\n| Topic | File |\n|-------|------|\n| Essential commands | `commands.md` |\n| Dockerfile patterns | `images.md` |\n| Compose orchestration | `compose.md` |\n| Networking & volumes | `infrastructure.md` |\n| Security hardening | `security.md` |\n| Setup | `setup.md` |\n| Memory | `memory-template.md` |\n## Core Rules\n### 1. Pin Image Versions\n- `python:3.11.5-slim` not `python:latest`\n- Today\'s latest differs from tomorrow\'s — breaks immutable builds\n### 2. Combine RUN Commands\n- `apt-get update && apt-get install -y pkg` in ONE layer\n- Separate layers = stale package cache weeks later\n### 3. Non-Root by Default\n- Add `USER nonroot` in Dockerfile\n- Running as root fails security scans and platform policies\n### 4. Set Resourc'
