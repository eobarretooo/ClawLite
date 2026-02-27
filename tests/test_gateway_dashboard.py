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
    monkeypatch.setattr(
        server,
        "run_task_with_meta",
        lambda prompt: (
            f"[pipeline] {prompt}",
            {"mode": "online", "reason": "provider-ok", "model": "openai/gpt-4o-mini"},
        ),
    )
    client = TestClient(server.app)

    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    install = client.post("/api/dashboard/skills/install", headers=headers, json={"slug": "my-local-skill"})
    assert install.status_code == 200
    assert "created" in install.json()

    skills = client.get("/api/dashboard/skills", headers=headers).json()["skills"]
    assert any(s["slug"] == "my-local-skill" for s in skills)

    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        _ = ws.receive_json()  # welcome
        ws.send_json({"type": "chat", "session_id": "s1", "text": "oi"})
        msg = ws.receive_json()
        assert msg["type"] == "chat"
        assert msg["meta"]["model"] == "openai/gpt-4o-mini"
        assert "[pipeline]" in msg["message"]["text"]

        ws.send_json({"type": "chat", "session_id": "s1", "text": "segunda"})
        _ = ws.receive_json()
        ws.send_json({"type": "chat", "session_id": "s2", "text": "terceira"})
        _ = ws.receive_json()

    telem = client.get("/api/dashboard/telemetry", headers=headers)
    assert telem.status_code == 200
    assert telem.json()["summary"]["events"] == 3
    assert telem.json()["summary"]["sessions"] == 2

    telem_s1 = client.get("/api/dashboard/telemetry?session_id=s1&period=all", headers=headers).json()
    assert telem_s1["summary"]["events"] == 2
    assert telem_s1["summary"]["sessions"] == 1
    assert telem_s1["sessions"][0]["session_id"] == "s1"

    telem_hour = client.get("/api/dashboard/telemetry?period=24h&granularity=hour", headers=headers).json()
    assert telem_hour["filters"]["granularity"] == "hour"
    assert len(telem_hour["timeline"]) >= 1

    sessions = client.get("/api/dashboard/sessions?q=s1", headers=headers).json()["sessions"]
    assert any(s["session_id"] == "s1" for s in sessions)


def test_logs_filtering_and_ws_snapshot(monkeypatch, tmp_path):
    server = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)
    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    server._log("skills.enabled", level="info", data={"slug": "abc"})
    server._log("chat.message", level="error", data={"session_id": "sx"})

    only_error = client.get("/api/dashboard/logs?level=error", headers=headers)
    assert only_error.status_code == 200
    logs = only_error.json()["logs"]
    assert logs
    assert all(item["level"] == "error" for item in logs)

    by_query = client.get("/api/dashboard/logs?q=sx", headers=headers).json()["logs"]
    assert by_query
    assert any("sx" in str(item.get("data", {})) for item in by_query)

    with client.websocket_connect(f"/ws/logs?token={token}&level=error") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot"
        assert all(item["level"] == "error" for item in first["logs"])
