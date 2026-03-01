from __future__ import annotations

from pathlib import Path

from clawlite.runtime.session_memory import ensure_memory_layout
from clawlite.skills.discovery import build_skills_summary


def _read(path: Path, max_chars: int = 2500) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars].strip()


def build_system_prompt(workspace_path: str | None = None) -> str:
    """System prompt base por sessão, inspirado em boas práticas de robustez.

    Estrutura:
    - identidade e missão
    - regras operacionais
    - estilo de resposta
    - contexto do usuário
    """
    root = Path(ensure_memory_layout(workspace_path))

    identity = _read(root / "IDENTITY.md", 1800)
    soul = _read(root / "SOUL.md", 2200)
    agents = _read(root / "AGENTS.md", 2400)
    user = _read(root / "USER.md", 1800)

    blocks = [
        "[SYSTEM ROLE] Você é o ClawLite Assistant, um agente operacional para execução técnica com segurança.",
        "[MISSION] Entregar resultados verificáveis, com objetividade e sem inventar fatos.",
        "[RULES] Priorize: segurança > instrução do usuário > contexto de sessão > eficiência.",
        "[STYLE] Respostas diretas, úteis, com próximos passos claros. Evite fluff.",
    ]

    if identity:
        blocks.append("[IDENTITY]\n" + identity)
    if soul:
        blocks.append("[SOUL]\n" + soul)
    if agents:
        blocks.append("[AGENTS]\n" + agents)
    if user:
        blocks.append("[USER]\n" + user)

    skills_summary = build_skills_summary(root)
    if skills_summary:
        blocks.append("[SKILLS]\n" + skills_summary[:2600])

    return "\n\n".join(blocks).strip()
