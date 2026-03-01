from __future__ import annotations

from pathlib import Path

from clawlite.onboarding import _save_identity_files
from clawlite.runtime.workspace import init_workspace


def test_save_identity_files_writes_rich_templates_with_placeholders_filled(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("clawlite.onboarding.init_workspace", lambda: str(workspace))

    cfg = {
        "assistant_name": "ClawLite Prime",
        "assistant_emoji": "🤖",
        "assistant_creature": "droid tático",
        "assistant_vibe": "direto e analítico",
        "assistant_backstory": "Nasceu para colaborar com decisões técnicas e execução prática.",
        "assistant_temperament": "Técnico e direto",
        "user_name": "Renan",
        "language": "pt-br",
        "user_timezone": "America/Sao_Paulo",
        "user_context": "Engenharia de software e automação operacional.",
    }

    _save_identity_files(cfg)

    identity = (workspace / "IDENTITY.md").read_text(encoding="utf-8")
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    user = (workspace / "USER.md").read_text(encoding="utf-8")
    agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    tools = (workspace / "TOOLS.md").read_text(encoding="utf-8")

    assert "Nome: ClawLite Prime" in identity
    assert "Emoji: 🤖" in identity
    assert "Creature: droid tático" in identity
    assert "Vibe: direto e analítico" in identity
    assert "Backstory" in identity
    assert "{{assistant_name}}" not in identity

    assert "## Valores Core" in soul
    assert "## Como Eu Me Comporto" in soul
    assert "## O Que Eu Evito" in soul
    assert "## Como Eu Lido Com Erros" in soul
    assert "## Tom Por Contexto" in soul
    assert "Telegram:" in soul
    assert "CLI:" in soul
    assert len(soul.splitlines()) >= 30

    assert "Nome do dono: Renan" in user
    assert "Timezone: America/Sao_Paulo" in user
    assert "Contexto profissional: Engenharia de software e automação operacional." in user

    assert "## Quando Age Sem Pedir Permissão" in agents
    assert "## Quando Consulta Antes de Agir" in agents
    assert "Cron:" in agents
    assert "Heartbeat:" in agents
    assert "Subagentes:" in agents

    assert "## Núcleo do Agente" in tools
    assert "## Limitações e Cuidados" in tools


def test_init_workspace_uses_sensible_defaults_without_onboarding(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_workspace(str(workspace))

    identity = (workspace / "IDENTITY.md").read_text(encoding="utf-8")
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    user = (workspace / "USER.md").read_text(encoding="utf-8")
    agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    tools = (workspace / "TOOLS.md").read_text(encoding="utf-8")

    assert "Nome: ClawLite Assistant" in identity
    assert "Emoji: 🦊" in identity
    assert "{{assistant_name}}" not in identity
    assert "{{user_name}}" not in user

    assert len(soul.splitlines()) >= 30
    assert "## Continuidade" in soul
    assert "## Preferências de Comunicação" in user
    assert "## Comportamento Autônomo" in agents
    assert "## Skills e Extensões" in tools
