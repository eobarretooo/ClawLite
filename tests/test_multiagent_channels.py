from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from clawlite.gateway import server
from clawlite.runtime import multiagent


def _patch_db(tmpdir: str):
    old_dir = multiagent.DB_DIR
    old_path = multiagent.DB_PATH
    multiagent.DB_DIR = Path(tmpdir) / ".clawlite"
    multiagent.DB_PATH = multiagent.DB_DIR / "multiagent.db"
    return old_dir, old_path


def test_create_list_bind_and_routing():
    tmp = tempfile.TemporaryDirectory()
    old_dir, old_path = _patch_db(tmp.name)
    try:
        orch = multiagent.create_agent("orchestrator", channel="telegram", orchestrator=True)
        assert orch > 0
        dev = multiagent.create_agent("dev", channel="telegram", tags=["bug", "code"])
        assert dev > 0

        multiagent.bind_agent("dev", channel="slack", account="workspace-a")
        agents = multiagent.list_agents(channel="telegram")
        assert len(agents) == 2
        bindings = multiagent.list_agent_bindings()
        assert bindings[0]["name"] == "dev"

        by_mention = multiagent.select_agent_for_message(channel="telegram", text="oi @dev", mentions=["dev"])
        assert by_mention and by_mention.name == "dev"

        by_tag = multiagent.select_agent_for_message(channel="telegram", text="tem bug no deploy", mentions=[])
        assert by_tag and by_tag.name == "dev"

        fallback = multiagent.select_agent_for_message(channel="telegram", text="bom dia", mentions=[])
        assert fallback and fallback.name == "orchestrator"
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path
        tmp.cleanup()


def test_gateway_agents_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    client = TestClient(server.app)
    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/agents",
        headers=headers,
        json={"name": "docs", "channel": "telegram", "account": "docs-bot"},
    )
    assert created.status_code == 200
    assert created.json()["ok"] is True

    bound = client.post(
        "/api/agents/bind",
        headers=headers,
        json={"agent": "docs", "channel": "discord", "account": "guild-1"},
    )
    assert bound.status_code == 200

    listed = client.get("/api/agents", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["ok"] is True
    assert any(a["name"] == "docs" for a in payload["agents"])
