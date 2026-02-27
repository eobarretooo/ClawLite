from __future__ import annotations
from clawlite.core.tools import exec_cmd


def run_task(prompt: str) -> str:
    # MVP: fallback local behavior
    if prompt.lower().startswith("resuma o diretório"):
        code, out, err = exec_cmd("ls -la")
        if code == 0:
            return f"Diretório atual:\n{out[:3000]}"
        return f"Falha ao listar diretório: {err}"
    return f"[MVP] Recebi: {prompt}"
