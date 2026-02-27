from __future__ import annotations
import shutil
import subprocess

SKILL_NAME = "github"
SKILL_DESCRIPTION = "Gerenciar repositórios, issues, PRs e commits"

def run(command: str = "") -> str:

    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    proc = subprocess.run(command, shell=True, text=True, capture_output=True)
    if proc.returncode != 0:
        return proc.stderr.strip() or "erro"
    return proc.stdout.strip()
