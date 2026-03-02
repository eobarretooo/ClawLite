from __future__ import annotations

import asyncio

from clawlite.agent.loop import AgentRequest, get_agent_loop
from clawlite.core import agent as agent_mod


def test_get_agent_loop_is_singleton() -> None:
    first = get_agent_loop()
    second = get_agent_loop()
    assert first is second


def test_run_task_with_meta_delegates_to_agent_loop(monkeypatch) -> None:
    called: list[tuple[str, str]] = []

    def _fake_impl(prompt: str, skill: str = "", session_id: str = "", workspace_path: str | None = None):
        del workspace_path
        called.append((prompt, session_id))
        return "ok-meta", {"mode": "provider", "reason": "test", "model": "openai/gpt-4o-mini"}

    monkeypatch.setattr(agent_mod, "_run_task_with_meta_impl", _fake_impl)

    out, meta = agent_mod.run_task_with_meta("ping", session_id="tg_1")
    assert out == "ok-meta"
    assert meta["mode"] == "provider"
    assert called == [("ping", "tg_1")]


def test_run_task_with_learning_delegates_to_agent_loop(monkeypatch) -> None:
    called: list[tuple[str, str]] = []

    def _fake_impl(prompt: str, skill: str = "", session_id: str = "", workspace_path: str | None = None):
        del workspace_path, skill
        called.append((prompt, session_id))
        return "ok-learning"

    monkeypatch.setattr(agent_mod, "_run_task_with_learning_impl", _fake_impl)

    out = agent_mod.run_task_with_learning("hello", session_id="tg_2")
    assert out == "ok-learning"
    assert called == [("hello", "tg_2")]


def test_agent_loop_process_async(monkeypatch) -> None:
    loop = get_agent_loop()

    async def _run() -> str:
        return await loop.process(prompt="async ping", session_id="tg_3", learning=False)

    def _fake_meta(prompt: str, skill: str = "", session_id: str = "", workspace_path: str | None = None):
        del skill, workspace_path
        return f"echo:{prompt}:{session_id}", {"mode": "provider", "reason": "ok", "model": "openai/gpt-4o-mini"}

    monkeypatch.setattr(agent_mod, "_run_task_with_meta_impl", _fake_meta)
    out = asyncio.run(_run())
    assert out == "echo:async ping:tg_3"


def test_agent_loop_stream_request(monkeypatch) -> None:
    loop = get_agent_loop()

    def _fake_stream(prompt: str, skill: str = "", session_id: str = "", workspace_path: str | None = None):
        del skill, workspace_path

        def _iter():
            yield f"chunk:{prompt}:{session_id}"

        return _iter(), {"mode": "provider", "reason": "stream-ok", "model": "openai/gpt-4o-mini"}

    monkeypatch.setattr(agent_mod, "_run_task_stream_with_meta_impl", _fake_stream)
    stream, meta = loop.stream_request(AgentRequest(prompt="abc", session_id="s-stream", learning=False))
    assert "".join(list(stream)) == "chunk:abc:s-stream"
    assert meta["reason"] == "stream-ok"
