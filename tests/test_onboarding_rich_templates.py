from __future__ import annotations

from pathlib import Path

from clawlite.onboarding import _save_identity_files


def test_save_identity_files_writes_rich_templates(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("clawlite.onboarding.init_workspace", lambda: str(workspace))

    cfg = {
        "assistant_name": "ClawLite Prime",
        "assistant_temperament": "Técnico e direto",
        "user_name": "Renan",
        "language": "pt-br",
        "user_timezone": "America/Sao_Paulo",
    }

    _save_identity_files(cfg)

    identity = (workspace / "IDENTITY.md").read_text(encoding="utf-8")
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    user = (workspace / "USER.md").read_text(encoding="utf-8")
    agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    tools = (workspace / "TOOLS.md").read_text(encoding="utf-8")

    assert "Creature:" in identity
    assert "Vibe:" in identity
    assert "Avatar:" in identity
    assert "Backstory:" in identity

    assert "## Valores Core" in soul
    assert "## Como Eu Lido Com Erros" in soul
    assert "## Tom Por Contexto" in soul
    assert len(soul.splitlines()) >= 20

    assert "## Preferências" in user
    assert "## Contexto de Trabalho" in user
    assert "Timezone:" in user

    assert "## Comportamento Autônomo" in agents
    assert "## Quando Agir Sem Pedir" in agents

    assert "## Core Runtime" in tools
    assert "## Segurança Prática" in tools
    assert "Quando usar:" in tools
