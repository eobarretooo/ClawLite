from __future__ import annotations

from pathlib import Path

TEMPLATES = {
    "AGENTS.md": "# AGENTS\n\nRegras operacionais do agente neste workspace.\n",
    "SOUL.md": "# SOUL\n\nTom e personalidade do assistente.\n",
    "USER.md": "# USER\n\nPreferências da pessoa usuária.\n",
    "IDENTITY.md": "# IDENTITY\n\nNome, assinatura e estilo do assistente.\n",
    "TOOLS.md": "# TOOLS\n\nNotas sobre ferramentas locais e integrações.\n",
    "MEMORY.md": "# MEMORY\n\nMemória de longo prazo do assistente.\n",
}


def init_workspace(path: str | None = None) -> str:
    root = Path(path).expanduser() if path else Path.home() / ".clawlite" / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    for name, content in TEMPLATES.items():
        p = root / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")
    (root / "memory").mkdir(exist_ok=True)
    return str(root)
