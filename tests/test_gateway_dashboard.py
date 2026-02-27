from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    server = importlib.import_module("clawlite.gateway.server")
    importlib.reload(server)
    return server


def test_dashboard_auth_and_settings(monkeypatch, tmp_path):
    server = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    token = server._token()
    r = client.post("/api/dashboard/auth", json={"token": token})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    headers = {"Authorization": f"Bearer {token}"}
    boot = client.get("/api/dashboard/bootstrap", headers=headers)
    assert boot.status_code == 200
    assert boot.json()["ok"] is True

    put = client.put(
        "/api/dashboard/settings",
        headers=headers,
        json={"model": "openai/gpt-4.1-mini", "hooks": {"pre": "A", "post": "B"}, "theme": "dark"},
    )
    assert put.status_code == 200
    assert put.json()["settings"]["model"] == "openai/gpt-4.1-mini"


def test_skills_and_telemetry_flow(monkeypatch, tmp_path):
    server = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    install = client.post("/api/dashboard/skills/install", headers=headers, json={"slug": "my-local-skill"})
    assert install.status_code == 200

    skills = client.get("/api/dashboard/skills", headers=headers).json()["skills"]
    assert any(s["slug"] == "my-local-skill" for s in skills)

    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        _ = ws.receive_json()  # welcome
        ws.send_json({"type": "chat", "session_id": "s1", "text": "oi"})
        msg = ws.receive_json()
        assert msg["type"] == "chat"

    telem = client.get("/api/dashboard/telemetry", headers=headers)
    assert telem.status_code == 200
    assert telem.json()["summary"]["events"] >= 1

    sessions = client.get("/api/dashboard/sessions?q=s1", headers=headers).json()["sessions"]
    assert any(s["session_id"] == "s1" for s in sessions)
