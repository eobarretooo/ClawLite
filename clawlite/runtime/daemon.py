from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class DaemonError(RuntimeError):
    """Falha operacional no gerenciamento de daemon."""


def _default_unit_path(service_name: str) -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{service_name}.service"


def render_systemd_unit(
    *,
    service_name: str,
    host: str,
    port: int,
    python_bin: str | None = None,
    workdir: str | None = None,
) -> str:
    py = python_bin or sys.executable
    wd = workdir or str(Path.cwd())
    exec_cmd = f"{shlex.quote(py)} -m clawlite.cli start --host {shlex.quote(host)} --port {int(port)}"
    return (
        "[Unit]\n"
        f"Description=ClawLite Gateway ({service_name})\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={wd}\n"
        f"ExecStart={exec_cmd}\n"
        "Restart=on-failure\n"
        "RestartSec=4\n"
        "Environment=PYTHONUNBUFFERED=1\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _require_systemctl() -> str:
    systemctl_bin = shutil.which("systemctl")
    if not systemctl_bin:
        raise DaemonError(
            "systemctl não encontrado. Este comando requer systemd user services."
        )
    return systemctl_bin


def install_systemd_user_service(
    *,
    host: str,
    port: int,
    service_name: str = "clawlite",
    enable_now: bool = True,
    start_now: bool = True,
) -> dict[str, Any]:
    if os.name == "nt":
        raise DaemonError("install-daemon não é suportado no Windows sem WSL/systemd.")
    _require_systemctl()

    unit_path = _default_unit_path(service_name)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_systemd_unit(
        service_name=service_name,
        host=host,
        port=port,
    )
    unit_path.write_text(content, encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True, text=True)
    if enable_now:
        subprocess.run(["systemctl", "--user", "enable", f"{service_name}.service"], check=False, capture_output=True, text=True)
    if start_now:
        subprocess.run(["systemctl", "--user", "restart", f"{service_name}.service"], check=False, capture_output=True, text=True)

    return {
        "ok": True,
        "service_name": service_name,
        "unit_path": str(unit_path),
        "enabled": bool(enable_now),
        "started": bool(start_now),
    }


def daemon_status(*, service_name: str = "clawlite") -> dict[str, Any]:
    _require_systemctl()

    def _run(*args: str) -> tuple[int, str]:
        proc = subprocess.run(
            ["systemctl", "--user", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, output

    enabled_code, enabled_out = _run("is-enabled", f"{service_name}.service")
    active_code, active_out = _run("is-active", f"{service_name}.service")
    return {
        "service_name": service_name,
        "enabled": enabled_code == 0,
        "enabled_state": enabled_out or ("enabled" if enabled_code == 0 else "disabled"),
        "active": active_code == 0,
        "active_state": active_out or ("active" if active_code == 0 else "inactive"),
        "unit_path": str(_default_unit_path(service_name)),
    }
