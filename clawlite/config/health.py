from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from clawlite.config.schema import AppConfig


def config_health(config: AppConfig) -> dict[str, Any]:
    """Validate critical runtime fields.

    Returns ``{"ok": bool, "issues": list[str]}``. Fast enough for a
    health endpoint (no I/O beyond a quick socket test).
    """
    issues: list[str] = []

    # Provider key present
    provider_key = str(config.provider.litellm_api_key or "").strip()
    model = str(config.provider.model or "").strip()
    if not provider_key and not _is_local_model(model):
        issues.append("provider.litellm_api_key is empty and model is not a known local provider")

    # Memory path writable
    workspace = str(config.workspace_path or "").strip()
    if workspace:
        ws_path = Path(workspace)
        if ws_path.exists() and not _is_writable(ws_path):
            issues.append(f"workspace_path '{workspace}' is not writable")
    else:
        issues.append("workspace_path is empty")

    # Gateway port available (quick check — don't bind, just probe)
    port = int(config.gateway.port or 0)
    if port and not _port_available(port):
        issues.append(f"gateway.port {port} appears to be in use")

    return {"ok": len(issues) == 0, "issues": issues}


def _is_local_model(model: str) -> bool:
    local_prefixes = ("ollama/", "ollama_chat/", "lm_studio/", "llamacpp/", "local/")
    return any(model.startswith(p) for p in local_prefixes)


def _is_writable(path: Path) -> bool:
    try:
        test = path / ".clawlite_write_check"
        test.touch()
        test.unlink()
        return True
    except OSError:
        return False


def _port_available(port: int) -> bool:
    """Return True if the port is not yet bound (i.e. available for us to use).

    Intentionally does NOT set SO_REUSEADDR so that an already-bound port
    reliably returns False on all platforms.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
