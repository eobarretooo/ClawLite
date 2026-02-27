from __future__ import annotations

import platform
import shutil
import socket
import sqlite3
import sys
from pathlib import Path

from clawlite.config.settings import load_config


def _check_connectivity(host: str = "api.openai.com", port: int = 443, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_doctor() -> str:
    cfg = load_config()
    lines: list[str] = []
    warnings: list[str] = []

    lines.append("🩺 ClawLite Doctor")
    lines.append(f"python.version: {sys.version.split()[0]}")
    lines.append(f"platform: {platform.platform()}")
    lines.append(f"python.bin: {'ok' if shutil.which('python3') or shutil.which('python') else 'missing'}")
    lines.append(f"git: {'ok' if shutil.which('git') else 'missing'}")
    lines.append(f"curl: {'ok' if shutil.which('curl') else 'missing'}")

    try:
        sqlite3.connect(":memory:").close()
        sqlite_ok = "ok"
    except Exception:
        sqlite_ok = "missing"
    lines.append(f"sqlite: {sqlite_ok}")

    online = _check_connectivity()
    lines.append(f"connectivity.optional: {'ok' if online else 'offline/blocked'}")

    # dependências opcionais do gateway (podem faltar em Termux sem Rust)
    try:
        import fastapi  # type: ignore
        import uvicorn  # type: ignore

        gateway_deps = "ok"
    except Exception:
        gateway_deps = "optional-missing"
        warnings.append(
            "Dependências do gateway ausentes (fastapi/uvicorn). CLI funciona; para gateway rode: pkg install rust clang && ~/.clawlite/venv/bin/pip install fastapi uvicorn"
        )
    lines.append(f"gateway.deps: {gateway_deps}")

    model = cfg.get("model", "")
    if not model:
        warnings.append("Modelo padrão não definido.")

    gw = cfg.get("gateway", {})
    lines.append(f"gateway.port: {gw.get('port', 'n/a')}")
    lines.append(f"gateway.token: {'configured' if gw.get('token') else 'missing'}")
    if cfg.get("security", {}).get("require_gateway_token", True) and not gw.get("token"):
        warnings.append("Gateway sem token, mas segurança exige token.")

    channels = cfg.get("channels", {})
    enabled_channels = [k for k, v in channels.items() if isinstance(v, dict) and v.get("enabled")]
    lines.append(f"channels.enabled: {', '.join(enabled_channels) if enabled_channels else 'none'}")

    ws = Path.home() / ".clawlite" / "workspace"
    lines.append(f"workspace: {'ok' if ws.exists() else 'missing'}")

    if not cfg.get("skills"):
        warnings.append("Nenhuma skill ativa; o assistente pode ficar limitado.")

    if warnings:
        lines.append("warnings:")
        lines.extend([f"- {w}" for w in warnings])
    else:
        lines.append("warnings: none ✅")

    return "\n".join(lines)
