#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd 2>/dev/null || true)"
VENV_DIR="${HOME}/.clawlite/venv"
BIN_DIR="${HOME}/.local/bin"
REPO_URL="https://github.com/eobarretooo/ClawLite.git"

IS_TERMUX=0
if [[ "${PREFIX:-}" == *"com.termux"* ]] && command -v pkg >/dev/null 2>&1; then
  IS_TERMUX=1
fi

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python || true)"
fi

if [[ "$IS_TERMUX" == "1" ]]; then
  NEED_PKGS=()
  command -v git >/dev/null 2>&1 || NEED_PKGS+=("git")
  command -v curl >/dev/null 2>&1 || NEED_PKGS+=("curl")
  if [[ -z "$PYTHON_BIN" ]]; then
    NEED_PKGS+=("python")
  fi
  if [[ ${#NEED_PKGS[@]} -gt 0 ]]; then
    pkg update -y >/dev/null
    pkg install -y "${NEED_PKGS[@]}" >/dev/null
    PYTHON_BIN="$(command -v python3 || command -v python || true)"
  fi
fi

[[ -n "$PYTHON_BIN" ]] || { echo "✗ python/python3 não encontrado"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "✗ git não encontrado"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "✗ curl não encontrado"; exit 1; }

"$PYTHON_BIN" -m venv "$VENV_DIR"
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
        out = (p.stderr or p.stdout or "").strip()
        cmd_txt = " ".join(cmd)
        if out:
            raise RuntimeError(f"{desc} falhou (cmd: {cmd_txt})\n{out}")
        raise RuntimeError(f"{desc} falhou (cmd: {cmd_txt})")


def ensure_path():
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / "clawlite"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(VENV_DIR / "bin" / "clawlite")

    # Termux: também instala launcher em $PREFIX/bin para evitar chamar binário global quebrado
    if IS_TERMUX:
        prefix_bin = Path(os.environ.get("PREFIX", "")) / "bin"
        if str(prefix_bin) and prefix_bin.exists():
            launcher = prefix_bin / "clawlite"
            bash_path = prefix_bin / "bash"
            shebang = f"#!{bash_path}" if bash_path.exists() else "#!/usr/bin/env bash"
            launcher_content = (
                f"{shebang}\n"
                "export CLAWLITE_SIMPLE_UI=1\n"
                f"exec '{VENV_DIR / 'bin' / 'clawlite'}' \"$@\"\n"
            )
            if not launcher.exists() or launcher.read_text(encoding="utf-8", errors="ignore") != launcher_content:
                launcher.write_text(launcher_content, encoding="utf-8")
            launcher.chmod(0o755)

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
        "cfg.setdefault('gateway',{});"
        "tok=str(cfg['gateway'].get('token','')).strip();"
        "cfg['gateway']['token']=tok or secrets.token_urlsafe(24);"
        "save_config(cfg)"
    )
    run([PYBIN, "-c", code], "bootstrap")


def install_deps():
    base_requirements = [
        "fastapi>=0.112",
        "uvicorn[standard]>=0.30",
        "websockets>=12.0",
        "wsproto>=1.2",
        "questionary>=2.0.1",
        "rich>=13.7.1",
        "httpx>=0.27",
        "duckduckgo-search>=6.0.0",
        "beautifulsoup4>=4.12.0",
        "python-telegram-bot>=21.0",
        "discord.py>=2.3.0",
        "slack-bolt>=1.22.0",
        "textual>=0.73.0",
        "playwright>=1.46.0",
        "edge-tts>=6.1.12",
        "groq>=0.11.0",
    ]

    req_file = Path(ROOT_DIR) / "requirements.txt" if ROOT_DIR else None
    pip_target = ["install", "--upgrade"]
    if req_file and req_file.exists():
        pip_target += ["-r", str(req_file)]
    else:
        pip_target += base_requirements

    if IS_TERMUX:
        run(["pkg", "update", "-y"], "pkg update")
        run(["pkg", "install", "-y", "rust", "clang", "python", "git", "curl"], "pkg install deps")
        env = os.environ.copy()
        env["ANDROID_API_LEVEL"] = env.get("ANDROID_API_LEVEL", "24")
        run(PIP + pip_target, "pip requirements", env=env)
    else:
        run(PIP + pip_target, "pip requirements")


def install_package():
    if ROOT_DIR and Path(ROOT_DIR, "pyproject.toml").exists():
        run(PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", "-e", ROOT_DIR], "install local")
    else:
        run(PIP + ["install", "--upgrade", "--force-reinstall", "--no-deps", f"git+{REPO_URL}"], "install git")


def doctor_check():
    run([str(VENV_DIR / "bin" / "clawlite"), "doctor"], "doctor")


def verify_gateway_runtime():
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

print("ok")
"""
    run([PYBIN, "-c", code], "verify gateway runtime")


def repair_gateway_runtime():
    run(
        PIP
        + [
            "install",
            "--upgrade",
            "fastapi>=0.112",
            "uvicorn[standard]>=0.30",
            "websockets>=12.0",
            "wsproto>=1.2",
        ],
        "repair gateway runtime",
    )


def ensure_gateway_runtime():
    try:
        verify_gateway_runtime()
    except Exception:
        repair_gateway_runtime()
        verify_gateway_runtime()


def install_playwright_runtime():
    try:
        run([PYBIN, "-m", "playwright", "install", "chromium"], "playwright chromium runtime")
    except Exception:
        # Browser tools continuam operando em modo mock se o runtime nao puder ser instalado.
        pass


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
        install_deps()
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
        install_playwright_runtime()
        doctor_check()
        ensure_gateway_runtime()
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
    install_playwright_runtime()
    doctor_check()
    ensure_gateway_runtime()
    print("✓")
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
        msg = str(e)
        if (
            "verify gateway runtime" in msg
            or "repair gateway runtime" in msg
            or "fastapi" in msg
            or "uvicorn" in msg
            or "websockets" in msg
            or "wsproto" in msg
        ):
            msg = (
                "Gateway runtime nao esta pronto (fastapi/uvicorn/websockets). "
                "Execute: ~/.clawlite/venv/bin/python -m pip install --upgrade "
                "fastapi 'uvicorn[standard]' websockets wsproto\n\n"
                f"Detalhes tecnicos: {str(e)}"
            )
        if USE_RICH:
            console.print(f"[red]✗[/red] {msg}")
        else:
            print(f"✗ {msg}")
        sys.exit(1)
PY

VENV_DIR="$VENV_DIR" ROOT_DIR="$ROOT_DIR" REPO_URL="$REPO_URL" BIN_DIR="$BIN_DIR" "$VENV_DIR/bin/python" "$TMP_PY"
rm -f "$TMP_PY"
