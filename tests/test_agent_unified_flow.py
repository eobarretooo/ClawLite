from __future__ import annotations

import asyncio
import json
from pathlib import Path

from clawlite.channels.manager import ChannelManager
from clawlite.channels import manager as manager_mod
from clawlite.core import agent as agent_mod
from clawlite.runtime import multiagent
from clawlite.runtime.conversation_cron import list_cron_jobs
from clawlite.runtime.message_bus import InboundEnvelope


def _ok_meta() -> dict[str, str]:
    return {
        "mode": "provider",
        "reason": "test",
        "model": "openai/gpt-4o-mini",
    }


def test_run_task_with_meta_uses_workspace_identity(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "IDENTITY.md").write_text("Nome: Assistente Teste", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("Estilo: direto e pragmático", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Agir com autonomia segura.", encoding="utf-8")
    (tmp_path / "USER.md").write_text("Dono: Test User", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("# MEMORY", encoding="utf-8")
    (tmp_path / "memory").mkdir(exist_ok=True)

    captured_prompts: list[str] = []

    def _fake_model(prompt: str):
        captured_prompts.append(prompt)
        return "Sou o assistente do workspace.", _ok_meta()

    monkeypatch.setattr(agent_mod, "_run_model_with_meta", _fake_model)

    out, _meta = agent_mod.run_task_with_meta(
        "quem voce e?",
        session_id="tg_1850513297",
        workspace_path=str(tmp_path),
    )

    assert out == "Sou o assistente do workspace."
    assert captured_prompts
    merged_prompt = captured_prompts[0]
    assert "[IDENTITY]" in merged_prompt
    assert "Assistente Teste" in merged_prompt
    assert "[SOUL]" in merged_prompt
    assert "pragmático" in merged_prompt


def test_run_task_with_meta_executes_cron_tool(tmp_path: Path, monkeypatch) -> None:
    db_dir = tmp_path / ".clawlite"
    monkeypatch.setattr(multiagent, "DB_DIR", db_dir)
    monkeypatch.setattr(multiagent, "DB_PATH", db_dir / "multiagent.db")

    responses = [
        json.dumps(
            {
                "tool_call": {
                    "name": "skill.cron",
                    "arguments": {"command": "add 120 lembrar de revisar deploy"},
                }
            }
        ),
        "Lembrete criado com sucesso.",
    ]

    def _fake_model(_prompt: str):
        return responses.pop(0), _ok_meta()

    monkeypatch.setattr(agent_mod, "_run_model_with_meta", _fake_model)

    out, _meta = agent_mod.run_task_with_meta(
        "me lembra em 2 minutos",
        session_id="tg_1850513297",
        workspace_path=str(tmp_path),
    )

    jobs = list_cron_jobs(channel="telegram")
    assert out == "Lembrete criado com sucesso."
    assert jobs
    latest = max(jobs, key=lambda item: item.id)
    assert latest.interval_seconds == 120
    assert "revisar deploy" in latest.text


def test_channel_manager_inbound_passes_session_id(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def _fake_run_task_with_meta(prompt: str, skill: str = "", session_id: str = "", workspace_path: str | None = None):
        del workspace_path
        calls.append((prompt, skill, session_id))
        return "ok", _ok_meta()

    monkeypatch.setattr(manager_mod, "run_task_with_meta", _fake_run_task_with_meta)

    cm = ChannelManager()
    env = InboundEnvelope(channel="telegram", session_id="tg_12345", text="quem voce e?")
    out = asyncio.run(cm._process_inbound(env))

    assert out == "ok"
    assert calls
    assert calls[0][2] == "tg_12345"
