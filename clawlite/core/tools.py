from __future__ import annotations
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
    proc = subprocess.run(command, shell=True, cwd=cwd, text=True, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr
