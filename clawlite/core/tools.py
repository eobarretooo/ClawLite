from __future__ import annotations
import shlex
import subprocess
from pathlib import Path


def read_file(path: str) -> str:
    p = Path(path).expanduser()
    return p.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def exec_cmd(command: str, cwd: str | None = None) -> tuple[int, str, str]:
    args = shlex.split(command)
    try:
        proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as e:
        return 127, "", f"Comando não encontrado: {args[0] if args else command}"
