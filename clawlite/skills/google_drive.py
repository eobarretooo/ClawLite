from __future__ import annotations
import subprocess

SKILL_NAME = "google-drive"
SKILL_DESCRIPTION = "Gerenciar arquivos no Google Drive"

def run(command: str = "") -> str:
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    p = subprocess.run(command, shell=True, text=True, capture_output=True)
    if p.returncode != 0:
        return p.stderr.strip() or "erro"
    return p.stdout.strip()
