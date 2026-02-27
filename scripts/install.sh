#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd 2>/dev/null || true)"
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/eobarretooo/ClawLite.git"

command -v python3 >/dev/null 2>&1 || { echo "[ERRO] python3 não encontrado"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "[ERRO] git não encontrado"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "[ERRO] curl não encontrado"; exit 1; }

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"$VENV_DIR/bin/python" -m pip install --upgrade rich alive-progress halo >/dev/null 2>&1 || true

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
IS_TERMUX = ("com.termux" in os.environ.get("PREFIX", "")) and (subprocess.call(["bash", "-lc", "command -v pkg >/dev/null"]) == 0)

# UI fallback
IS_TTY = sys.stdout.isatty() and sys.stdin.isatty()
USE_RICH = USE_ALIVE = USE_HALO = False
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    console = Console()
    USE_RICH = IS_TTY
except Exception:
    console = None

try:
    from alive_progress import alive_bar
    USE_ALIVE = IS_TTY
except Exception:
    alive_bar = None

try:
    from halo import Halo
    USE_HALO = IS_TTY
except Exception:
    Halo = None


def print_line(msg: str):
    print(msg, flush=True)


def ok(msg: str):
    if USE_RICH:
        console.print(f"[green]✓[/green] {msg}")
    else:
        print_line(f"✓ {msg}")


def fail(msg: str):
    if USE_RICH:
        console.print(f"[red]✗[/red] {msg}")
    else:
        print_line(f"✗ {msg}")


def info(msg: str):
    if USE_RICH:
        console.print(f"[cyan]ℹ[/cyan] {msg}")
    else:
        print_line(f"ℹ {msg}")


def run(cmd: list[str], desc: str, shell: bool = False):
    if USE_HALO:
        spinner = Halo(text=desc, spinner="dots")
        spinner.start()
        p = subprocess.run(cmd if not shell else " ".join(cmd), shell=shell, capture_output=True, text=True)
        if p.returncode == 0:
            spinner.succeed(desc)
            return
        spinner.fail(desc)
        raise RuntimeError((p.stderr or p.stdout or "erro").strip())
    else:
        info(desc)
        p = subprocess.run(cmd if not shell else " ".join(cmd), shell=shell, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout or "erro").strip())


def ensure_path():
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / "clawlite"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(VENV_DIR / "bin" / "clawlite")

    export_line = 'export PATH="$HOME/.local/bin:$PATH"'
    shell = os.environ.get("SHELL", "")
    rc = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
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
    run([PYBIN, "-c", code], "Aplicando configuração inicial")


def main():
    if USE_RICH:
        console.print("[bold orange1]🦊 ClawLite Installer v0.4.1[/bold orange1]")
        console.print("[cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/cyan]")
        console.print(Panel.fit(f"Plataforma: {'Termux' if IS_TERMUX else 'Linux'}\nPython: {platform.python_version()}"))
    else:
        print_line("🦊 ClawLite Installer v0.4.1")
        print_line("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print_line(f"Plataforma: {'Termux' if IS_TERMUX else 'Linux'} | Python: {platform.python_version()}")

    # [1/5]
    info("[1/5] Detectando ambiente...")
    ok("Termux detectado" if IS_TERMUX else "Linux detectado")

    # [2/5]
    info("[2/5] Instalando dependências...")
    if USE_ALIVE:
        with alive_bar(100, title="dependências") as bar:
            done = 0
            bar(10); done += 10
            if IS_TERMUX:
                run(["pkg", "update", "-y"], "Atualizando pacotes do Termux")
                bar(35); done += 35
                run(["pkg", "install", "-y", "rust", "clang", "python", "git", "curl"], "Instalando rust/clang/python/git/curl")
                bar(25); done += 25
            run(PIP + ["install", "--upgrade", "rich", "questionary", "fastapi", "uvicorn", "alive-progress", "halo"], "Instalando libs Python essenciais")
            bar(20); done += 20
            if done < 100:
                bar(100 - done)
    else:
        if IS_TERMUX:
            run(["pkg", "update", "-y"], "Atualizando pacotes do Termux")
            run(["pkg", "install", "-y", "rust", "clang", "python", "git", "curl"], "Instalando rust/clang/python/git/curl")
        run(PIP + ["install", "--upgrade", "rich", "questionary", "fastapi", "uvicorn", "alive-progress", "halo"], "Instalando libs Python essenciais")
    ok("Dependências instaladas")

    # [3/5]
    info("[3/5] Instalando ClawLite...")
    if ROOT_DIR and Path(ROOT_DIR, "pyproject.toml").exists():
        run(PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", "-e", ROOT_DIR], "Instalando pacote local")
    else:
        run(PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", f"git+{REPO_URL}"], "Instalando pacote do GitHub")
    ok("v0.4.1")

    # [4/5]
    info("[4/5] Configurando workspace...")
    ensure_path()
    bootstrap_workspace()
    ok("Pronto")

    # [5/5]
    info("[5/5] Verificando instalação...")
    run([str(VENV_DIR / "bin" / "clawlite"), "doctor"], "Rodando doctor")
    ok("Tudo ok")

    if USE_RICH:
        console.print(Panel.fit("🦊 ClawLite v0.4.1 instalado!\n👉 clawlite onboarding", border_style="green"))
    else:
        print_line("🦊 ClawLite v0.4.1 instalado!\n👉 clawlite onboarding")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fail(str(e))
        sys.exit(1)
PY

VENV_DIR="$VENV_DIR" ROOT_DIR="$ROOT_DIR" REPO_URL="$REPO_URL" BIN_DIR="$BIN_DIR" "$VENV_DIR/bin/python" "$TMP_PY"
rm -f "$TMP_PY"
