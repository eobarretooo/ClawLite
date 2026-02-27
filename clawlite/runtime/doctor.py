from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from clawlite.config.settings import load_config


def run_doctor() -> str:
    cfg = load_config()
    lines: list[str] = []
    lines.append("ClawLite Doctor")
    lines.append(f"python: {sys.version.split()[0]}")
    lines.append(f"platform: {platform.platform()}")
    lines.append(f"git: {'ok' if shutil.which('git') else 'missing'}")
    lines.append(f"curl: {'ok' if shutil.which('curl') else 'missing'}")

    gw = cfg.get("gateway", {})
    lines.append(f"gateway.port: {gw.get('port', 'n/a')}")
    lines.append(f"gateway.token: {'configured' if gw.get('token') else 'missing'}")

    auth = cfg.get("auth", {}).get("providers", {})
    lines.append(f"auth.providers.configured: {len([k for k,v in auth.items() if v.get('token')])}")

    ws = Path.home() / ".clawlite" / "workspace"
    lines.append(f"workspace: {'ok' if ws.exists() else 'missing'}")

    warnings: list[str] = []
    if not gw.get("token"):
        warnings.append("Gateway sem token configurado.")
    if not cfg.get("skills"):
        warnings.append("Nenhuma skill ativa no config.")
    if warnings:
        lines.append("warnings:")
        lines.extend([f"- {w}" for w in warnings])

    return "\n".join(lines)
