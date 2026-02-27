#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd 2>/dev/null || true)"
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/eobarretooo/ClawLite.git"

command -v python3 >/dev/null 2>&1 || { echo "✗ python3 não encontrado"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "✗ git não encontrado"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "✗ curl não encontrado"; exit 1; }

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"$VENV_DIR/bin/python" -m pip install --upgrade rich >/dev/null 2>&1 || true

TMP_PY="$(mktemp)"
cat > "$TMP_PY" <<'PY'
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
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")

USE_RICH = False
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    console = Console()
    USE_RICH = sys.stdout.isatty()
except Exception:
    console = None


def run(cmd: list[str], desc: str, env: dict | None = None):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or f"Falha em {desc}").strip())


def ensure_path():
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


def bootstrap_workspace():
    code = (
        "import secrets;"
        "from clawlite.config.settings import load_config,save_config;"
        "from clawlite.runtime.workspace import init_workspace;"
        "cfg=load_config();init_workspace();"
        "cfg.setdefault('gateway',{}).setdefault('token',secrets.token_urlsafe(24));"
        "save_config(cfg)"
    )
    run([PYBIN, "-c", code], "bootstrap")


def install_deps():
    if IS_TERMUX:
        run(["pkg", "update", "-y"], "pkg update")
        run(["pkg", "install", "-y", "rust", "clang", "python", "git", "curl"], "pkg install deps")
        env = os.environ.copy()
        env["ANDROID_API_LEVEL"] = env.get("ANDROID_API_LEVEL", "24")
        run(PIP + ["install", "--upgrade", "rich", "questionary"], "pip base", env=env)
        run(PIP + ["install", "--upgrade", "pydantic==1.10.21", "--only-binary=:all:"], "pip pydantic v1", env=env)
        run(PIP + ["install", "--upgrade", "fastapi==0.100.1", "uvicorn", "--only-binary=:all:"], "pip fastapi/uvicorn termux", env=env)
    else:
        run(PIP + ["install", "--upgrade", "rich", "questionary", "fastapi", "uvicorn"], "pip deps")


def install_package():
    if ROOT_DIR and Path(ROOT_DIR, "pyproject.toml").exists():
        run(PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", "-e", ROOT_DIR], "install local")
    else:
        run(PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", f"git+{REPO_URL}"], "install git")


def doctor_check():
    run([str(VENV_DIR / "bin" / "clawlite"), "doctor"], "doctor")


def rich_flow():
    console.print("[bold #ff6b2b]🦊 ClawLite Installer v0.4.1[/bold #ff6b2b]")
    console.print("[bold #00f5ff]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold #00f5ff]")
    console.print(f"[cyan]Plataforma: {'Termux' if IS_TERMUX else 'Linux'} | Python: {platform.python_version()}[/cyan]")

    # [1/5]
    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[1/5] Detectando ambiente...", total=None)
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    # [2/5] com barra
    with Progress(
        SpinnerColumn(style="#00f5ff"),
        TextColumn("[bold][2/5] Instalando dependências..."),
        BarColumn(complete_style="#ff6b2b", finished_style="#ff6b2b"),
        TaskProgressColumn(),
        transient=True,
        console=console,
    ) as pb:
        t = pb.add_task("deps", total=100)
        if IS_TERMUX:
            env = os.environ.copy()
            env["ANDROID_API_LEVEL"] = env.get("ANDROID_API_LEVEL", "24")
            run(["pkg", "update", "-y"], "pkg update")
            pb.advance(t, 25)
            run(["pkg", "install", "-y", "rust", "clang", "python", "git", "curl"], "pkg install")
            pb.advance(t, 25)
            run(PIP + ["install", "--upgrade", "rich", "questionary"], "pip base", env=env)
            pb.advance(t, 15)
            run(PIP + ["install", "--upgrade", "pydantic==1.10.21", "--only-binary=:all:"], "pip pydantic v1", env=env)
            pb.advance(t, 15)
            run(PIP + ["install", "--upgrade", "fastapi==0.100.1", "uvicorn", "--only-binary=:all:"], "pip fastapi/uvicorn termux", env=env)
            pb.advance(t, 20)
        else:
            run(PIP + ["install", "--upgrade", "rich", "questionary", "fastapi", "uvicorn"], "pip deps")
            pb.advance(t, 100)
    console.print("[green]✓[/green]")

    # [3/5]
    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[3/5] Instalando ClawLite...", total=None)
        install_package()
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    # [4/5]
    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[4/5] Configurando workspace...", total=None)
        ensure_path()
        bootstrap_workspace()
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    # [5/5]
    with Progress(SpinnerColumn(style="#00f5ff"), TextColumn("[bold]{task.description}"), transient=True, console=console) as sp:
        t = sp.add_task("[5/5] Verificando instalação...", total=None)
        doctor_check()
        sp.update(t, completed=1)
    console.print("[green]✓[/green]")

    console.print(Panel.fit("🦊 ClawLite v0.4.1 instalado!\n👉 clawlite onboarding", border_style="#ff6b2b"))


def simple_flow():
    print("🦊 ClawLite Installer v0.4.1")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Plataforma: {'Termux' if IS_TERMUX else 'Linux'} | Python: {platform.python_version()}")

    print("[1/5] Detectando ambiente... ✓")
    print("[2/5] Instalando dependências...")
    install_deps()
    print("✓")
    print("[3/5] Instalando ClawLite...")
    install_package(); print("✓")
    print("[4/5] Configurando workspace...")
    ensure_path(); bootstrap_workspace(); print("✓")
    print("[5/5] Verificando instalação...")
    doctor_check(); print("✓")
    print("🦊 ClawLite v0.4.1 instalado!\n👉 clawlite onboarding")


def main():
    if USE_RICH:
        # etapa 2 precisa vir na ordem visual definida, então fazemos detect antes e deps já no fluxo rich
        rich_flow()
    else:
        simple_flow()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if USE_RICH:
            console.print(f"[red]✗[/red] {e}")
        else:
            print(f"✗ {e}")
        sys.exit(1)
PY

VENV_DIR="$VENV_DIR" ROOT_DIR="$ROOT_DIR" REPO_URL="$REPO_URL" BIN_DIR="$BIN_DIR" "$VENV_DIR/bin/python" "$TMP_PY"
rm -f "$TMP_PY"
