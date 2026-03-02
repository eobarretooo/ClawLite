#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=""
if [[ -n "${BASH_SOURCE[0]-}" && -f "${BASH_SOURCE[0]}" ]]; then
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd 2>/dev/null || true)"
elif [[ -f "${0}" ]]; then
  ROOT_DIR="$(cd "$(dirname "${0}")/.." && pwd 2>/dev/null || true)"
fi
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/eobarretooo/ClawLite.git"

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python || true)"
fi

[[ -n "${PYTHON_BIN}" ]] || { echo "✗ python/python3 não encontrado"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "✗ git não encontrado"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "✗ curl não encontrado"; exit 1; }

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"${VENV_DIR}/bin/python" -m pip install --upgrade rich >/dev/null 2>&1 || true

TMP_PY="$(mktemp)"
cat > "${TMP_PY}" <<'PY'
from __future__ import annotations

import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path

VENV_DIR = Path(os.environ["VENV_DIR"])
ROOT_DIR = os.environ.get("ROOT_DIR", "")
REPO_URL = os.environ["REPO_URL"]
BIN_DIR = Path(os.environ["BIN_DIR"])

PYBIN = str(VENV_DIR / "bin" / "python")
PIP = [PYBIN, "-m", "pip"]

USE_RICH = False
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

    console = Console()
    USE_RICH = sys.stdout.isatty()
except Exception:
    console = None


def run(cmd: list[str], desc: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return
    output = (proc.stderr or proc.stdout or "").strip()
    cmd_txt = " ".join(cmd)
    if output:
        raise RuntimeError(f"{desc} falhou (cmd: {cmd_txt})\n{output}")
    raise RuntimeError(f"{desc} falhou (cmd: {cmd_txt})")


def ensure_path() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / "clawlite"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(VENV_DIR / "bin" / "clawlite")

    export_line = 'export PATH="$HOME/.local/bin:$PATH"'
    rc = Path.home() / (".zshrc" if "zsh" in os.environ.get("SHELL", "") else ".bashrc")
    rc.touch(exist_ok=True)
    if export_line not in rc.read_text(encoding="utf-8", errors="ignore"):
        with rc.open("a", encoding="utf-8") as fh:
            fh.write("\n" + export_line + "\n")

    profile = Path.home() / ".profile"
    profile.touch(exist_ok=True)
    if export_line not in profile.read_text(encoding="utf-8", errors="ignore"):
        with profile.open("a", encoding="utf-8") as fh:
            fh.write("\n" + export_line + "\n")


def install_local() -> None:
    req_file = Path(ROOT_DIR) / "requirements.txt"
    if req_file.exists():
        run(PIP + ["install", "--upgrade", "-r", str(req_file)], "pip requirements")
    run(
        PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", "-e", ROOT_DIR],
        "install local",
    )


def install_from_git() -> None:
    run(PIP + ["install", "--upgrade", "--force-reinstall", f"git+{REPO_URL}"], "install git")


def bootstrap_workspace() -> None:
    code = (
        "import secrets;"
        "from clawlite.config.loader import load_config,save_config;"
        "from clawlite.workspace.loader import WorkspaceLoader;"
        "cfg=load_config();"
        "WorkspaceLoader(workspace_path=cfg.workspace_path).bootstrap();"
        "tok=str(cfg.gateway.token or '').strip();"
        "cfg.gateway.token=tok or secrets.token_urlsafe(24);"
        "save_config(cfg)"
    )
    run([PYBIN, "-c", code], "bootstrap")


def doctor_check() -> None:
    run([str(VENV_DIR / "bin" / "clawlite"), "--help"], "clawlite help")


def ensure_gateway_runtime() -> None:
    code = """
import importlib
import sys

missing = []
for mod in ("fastapi", "uvicorn"):
    try:
        importlib.import_module(mod)
    except Exception as exc:
        missing.append(f"{mod}({exc.__class__.__name__})")

ws_ok = False
for mod in ("websockets", "wsproto"):
    try:
        importlib.import_module(mod)
        ws_ok = True
        break
    except Exception:
        pass

if not ws_ok:
    missing.append("websocket-stack(websockets|wsproto)")

if missing:
    print("missing:" + ",".join(missing))
    sys.exit(1)
"""
    run([PYBIN, "-c", code], "verify gateway runtime")


def install_playwright_runtime() -> None:
    try:
        run([PYBIN, "-m", "playwright", "install", "chromium"], "playwright chromium runtime")
    except Exception:
        pass


def rich_flow() -> None:
    console.print("[bold #ff6b2b]🦊 ClawLite Installer v0.5.0-beta.2[/bold #ff6b2b]")
    console.print("[bold #00f5ff]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold #00f5ff]")
    console.print(f"[cyan]Plataforma: Linux | Python: {platform.python_version()}[/cyan]")

    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[1/5] Detectando ambiente...", total=None)
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    with Progress(
        SpinnerColumn(style="#00f5ff"),
        TextColumn("[bold][2/5] Instalando dependências..."),
        BarColumn(complete_style="#ff6b2b", finished_style="#ff6b2b"),
        TaskProgressColumn(),
        transient=True,
        console=console,
    ) as pb:
        t = pb.add_task("deps", total=100)
        if ROOT_DIR and Path(ROOT_DIR, "pyproject.toml").exists():
            install_local()
        else:
            install_from_git()
        pb.advance(t, 100)
    console.print("[green]✓[/green]")

    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[3/5] Configurando CLI...", total=None)
        ensure_path()
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[4/5] Preparando workspace...", total=None)
        bootstrap_workspace()
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[5/5] Verificando instalação...", total=None)
        install_playwright_runtime()
        doctor_check()
        ensure_gateway_runtime()
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    console.print(Panel.fit("🦊 ClawLite v0.5.0-beta.2 instalado!\n👉 clawlite onboard", border_style="#ff6b2b"))


def simple_flow() -> None:
    print("🦊 ClawLite Installer v0.5.0-beta.2")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Plataforma: Linux | Python: {platform.python_version()}")

    print("[1/5] Detectando ambiente... ✓")
    print("[2/5] Instalando dependências...")
    if ROOT_DIR and Path(ROOT_DIR, "pyproject.toml").exists():
        install_local()
    else:
        install_from_git()
    print("✓")
    print("[3/5] Configurando CLI...")
    ensure_path()
    print("✓")
    print("[4/5] Preparando workspace...")
    bootstrap_workspace()
    print("✓")
    print("[5/5] Verificando instalação...")
    install_playwright_runtime()
    doctor_check()
    ensure_gateway_runtime()
    print("✓")
    print("🦊 ClawLite v0.5.0-beta.2 instalado!\n👉 clawlite onboard")


def main() -> None:
    if USE_RICH:
        rich_flow()
    else:
        simple_flow()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        msg = str(exc)
        if any(x in msg for x in ("verify gateway runtime", "fastapi", "uvicorn", "websockets", "wsproto")):
            msg = (
                "Gateway runtime nao esta pronto (fastapi/uvicorn/websockets). "
                "Execute: ~/.clawlite/venv/bin/python -m pip install --upgrade "
                "fastapi uvicorn websockets wsproto\n\n"
                f"Detalhes tecnicos: {exc}"
            )
        if USE_RICH:
            console.print(f"[red]✗[/red] {msg}")
        else:
            print(f"✗ {msg}")
        sys.exit(1)
PY

VENV_DIR="${VENV_DIR}" ROOT_DIR="${ROOT_DIR}" REPO_URL="${REPO_URL}" BIN_DIR="${BIN_DIR}" "${VENV_DIR}/bin/python" "${TMP_PY}"
rm -f "${TMP_PY}"
