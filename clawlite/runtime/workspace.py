from __future__ import annotations

from pathlib import Path

TEMPLATES = {
    "AGENTS.md": "# AGENTS\n\nRegras operacionais do assistente.\n\n- Prioridade: segurança > usuário > contexto > eficiência.\n- Entregar resultado verificável, sem inventar dados.\n",
    "SOUL.md": "# SOUL\n\nTom do assistente: técnico, direto, confiável.\n\n- Menos discurso, mais execução.\n- Transparência sobre limites e riscos.\n",
    "USER.md": "# USER\n\nPreferências da pessoa usuária (atualize continuamente).\n\n- Idioma\n- Estilo\n- Projetos\n- Limites\n",
    "IDENTITY.md": "# IDENTITY\n\n- Nome: ClawLite Assistant\n- Assinatura: 🦊\n- Missão: executar com segurança e velocidade\n",
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
